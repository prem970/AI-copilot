import secrets
from datetime import datetime, timedelta
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile, File, Query
from fastapi.responses import FileResponse
from sqlalchemy import select, delete, func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.db import get_db
from app.core.config import settings
from app.models import User, Patient, AuthSession, LoginAttempt, Document, Extraction, Observation, Medication, Summary, Conversation, Message, Job, now, uid
from app.contracts import LoginInput, RegisterInput, ProfileInput, ExtractionEdit, Confirmation, MedicationStatus, ConversationInput, MessageInput
from app.security import current_patient, check_origin, issue_session, hasher, verify_password, DUMMY_HASH, digest, owned_document, audit, require_consent
from app.repository import serialize, extraction_for, confirmed_query, enqueue, invalidate, approve, change_medication_status
from app.storage import read_upload, validate_file, file_path, safe_name

router = APIRouter(prefix='/api/v1')
PatientDep = Depends(current_patient)
DB = Depends(get_db)

def authenticated_response(request, response, db, user, patient, action):
    old = request.cookies.get('health_session')
    if old:
        db.execute(delete(AuthSession).where(AuthSession.token_hash == digest(old)))
    token, csrf = issue_session(db, user)
    audit(db, patient, action, user.id)
    db.commit()
    cookie = dict(secure=settings.cookie_secure, samesite='strict', max_age=settings.session_hours * 3600, path='/')
    response.set_cookie('health_session', token, httponly=True, **cookie)
    response.set_cookie('health_csrf', csrf, httponly=False, **cookie)
    return {'patient': serialize(patient), 'csrf_token': csrf}

@router.post('/auth/register', status_code=201)
def register(payload: RegisterInput, request: Request, response: Response, db: Session = DB):
    check_origin(request)
    address = request.client.host if request.client else 'unknown'
    key = digest('registration-ip:' + address)
    cutoff = now() - timedelta(minutes=15)
    count = db.scalar(select(func.count()).select_from(LoginAttempt).where(LoginAttempt.key == key, LoginAttempt.created_at > cutoff))
    if count >= 5:
        raise HTTPException(429, 'Too many account creation attempts. Try again in 15 minutes.')
    db.execute(delete(LoginAttempt).where(LoginAttempt.created_at < cutoff))
    db.add(LoginAttempt(key=key))
    db.commit()
    if db.scalar(select(User.id).where(User.email == payload.email)):
        raise HTTPException(409, 'An account with this email already exists. Sign in instead.')
    user = User(email=payload.email, password_hash=hasher.hash(payload.password))
    try:
        db.add(user)
        db.flush()
        patient = Patient(user_id=user.id, full_name=payload.full_name, email=user.email)
        db.add(patient)
        db.flush()
        return authenticated_response(request, response, db, user, patient, 'account_created')
    except IntegrityError:
        db.rollback()
        if db.scalar(select(User.id).where(User.email == payload.email)):
            raise HTTPException(409, 'An account with this email already exists. Sign in instead.')
        raise

@router.post('/auth/login')
def login(payload: LoginInput, request: Request, response: Response, db: Session = DB):
    check_origin(request)
    email = payload.email.strip().lower()
    address = request.client.host if request.client else 'unknown'
    keys = [digest('email:' + email), digest('ip:' + address)]
    cutoff = now() - timedelta(minutes=15)
    for key, limit in zip(keys, (8, 40)):
        count = db.scalar(select(func.count()).select_from(LoginAttempt).where(LoginAttempt.key == key, LoginAttempt.created_at > cutoff))
        if count >= limit:
            raise HTTPException(429, 'Too many sign-in attempts. Try again in 15 minutes.')
    user = db.scalar(select(User).where(User.email == email))
    valid = verify_password(user.password_hash if user else DUMMY_HASH, payload.password)
    if not valid or not user or not user.enabled:
        for key in keys:
            db.add(LoginAttempt(key=key))
        db.commit()
        raise HTTPException(401, 'Email or password is incorrect')
    db.execute(delete(LoginAttempt).where(LoginAttempt.key == keys[0]))
    db.execute(delete(LoginAttempt).where(LoginAttempt.created_at < cutoff))
    patient = db.scalar(select(Patient).where(Patient.user_id == user.id))
    if patient is None:
        raise HTTPException(401, 'Account profile is unavailable')
    return authenticated_response(request, response, db, user, patient, 'signed_in')

@router.get('/auth/session')
def session(request: Request, patient: Patient = PatientDep):
    return {'patient': serialize(patient), 'csrf_token': request.cookies.get('health_csrf', '')}

