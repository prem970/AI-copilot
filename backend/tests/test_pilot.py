import asyncio
from datetime import timedelta
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from app.main import app
from app.models import User, Patient, Document, Observation, Medication, Summary, Job, AuthSession, Chunk, Conversation, Message, now
from app.security import hasher
from app.worker import claim_job, run_job, fail_job, save_result
from app.ai import ProviderError, validate_answer, numbers
from app.services.medical_nlp import parse_medical_document_text
from conftest import pdf_bytes, upload_processed, confirm
import pytest

def test_empty_database_has_no_seed(factory):
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Patient)) == 0
        assert db.scalar(select(func.count()).select_from(Document)) == 0

def test_auth_requires_valid_session_and_csrf(client):
    assert client.get('/api/v1/auth/session').status_code == 200
    assert client.get('/api/v1/auth/session').headers['cache-control'] == 'no-store'
    assert client.patch('/api/v1/patient/me', json={'full_name':'Changed'}, headers={'X-CSRF-Token':''}).status_code == 403
    assert client.patch('/api/v1/patient/me', json={'full_name':'Changed'}, headers={'Origin':'https://untrusted.test'}).status_code == 403
    assert client.post('/api/v1/auth/logout').status_code == 200
    assert client.get('/api/v1/documents').status_code == 401
    assert client.post('/api/v1/auth/demo-login').status_code == 404

def test_session_expiry(client, factory):
    with factory.begin() as db:
        for session in db.scalars(select(AuthSession)):
            session.expires_at = now()-timedelta(seconds=1)
    assert client.get('/api/v1/patient/me').status_code == 401

def test_login_throttles_failures(factory, account):
    with TestClient(app) as client:
        for _ in range(8):
            assert client.post('/api/v1/auth/login', json={'email':'pilot@example.test','password':'bad'}).status_code == 401
        assert client.post('/api/v1/auth/login', json={'email':'pilot@example.test','password':'bad'}).status_code == 429

def test_profile_updates_persist(client, factory, account):
    response = client.patch('/api/v1/patient/me', json={'full_name':'Real Name','blood_group':'O+','contact_phone':None,'external_ai_consent':True})
    assert response.status_code == 200
    with factory() as db:
        patient = db.get(Patient, account)
        assert patient.full_name == 'Real Name'
        assert patient.external_ai_consent and patient.consent_at
    assert client.patch('/api/v1/patient/me', json={'date_of_birth':'2999-01-01'}).status_code == 422

def test_invalid_file_is_never_a_report(client):
    result = client.post('/api/v1/documents', files={'file':('lipid_report.pdf',b'%PDF fake medical file','application/pdf')})
    assert result.status_code == 400
    assert client.get('/api/v1/documents').json() == []
    result = client.post('/api/v1/documents', files={'file':('report.pdf',pdf_bytes(),'image/png')})
    assert result.status_code == 400

def test_image_requires_consent(client):
    from PIL import Image
    import io
    stream = io.BytesIO(); Image.new('RGB',(20,20)).save(stream,'PNG')
    assert client.post('/api/v1/documents', files={'file':('scan.png',stream.getvalue(),'image/png')}).status_code == 409

def test_upload_processing_and_idempotent_confirmation(client, factory):
    identifier, extraction = upload_processed(client)
    assert extraction['extraction_provider'] == 'local_pdf_parser'
    items = extraction['structured_candidate_data']['observations']
    assert len(items) == 2 and items[0]['value_numeric'] == 138
    assert items[0]['page'] == 1
    assert client.get('/api/v1/observations').json() == []
    assert confirm(client,identifier,extraction).status_code == 200
    assert confirm(client,identifier,extraction).status_code == 200
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Observation)) == 2
        assert db.scalar(select(func.count()).select_from(Chunk)) == 2
    records = client.get('/api/v1/observations').json()
    assert all(item['effective_at'].startswith('2026-05-06') for item in records)
    assert client.get('/api/v1/observations/trends').json()[0]['history'][0]['date'] == '2026-05-06'

