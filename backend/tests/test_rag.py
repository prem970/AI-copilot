"""Adversarial provider fixtures live only in tests, never in runtime code."""
import asyncio
import json
from types import SimpleNamespace
import pytest
from sqlalchemy import select
from app.models import Patient, Document, Chunk, Extraction, Summary, Conversation, Message, Medication, Job
from app.ai import ProviderError, validate_answer
from app.rag import source_data
from conftest import upload_processed, confirm

def prepared(client):
    client.patch('/api/v1/patient/me', json={'external_ai_consent':True})
    identifier, extraction = upload_processed(client)
    assert confirm(client, identifier, extraction).status_code == 200
    return identifier, extraction

def providers(monkeypatch, route='records', support=True):
    import app.rag as rag
    async def decision(state, questions):
        if 'route' in questions:
            return {'answers':{'route':{'choice':route, 'probabilities':{route:0.98}}}, 'routing':{'model':'fixture'}}
        if 'relevant' in questions:
            return {'answers':{'relevant':{'noul':0.98}}}
        choice = 'answer' if support else 'abstain'
        return {'answers':{'supported':{'choice':choice, 'probabilities':{choice:0.98}}}}
    async def generate(prompt):
        source = next(s for s in json.loads(prompt)['reviewed_sources'] if 'Fasting Blood Glucose' in s['text'])
        return {'claims':[{'text':'The reviewed glucose result was 138 mg/dL.', 'source_ids':[source['id']]}]}
    monkeypatch.setattr(rag, 'decide', decision)
    monkeypatch.setattr(rag, 'chat_json', generate)
    return rag

def ask(client):
    conversation = client.post('/api/v1/rag/conversations', json={}).json()
    response = client.post('/api/v1/rag/conversations/'+conversation['id']+'/messages', json={'question':'What is my glucose result?'})
    return response

def test_supported_answer_has_owned_live_source(client, monkeypatch):
    identifier, _ = prepared(client)
    providers(monkeypatch)
    result = ask(client).json()['data']
    assert result['status'] == 'answered'
    assert result['citations'][0]['document_id'] == identifier
    assert client.get(result['citations'][0]['url']).status_code == 200

def test_laya_abstention_discards_generated_claim(client, monkeypatch):
    prepared(client); providers(monkeypatch, support=False)
    result = ask(client).json()['data']
    assert result['status'] == 'insufficient_evidence' and result['citations'] == []

def test_corrected_numbers_exclude_old_ocr_from_authoritative_evidence():
    chunk = SimpleNamespace(id='c', revision=2, page=1, text=json.dumps({'test_name':'Glucose', 'value_numeric':0, 'unit':'mg/dL', 'source_text':'Glucose: 138 mg/dL'}))
    source = source_data(chunk, SimpleNamespace(id='d', original_filename='record.pdf'))
    assert '138' not in source['text'] and '138' in source['excerpt']
    with pytest.raises(ProviderError):
        validate_answer({'claims':[{'text':'Glucose: 138 mg/dL', 'source_ids':['c']}]}, [source])

def test_stale_vectors_cannot_become_evidence(client, factory, monkeypatch):
    identifier, _ = prepared(client)
    with factory() as db:
        stale_ids = [c.id for c in db.scalars(select(Chunk))]
    assert client.delete('/api/v1/documents/'+identifier).status_code == 200
    rag = providers(monkeypatch, route='narrative')
    async def embedding(*args, **kwargs): return [[0.0]*384]
    class StaleVectorClient:
        def query_points(self, **kwargs):
            assert kwargs['query_filter'].must[0].key == 'patient_id'
            return SimpleNamespace(points=[SimpleNamespace(id=i) for i in stale_ids])
        def close(self): pass
    monkeypatch.setattr(rag,'embed',embedding)
    monkeypatch.setattr(rag,'vector_client',StaleVectorClient)
    assert ask(client).json()['data']['status'] == 'insufficient_evidence'

def test_consent_revoked_during_decision_prevents_provider_call(client, factory, monkeypatch, account):
    prepared(client)
    rag = providers(monkeypatch)
    original = rag.decide
    called = []
    async def decision(state, questions):
        if 'relevant' in questions:
            with factory.begin() as db: db.get(Patient, account).external_ai_consent = False
        return await original(state, questions)
    async def forbidden(*args): called.append(True); raise AssertionError('External call after revocation')
    monkeypatch.setattr(rag,'decide',decision)
    monkeypatch.setattr(rag,'chat_json',forbidden)
    assert ask(client).status_code == 409
    assert not called

def test_medication_status_creates_revision_and_invalidates_derived_answers(client, factory):
    identifier, extraction = upload_processed(client)
    candidate = extraction['structured_candidate_data']
    candidate['medications'] = [{'id':'med1','medication_name':'ExampleDrug','strength':'5 mg','source_text':'Tab. ExampleDrug 5 mg','page':1}]
    edited = client.patch('/api/v1/documents/'+identifier+'/extraction', json={'revision':extraction['revision'],'structured_candidate_data':candidate}).json()
    assert confirm(client,identifier,edited).status_code == 200
    medication = client.get('/api/v1/medications').json()[0]
    with factory.begin() as db:
        db.add(Summary(document_id=identifier, revision=edited['revision'], language='en', provider_model='fixture', data={}))
    changed = client.patch('/api/v1/medications/'+medication['id'], json={'medication_status':'discontinued'})
    assert changed.status_code == 200 and changed.json()['medication_status'] == 'discontinued'
    assert client.get('/api/v1/documents/'+identifier).json()['revision'] == edited['revision']+1
    assert len(client.get('/api/v1/observations').json()) == 2
    with factory() as db:
        assert db.scalar(select(Summary)) is None
        chunk = next(c for c in db.scalars(select(Chunk)) if 'ExampleDrug' in c.text)
        assert json.loads(chunk.text)['medication_status'] == 'discontinued'

def test_deleted_source_cannot_save_inflight_answer(client, monkeypatch):
    identifier, _ = prepared(client)
    rag = providers(monkeypatch)
    original = rag.decide
    async def decision(state, questions):
        if 'supported' in questions:
            assert (await asyncio.to_thread(client.delete, '/api/v1/documents/'+identifier)).status_code == 200
        return await original(state, questions)
    monkeypatch.setattr(rag, 'decide', decision)
    result = ask(client).json()['data']
    assert result['status'] == 'source_changed' and not result['citations']