@router.post('/auth/logout')
def logout(request: Request, response: Response, patient: Patient = PatientDep, db: Session = DB):
    db.execute(delete(AuthSession).where(AuthSession.token_hash == digest(request.cookies.get('health_session', ''))))
    audit(db, patient, 'signed_out')
    db.commit()
    response.delete_cookie('health_session', path='/')
    response.delete_cookie('health_csrf', path='/')
    return {'status': 'signed_out'}

@router.get('/patient/me')
def profile(patient: Patient = PatientDep):
    return serialize(patient)

@router.patch('/patient/me')
def update_profile(payload: ProfileInput, patient: Patient = PatientDep, db: Session = DB):
    values = payload.model_dump(exclude_unset=True)
    if values.get('date_of_birth') and values['date_of_birth'] > now().date():
        raise HTTPException(422, 'Date of birth cannot be in the future')
    if 'full_name' in values and (not values['full_name'] or not values['full_name'].strip()):
        raise HTTPException(422, 'Full name cannot be empty')
    if values.get('preferred_language') is None:
        values.pop('preferred_language', None)
    if 'external_ai_consent' in values:
        if values['external_ai_consent'] is None:
            raise HTTPException(422, 'Consent must be true or false')
        patient.consent_at = now()
        audit(db, patient, 'external_ai_consent_changed', allowed=values['external_ai_consent'])
    for name, value in values.items():
        setattr(patient, name, value.strip() if isinstance(value, str) else value)
    audit(db, patient, 'profile_updated')
    db.commit()
    return serialize(patient)

@router.post('/documents', status_code=202)
async def upload(file: UploadFile = File(...), patient: Patient = PatientDep, db: Session = DB):
    data = await read_upload(file)
    mime = validate_file(data, file.content_type)
    if mime != 'application/pdf':
        require_consent(patient)
    identifier = uid()
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    path = file_path(identifier)
    path.write_bytes(data)
    try:
        document = Document(id=identifier, patient_id=patient.id, original_filename=safe_name(file.filename),
            storage_path=identifier+'.bin', mime_type=mime, file_size_bytes=len(data))
        db.add(document)
        db.flush()
        enqueue(db, document, 'extract')
        audit(db, patient, 'document_uploaded', identifier)
        db.commit()
        return serialize(document)
    except Exception:
        db.rollback()
        path.unlink(missing_ok=True)
        raise