def test_partial_approval_only_indexes_selected_records(client, factory):
    identifier, extraction = upload_processed(client)
    selected = extraction['structured_candidate_data']['observations'][0]['id']
    response = client.post(f'/api/v1/documents/{identifier}/confirm',json={'revision':1,'observation_ids':[selected]})
    assert response.status_code == 200
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Observation)) == 1
        assert db.scalar(select(func.count()).select_from(Chunk)) == 1

def test_corrections_invalidate_records_summaries_and_chat(client, factory):
    identifier, extraction = upload_processed(client)
    confirm(client,identifier,extraction)
    with factory.begin() as db:
        document = db.get(Document,identifier)
        conversation = Conversation(patient_id=document.patient_id); db.add(conversation); db.flush()
        db.add(Message(conversation_id=conversation.id,role='assistant',data={'answer':'Old value','citations':[{'document_id':identifier}]}))
        db.add(Summary(document_id=identifier,revision=1,language='en',data={'overview':'Old'},provider_model='test-fixture'))
    data = extraction['structured_candidate_data']
    data['observations'][0]['value_numeric'] = 0
    response = client.patch(f'/api/v1/documents/{identifier}/extraction',json={'revision':1,'structured_candidate_data':data})
    assert response.status_code == 200 and response.json()['revision'] == 2
    assert response.json()['structured_candidate_data']['observations'][0]['value_text'] == '0.0'
    assert client.get('/api/v1/observations').json() == []
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Summary)) == 0
        assert db.scalar(select(Message)).data['status'] == 'source_changed'
    assert confirm(client,identifier,extraction).status_code == 409
    assert confirm(client,identifier,response.json()).status_code == 200
    assert any(item['value_numeric'] == 0 for item in client.get('/api/v1/observations').json())

def test_owner_isolation_every_document_route(client, factory):
    identifier, extraction = upload_processed(client)
    with factory.begin() as db:
        user = User(email='other@example.test',password_hash=hasher.hash('other-password-long')); db.add(user); db.flush()
        db.add(Patient(user_id=user.id,full_name='Other Test',email=user.email))
    with TestClient(app) as other:
        login = other.post('/api/v1/auth/login',json={'email':'other@example.test','password':'other-password-long'})
        other.headers['X-CSRF-Token'] = login.json()['csrf_token']
        for suffix in ('','/file','/status','/extraction','/summary'):
            assert other.get(f'/api/v1/documents/{identifier}'+suffix).status_code == 404
        assert other.delete(f'/api/v1/documents/{identifier}').status_code == 404
        assert other.post(f'/api/v1/documents/{identifier}/confirm',json={'revision':1,'confirm_all':True}).status_code == 404
        assert other.patch(f'/api/v1/documents/{identifier}/extraction',json={'revision':1,'structured_candidate_data':extraction['structured_candidate_data']}).status_code == 404
        assert other.get('/api/v1/documents',headers={'X-Patient-Id':client.get('/api/v1/patient/me').json()['id']}).json() == []

def test_deletion_removes_records_and_queues_cleanup(client, factory):
    identifier, extraction = upload_processed(client); confirm(client,identifier,extraction)
    assert client.delete(f'/api/v1/documents/{identifier}').status_code == 200
    assert client.get(f'/api/v1/documents/{identifier}/file').status_code == 404
    assert client.get('/api/v1/observations').json() == []
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Chunk)) == 0
        assert db.scalar(select(Job).where(Job.kind=='cleanup')).status == 'queued'

def test_worker_recovers_expired_lease(client, factory):
    result = client.post('/api/v1/documents',files={'file':('test.pdf',pdf_bytes(),'application/pdf')})
    first = claim_job()
    with factory.begin() as db:
        db.get(Job, first[0]).lease_until = now()-timedelta(seconds=5)
    second = claim_job()
    assert second[0] == first[0] and second[1] != first[1]
    fail_job(*first,ProviderError('old lease failure'))
    asyncio.run(run_job(*second))
    assert client.get('/api/v1/documents/'+result.json()['id']).json()['processing_status'] == 'awaiting_review'

