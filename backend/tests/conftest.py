import os
os.environ['ENVIRONMENT'] = 'test'
os.environ['DATABASE_URL'] = 'sqlite://'

import io
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from reportlab.pdfgen import canvas
from app.main import app
from app import db as database
from app.db import Base, make_engine
from app.models import User, Patient
from app.security import hasher
from app.core.config import settings

@pytest.fixture
def factory(tmp_path, monkeypatch):
    url = os.environ.get('TEST_DATABASE_URL', 'sqlite:///' + str(tmp_path / 'test.db'))
    if url.startswith('mysql'):
        from sqlalchemy.engine import make_url
        if not make_url(url).database.endswith('_verify'):
            raise RuntimeError('MySQL test database name must end in _verify. Never run tests against patient data.')
    engine = make_engine(url)
    if url.startswith('mysql'):
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, 'SessionLocal', factory)
    monkeypatch.setattr(settings, 'storage_dir', tmp_path / 'storage')
    monkeypatch.setattr(settings, 'sarvam_api_key', '')
    monkeypatch.setattr(settings, 'laya_api_key', '')
    monkeypatch.setattr(settings, 'gemini_api_key', '')
    def override():
        with factory() as db:
            yield db
    app.dependency_overrides[database.get_db] = override
    yield factory
    app.dependency_overrides.clear()
    if url.startswith('mysql'):
        Base.metadata.drop_all(engine)
    engine.dispose()

@pytest.fixture
def account(factory):
    with factory.begin() as db:
        user = User(email='pilot@example.test', password_hash=hasher.hash('test-password-long'))
        db.add(user); db.flush()
        patient = Patient(user_id=user.id, full_name='Test Patient', email=user.email)
        db.add(patient); db.flush()
        return patient.id

@pytest.fixture
def client(factory, account):
    with TestClient(app) as client:
        result = client.post('/api/v1/auth/login', json={'email':'pilot@example.test','password':'test-password-long'})
        assert result.status_code == 200
        client.headers['X-CSRF-Token'] = result.json()['csrf_token']
        yield client

def pdf_bytes(lines=None):
    stream = io.BytesIO()
    page = canvas.Canvas(stream)
    for index, line in enumerate(lines or ['Report Date: 2026-05-06', 'Fasting Blood Glucose: 138 mg/dL (70 - 99) [H]', 'HbA1c: 7.4 % (4.0 - 5.6) [H]']):
        page.drawString(40, 800-index*24, line)
    page.save()
    return stream.getvalue()

def upload_processed(client):
    result = client.post('/api/v1/documents', files={'file': ('report.pdf', pdf_bytes(), 'application/pdf')})
    assert result.status_code == 202, result.text
    from app.worker import claim_job, run_job
    import asyncio
    asyncio.run(run_job(*claim_job()))
    identifier = result.json()['id']
    extraction = client.get(f'/api/v1/documents/{identifier}/extraction')
    assert extraction.status_code == 200, extraction.text
    return identifier, extraction.json()

def confirm(client, identifier, extraction):
    return client.post(f'/api/v1/documents/{identifier}/confirm', json={
        'revision':extraction['revision'], 'confirm_all':True, 'active_medications':[]})
