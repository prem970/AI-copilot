from sqlalchemy import select, delete
from fastapi import HTTPException
from app.models import Document, Extraction, Observation, Medication, Summary, Chunk, Job, Message, Conversation, Patient, now

def serialize(row):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}

def extraction_for(db, document):
    row = db.scalar(select(Extraction).where(Extraction.document_id == document.id, Extraction.revision == document.revision))
    if row is None:
        raise HTTPException(409, 'Extraction is not ready. Check document status.')
    return row

def confirmed_query(model, patient_id):
    return select(model).join(Document, model.document_id == Document.id).where(
        model.patient_id == patient_id, Document.deleted_at.is_(None),
        Document.approved_revision == model.revision,
        Document.approved_revision == Document.revision)

def enqueue(db, document, kind):
    pending = db.scalar(select(Job).where(Job.document_id == document.id, Job.kind == kind, Job.revision == document.revision, Job.status.in_(['queued', 'running'])))
    if pending is None:
        db.add(Job(document_id=document.id, kind=kind, revision=document.revision))

def invalidate(db, document):
    document.approved_revision = None
    document.summary_status = 'not_requested'
    document.index_status = 'not_requested'
    for model in (Observation, Medication, Summary, Chunk):
        db.execute(delete(model).where(model.document_id == document.id))
    # Old conversation answers must not retain invalidated/deleted medical evidence.
    for message in db.scalars(select(Message).join(Conversation).where(Message.role == 'assistant', Conversation.patient_id == document.patient_id)):
        if any(c.get('document_id') == document.id for c in message.data.get('citations', [])):
            message.data = {'status': 'source_changed', 'answer': 'Source records changed. Ask again for a current answer.', 'citations': [], 'language': message.data.get('language', 'en')}

def approve(db, document, request, medication_statuses=None):
    extraction = extraction_for(db, document)
    if request.revision != document.revision:
        raise HTTPException(409, 'Extraction changed. Reload before confirming.')
    if document.approved_revision == document.revision:
        return
    data = extraction.structured_candidate_data
    observations, medications = data.get('observations', []), data.get('medications', [])
    obs_ids = {item['id'] for item in observations} if request.confirm_all else set(request.observation_ids)
    med_ids = {item['id'] for item in medications} if request.confirm_all else set(request.medication_ids)
    if not obs_ids.issubset({item['id'] for item in observations}) or not med_ids.issubset({item['id'] for item in medications}):
        raise HTTPException(422, 'Unknown candidate identifier')
    if not obs_ids and not med_ids:
        raise HTTPException(422, 'Select at least one record to confirm')
    if not set(request.active_medications).issubset(med_ids):
        raise HTTPException(422, 'Active medications must be among selected medication identifiers')
    from datetime import date, datetime, time
    effective_date = date.fromisoformat(data['document_date']) if data.get('document_date') else None
    document.document_date = effective_date
    for item in observations:
        if item['id'] not in obs_ids:
            continue
        db.add(Observation(patient_id=document.patient_id, document_id=document.id, revision=document.revision,
            candidate_id=item['id'], display_name=item['test_name'], value_numeric=item.get('value_numeric'),
            value_text=item.get('value_text'), unit=item.get('unit'), reference_low=item.get('reference_low'),
            reference_high=item.get('reference_high'), source_abnormal_flag=item.get('source_abnormal_flag'),
            source_text=item['source_text'], effective_at=datetime.combine(effective_date, time()) if effective_date else None))
    for item in medications:
        if item['id'] not in med_ids:
            continue
        fields = {key: item.get(key) for key in ('medication_name', 'generic_name', 'strength', 'dose_instructions', 'route', 'frequency', 'duration')}
        prescribed = date.fromisoformat(item['prescription_date']) if item.get('prescription_date') else effective_date
        db.add(Medication(patient_id=document.patient_id, document_id=document.id, revision=document.revision,
            candidate_id=item['id'], **fields, source_text=item['source_text'], prescription_date=prescribed,
            medication_status=(medication_statuses or {}).get(item['id'], 'active' if item['id'] in request.active_medications else 'prescribed')))
    # Store only approved passages; partial review must not make unapproved claims retrievable.
    selected = [item for item in observations if item['id'] in obs_ids] + [item for item in medications if item['id'] in med_ids]
    for item in selected:
        import json
        fields = {k: v for k, v in item.items() if k not in ('confidence', 'validation_status') and v is not None}
        fields['document_date'] = data.get('document_date')
        fields['source_text'] = fields['source_text'][:900]
        if item['id'] in med_ids:
            fields['medication_status'] = (medication_statuses or {}).get(item['id'], 'active' if item['id'] in request.active_medications else 'prescribed')
        db.add(Chunk(patient_id=document.patient_id, document_id=document.id, revision=document.revision,
            page=item.get('page'), text=json.dumps(fields, ensure_ascii=False)))
    document.approved_revision = document.revision
    document.processing_status = 'completed'
    consent = db.get(Patient, document.patient_id).external_ai_consent
    document.index_status = 'queued' if consent else 'consent_required'
    document.summary_status = 'queued' if consent else 'consent_required'
    extraction.review_status = 'approved'
    extraction.validation_status = 'user_verified'
    if consent:
        enqueue(db, document, 'index')
        enqueue(db, document, 'summary')

def change_medication_status(db, document, medication, status):
    """Create a new approved revision so in-flight answers cannot use old status."""
    from app.contracts import Confirmation
    extraction = extraction_for(db, document)
    obs_ids = [o.candidate_id for o in db.scalars(confirmed_query(Observation, document.patient_id).where(Observation.document_id == document.id))]
    statuses = {m.candidate_id: m.medication_status for m in db.scalars(confirmed_query(Medication, document.patient_id).where(Medication.document_id == document.id))}
    candidate_id = medication.candidate_id
    statuses[candidate_id] = status
    invalidate(db, document)
    document.revision += 1
    db.add(Extraction(document_id=document.id, revision=document.revision, raw_ocr_text=extraction.raw_ocr_text,
        pages=extraction.pages, structured_candidate_data=extraction.structured_candidate_data,
        extraction_provider=extraction.extraction_provider, provider_model=extraction.provider_model))
    db.flush()
    approve(db, document, Confirmation(revision=document.revision, observation_ids=obs_ids, medication_ids=list(statuses)), statuses)
    db.flush()
    return db.scalar(confirmed_query(Medication, document.patient_id).where(Medication.document_id == document.id, Medication.candidate_id == candidate_id))