@router.get('/documents')
def documents(patient: Patient = PatientDep, db: Session = DB,
        doc_type: str | None = None, status: str | None = None,
        offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
    query = select(Document).where(Document.patient_id == patient.id, Document.deleted_at.is_(None))
    if doc_type:
        query = query.where(Document.document_type == doc_type)
    if status:
        query = query.where(Document.processing_status == status)
    return [serialize(d) for d in db.scalars(query.order_by(Document.created_at.desc(), Document.id).offset(offset).limit(limit))]

@router.get('/documents/{document_id}')
@router.get('/documents/{document_id}/status')
def document_details(document_id: UUID, patient: Patient = PatientDep, db: Session = DB):
    return serialize(owned_document(db, patient, document_id))

@router.get('/documents/{document_id}/file')
def document_file(document_id: UUID, patient: Patient = PatientDep, db: Session = DB):
    document = owned_document(db, patient, document_id)
    path = file_path(document.id)
    if not path.exists():
        raise HTTPException(404, 'Source file unavailable')
    audit(db, patient, 'document_viewed', document.id)
    db.commit()
    return FileResponse(path, media_type=document.mime_type, filename=document.original_filename, content_disposition_type='inline',
        headers={'Content-Security-Policy': "sandbox; default-src 'none';"})

@router.post('/documents/{document_id}/process', status_code=202)
def retry_extraction(document_id: UUID, patient: Patient = PatientDep, db: Session = DB):
    document = owned_document(db, patient, document_id, lock=True)
    if document.processing_status in ('queued', 'processing'):
        return {'status': document.processing_status}
    if document.processing_status != 'failed':
        raise HTTPException(409, 'Only failed extraction can be retried. Edit the current review instead.')
    document.processing_status = 'queued'
    document.error_message = None
    enqueue(db, document, 'extract')
    audit(db, patient, 'extraction_retried', document.id)
    db.commit()
    return {'status': 'queued'}

@router.delete('/documents/{document_id}')
def delete_document(document_id: UUID, patient: Patient = PatientDep, db: Session = DB):
    document = owned_document(db, patient, document_id, lock=True)
    document.deleted_at = now()
    invalidate(db, document)
    db.execute(delete(Extraction).where(Extraction.document_id == document.id))
    enqueue(db, document, 'cleanup')
    audit(db, patient, 'document_deleted', document.id)
    db.commit()
    return {'status': 'deleted'}

@router.get('/documents/{document_id}/extraction')
def extraction(document_id: UUID, patient: Patient = PatientDep, db: Session = DB):
    return serialize(extraction_for(db, owned_document(db, patient, document_id)))

@router.get('/documents/{document_id}/jobs')
def document_jobs(document_id: UUID, patient: Patient = PatientDep, db: Session = DB):
    document = owned_document(db, patient, document_id)
    return [{'kind': job.kind, 'status': job.status, 'error': job.error, 'attempts': job.attempts}
        for job in db.scalars(select(Job).where(Job.document_id == document.id).order_by(Job.created_at.desc()).limit(20))]

@router.patch('/documents/{document_id}/extraction')
def edit_extraction(document_id: UUID, payload: ExtractionEdit, patient: Patient = PatientDep, db: Session = DB):
    document = owned_document(db, patient, document_id, lock=True)
    previous = extraction_for(db, document)
    if payload.revision != document.revision:
        raise HTTPException(409, 'Another update changed this extraction. Reload before editing.')
    data = payload.structured_candidate_data.model_dump(mode='json')
    if any(item.get('page', 1) and item['page'] > len(previous.pages) for kind in ('observations', 'medications') for item in data[kind]):
        raise HTTPException(422, 'Source page must exist in the uploaded document')
    if data == previous.structured_candidate_data:
        return serialize(previous)
    invalidate(db, document)
    document.revision += 1
    document.document_date = payload.structured_candidate_data.document_date
    document.document_type = payload.structured_candidate_data.document_type
    document.processing_status = 'awaiting_review'
    edited = Extraction(document_id=document.id, revision=document.revision, raw_ocr_text=previous.raw_ocr_text,
        pages=previous.pages, structured_candidate_data=data, extraction_provider=previous.extraction_provider,
        provider_model=previous.provider_model, review_status='in_review')
    db.add(edited)
    audit(db, patient, 'extraction_corrected', document.id, revision=document.revision)
    db.commit()
    return serialize(edited)

@router.post('/documents/{document_id}/confirm')
def confirm(document_id: UUID, payload: Confirmation, patient: Patient = PatientDep, db: Session = DB):
    document = owned_document(db, patient, document_id, lock=True)
    approve(db, document, payload)
    audit(db, patient, 'extraction_confirmed', document.id, revision=document.revision)
    db.commit()
    return {'status': 'confirmed', 'revision': document.revision}

@router.get('/observations')
def observations(patient: Patient = PatientDep, db: Session = DB, test_name: str | None = None):
    query = confirmed_query(Observation, patient.id)
    if test_name:
        query = query.where(Observation.display_name == test_name)
    return [serialize(o) for o in db.scalars(query.order_by(Observation.effective_at.desc(), Observation.created_at.desc()))]

@router.get('/observations/trends')
def trends(patient: Patient = PatientDep, db: Session = DB):
    groups = {}
    for row in db.scalars(confirmed_query(Observation, patient.id).where(Observation.effective_at.is_not(None), Observation.value_numeric.is_not(None)).order_by(Observation.effective_at)):
        key = (row.display_name, row.unit)
        groups.setdefault(key, []).append({'date': row.effective_at.date().isoformat(), 'value': row.value_numeric,
            'unit': row.unit, 'reference_low': row.reference_low, 'reference_high': row.reference_high, 'source_document_id': row.document_id})
    return [{'test_name': name, 'unit': unit, 'history': history} for (name, unit), history in groups.items()]

@router.get('/medications')
def medications(patient: Patient = PatientDep, db: Session = DB, status: str | None = None):
    query = confirmed_query(Medication, patient.id)
    if status:
        query = query.where(Medication.medication_status == status)
    return [serialize(m) for m in db.scalars(query.order_by(Medication.created_at.desc()))]

@router.patch('/medications/{medication_id}')
def medication_status(medication_id: UUID, payload: MedicationStatus, patient: Patient = PatientDep, db: Session = DB):
    medication = db.scalar(confirmed_query(Medication, patient.id).where(Medication.id == str(medication_id)))
    if medication is None:
        raise HTTPException(404, 'Medication not found')
    document = owned_document(db, patient, medication.document_id, lock=True)
    db.refresh(medication)
    if medication.medication_status != payload.medication_status:
        medication = change_medication_status(db, document, medication, payload.medication_status)
    audit(db, patient, 'medication_status_changed', medication.id, status=payload.medication_status)
    db.commit()
    return serialize(medication)

@router.get('/timeline')
def timeline(patient: Patient = PatientDep, db: Session = DB):
    docs = db.scalars(select(Document).where(Document.patient_id == patient.id, Document.deleted_at.is_(None)).order_by(Document.created_at.desc())).all()
    events = [{'id': d.id, 'event_type': 'document', 'title': d.original_filename, 'description': d.processing_status,
        'event_date': d.document_date or d.created_at.date(), 'source_document_id': d.id} for d in docs]
    return {'patient_id': patient.id, 'events': events, 'total_count': len(events)}

@router.get('/documents/{document_id}/summary')
def summary(document_id: UUID, lang: str = Query('en', pattern='^(en|ta)$'), patient: Patient = PatientDep, db: Session = DB):
    document = owned_document(db, patient, document_id)
    if document.approved_revision != document.revision:
        raise HTTPException(409, 'Confirm reviewed records before generating a summary')
    row = db.scalar(select(Summary).where(Summary.document_id == document.id, Summary.revision == document.revision, Summary.language == lang))
    if row is None:
        raise HTTPException(409, 'Summary is '+document.summary_status+'. You can retry generation.')
    return {'id': row.id, 'document_id': row.document_id, 'revision': row.revision, 'language': row.language,
        'provider_model': row.provider_model, 'created_at': row.created_at, **row.data}

@router.post('/documents/{document_id}/summary', status_code=202)
@router.post('/documents/{document_id}/summary/translate', status_code=202)
def generate_summary(document_id: UUID, patient: Patient = PatientDep, db: Session = DB):
    require_consent(patient)
    document = owned_document(db, patient, document_id, lock=True)
    if document.approved_revision != document.revision:
        raise HTTPException(409, 'Confirm the extraction first')
    document.summary_status = 'queued'
    enqueue(db, document, 'summary')
    db.commit()
    return {'status': 'queued'}

@router.post('/documents/{document_id}/index', status_code=202)
def retry_index(document_id: UUID, patient: Patient = PatientDep, db: Session = DB):
    require_consent(patient)
    document = owned_document(db, patient, document_id, lock=True)
    if document.approved_revision != document.revision:
        raise HTTPException(409, 'Confirm the extraction first')
    document.index_status = 'queued'
    enqueue(db, document, 'index')
    db.commit()
    return {'status': 'queued'}

@router.get('/abha/status')
def abha_status(patient: Patient = PatientDep):
    return {'patient_id': patient.id, 'available': False, 'is_linked': False, 'reason': 'Official ABDM onboarding is not configured'}

@router.get('/rag/conversations')
def conversations(patient: Patient = PatientDep, db: Session = DB):
    return [serialize(c) for c in db.scalars(select(Conversation).where(Conversation.patient_id == patient.id).order_by(Conversation.created_at.desc()))]

@router.post('/rag/conversations', status_code=201)
def create_conversation(payload: ConversationInput, patient: Patient = PatientDep, db: Session = DB):
    conversation = Conversation(patient_id=patient.id, title=payload.title)
    db.add(conversation)
    db.commit()
    return serialize(conversation)

def owned_conversation(db, patient, identifier):
    conversation = db.scalar(select(Conversation).where(Conversation.id == str(identifier), Conversation.patient_id == patient.id))
    if conversation is None:
        raise HTTPException(404, 'Conversation not found')
    return conversation

@router.get('/rag/conversations/{conversation_id}/messages')
def messages(conversation_id: UUID, patient: Patient = PatientDep, db: Session = DB):
    owned_conversation(db, patient, conversation_id)
    return [serialize(m) for m in db.scalars(select(Message).where(Message.conversation_id == str(conversation_id)).order_by(Message.created_at, Message.id))]

@router.post('/rag/conversations/{conversation_id}/messages')
async def ask(conversation_id: UUID, payload: MessageInput, patient: Patient = PatientDep, db: Session = DB):
    require_consent(patient)
    owned_conversation(db, patient, conversation_id)
    db.add(Message(conversation_id=str(conversation_id), role='user', data=payload.model_dump()))
    db.commit()
    from app.rag import answer
    from app.ai import ProviderError
    try:
        result = await answer(db, patient, payload.question, payload.language)
    except ProviderError as exc:
        result = {'status': 'unavailable', 'answer': str(exc), 'citations': [], 'language': payload.language}
    # Recheck current authorization/consent before storing or returning generated medical content.
    db.rollback()
    db.expire_all()
    fresh = db.get(Patient, patient.id)
    if not fresh.external_ai_consent or not db.get(User, fresh.user_id).enabled:
        raise HTTPException(409, 'External AI consent or account access changed')
    if result.get('status') == 'answered':
        for citation in result.get('citations', []):
            doc = db.get(Document, citation['document_id'])
            if not doc or doc.deleted_at or doc.patient_id != patient.id or doc.approved_revision != citation['revision'] or doc.revision != citation['revision']:
                result = {'status': 'source_changed', 'answer': 'Source records changed. Ask again.', 'citations': [], 'language': payload.language}
                break
    message = Message(conversation_id=str(conversation_id), role='assistant', data=result)
    db.add(message)
    audit(db, patient, 'rag_answer', str(conversation_id), status=result['status'])
    db.commit()
    return serialize(message)
