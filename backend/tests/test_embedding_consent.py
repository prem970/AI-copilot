import asyncio
import pytest
from sqlalchemy import select
from app import worker
from app.ai import ProviderError
from app.models import Patient, Document, Chunk, Job
from app.repository import serialize
from app.rag import source_data
from conftest import upload_processed, confirm

def test_gemini_migration_refreshes_permission_without_removing_records(client, factory, monkeypatch):
    from importlib import import_module
    from app.models import Observation
    migration = import_module('migrations.versions.0004_gemini_embeddings')
    client.patch('/api/v1/patient/me', json={'external_ai_consent': True})
    identifier, extraction = upload_processed(client)
    assert confirm(client, identifier, extraction).status_code == 200
    with factory.begin() as db:
        db.get(Document, identifier).index_status = 'completed'
        for chunk in db.scalars(select(Chunk)):
            chunk.indexed = True
        db.flush()
        monkeypatch.setattr(migration.op, 'execute', db.execute)
        migration.upgrade()
    with factory() as db:
        patient = db.scalar(select(Patient))
        document = db.get(Document, identifier)
        assert not patient.external_ai_consent and patient.consent_at is None
        assert document.index_status == 'consent_required'
        assert document.approved_revision == document.revision
        assert len(db.scalars(select(Observation)).all()) == 2
        assert all(not chunk.indexed for chunk in db.scalars(select(Chunk)))
        assert all(job.status == 'cancelled' for job in db.scalars(select(Job).where(Job.kind.in_(['index', 'summary']))))

def indexing_data(factory, identifier):
    with factory() as db:
        document = db.get(Document, identifier)
        job = db.scalar(select(Job).where(Job.document_id == identifier, Job.kind == 'index'))
        sources = [source_data(c, document) for c in db.scalars(select(Chunk).where(Chunk.document_id == identifier))]
        return {'job': serialize(job), 'document': serialize(document), 'sources': sources}

def test_confirmation_requires_consent_before_hosted_indexing(client, factory):
    identifier, extraction = upload_processed(client)
    assert confirm(client, identifier, extraction).status_code == 200
    assert client.get('/api/v1/documents/' + identifier).json()['index_status'] == 'consent_required'
    with factory() as db:
        assert db.scalar(select(Job).where(Job.kind == 'index')) is None
    assert client.post('/api/v1/documents/' + identifier + '/index').status_code == 409
    assert client.patch('/api/v1/patient/me', json={'external_ai_consent': True}).status_code == 200
    assert client.post('/api/v1/documents/' + identifier + '/index').status_code == 202

def test_revoked_consent_stops_embedding_request(client, factory, monkeypatch):
    client.patch('/api/v1/patient/me', json={'external_ai_consent': True})
    identifier, extraction = upload_processed(client)
    confirm(client, identifier, extraction)
    data = indexing_data(factory, identifier)
    client.patch('/api/v1/patient/me', json={'external_ai_consent': False})
    async def forbidden(*args):
        pytest.fail('Embedding provider called after consent was revoked')
    monkeypatch.setattr(worker, 'embed', forbidden)
    with pytest.raises(ProviderError, match='consent'):
        asyncio.run(worker.perform(data))

def test_revocation_during_embedding_prevents_vector_publication(client, factory, monkeypatch, account):
    client.patch('/api/v1/patient/me', json={'external_ai_consent': True})
    identifier, extraction = upload_processed(client)
    confirm(client, identifier, extraction)
    data = indexing_data(factory, identifier)
    async def embedding(texts):
        with factory.begin() as db:
            db.get(Patient, account).external_ai_consent = False
        return [[1.0, 0.0] for _ in texts]
    monkeypatch.setattr(worker, 'embed', embedding)
    monkeypatch.setattr(worker, 'index_sync', lambda *args: pytest.fail('Revoked index published to vector storage'))
    with pytest.raises(ProviderError, match='consent'):
        asyncio.run(worker.perform(data))