def test_summary_outage_does_not_undo_review(client, factory):
    client.patch('/api/v1/patient/me',json={'external_ai_consent':True})
    identifier, extraction = upload_processed(client); confirm(client,identifier,extraction)
    with factory.begin() as db:
        job = db.scalar(select(Job).where(Job.kind=='summary')); job.status='running'; job.lease_token='test-lease'; job.attempts=3
        job_id = job.id
    fail_job(job_id,'test-lease',ProviderError('Sarvam not configured'))
    assert client.get('/api/v1/documents/'+identifier).json()['processing_status'] == 'completed'
    assert client.get('/api/v1/documents/'+identifier).json()['summary_status'] == 'failed'
    assert len(client.get('/api/v1/observations').json()) == 2

def test_parser_never_fills_unknown_clinical_details():
    data = parse_medical_document_text('Fasting Blood Glucose: 100\nTab. ExampleDrug')
    assert data['document_date'] is None and data['healthcare_provider'] is None
    obs = data['observations'][0]
    assert obs['unit'] is None and obs['reference_low'] is None and obs['source_abnormal_flag'] is None
    medication = data['medications'][0]
    assert medication['strength'] is None and medication['frequency'] is None and medication['route'] is None
    assert parse_medical_document_text('Unreadable image','lipid_report.pdf')['observations'] == []
    assert parse_medical_document_text('Fasting Blood Glucose: 138 mg/dL Normal range: 70 - 99')['observations'][0]['source_abnormal_flag'] is None
    assert parse_medical_document_text('Blood Urea: 30 mg/dL')['observations'][0]['test_name'] == 'Blood Urea'

def test_answer_validation_rejects_invented_values_and_citations():
    sources=[{'id':'s1','text':'Glucose 138 mg/dL'}]
    valid={'claims':[{'text':'Glucose was 138 mg/dL.','source_ids':['s1']}]}
    assert validate_answer(valid,sources)[0]['text'].startswith('Glucose')
    for data in ({'claims':[{'text':'Glucose 139 mg/dL','source_ids':['s1']}]}, {'claims':[{'text':'Glucose 138 mg/dL','source_ids':['other']}]}, {'claims':[{'text':'Double your medication dose','source_ids':['s1']}]}):
        with pytest.raises(ProviderError): validate_answer(data,sources)
    assert numbers('138 138') != numbers('138')

def test_conversation_requires_ownership_and_consent(client, factory):
    conversation = client.post('/api/v1/rag/conversations',json={}).json()
    assert client.post('/api/v1/rag/conversations/'+conversation['id']+'/messages',json={'question':'Glucose?'}).status_code == 409
    assert client.get('/api/v1/rag/conversations/10000000-0000-0000-0000-000000000001/messages').status_code == 404

def test_rag_no_evidence_and_provider_outage_are_explicit(client, monkeypatch):
    client.patch('/api/v1/patient/me',json={'external_ai_consent':True})
    conversation = client.post('/api/v1/rag/conversations',json={}).json()
    import app.rag as rag
    async def decide_fixture(*args):
        return {'answers':{'route':{'choice':'records','probabilities':{'records':0.95}}},'routing':{'model':'test-fixture'}}
    monkeypatch.setattr(rag,'decide',decide_fixture)
    response=client.post('/api/v1/rag/conversations/'+conversation['id']+'/messages',json={'question':'What is my glucose?'})
    assert response.json()['data']['status']=='insufficient_evidence'
    async def unavailable(*args): raise ProviderError('Local inference unavailable')
    monkeypatch.setattr(rag,'decide',unavailable)
    response=client.post('/api/v1/rag/conversations/'+conversation['id']+'/messages',json={'question':'Glucose?'})
    assert response.json()['data']['status']=='unavailable'
