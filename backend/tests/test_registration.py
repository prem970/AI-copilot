import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from app.main import app
from app.models import User, Patient, AuthSession, Audit
from app.security import verify_password


def registration(**changes):
    return {'full_name': 'New Patient', 'email': 'new@example.test',
            'password': 'new-account-password', 'confirm_password': 'new-account-password', **changes}


def test_registration_creates_private_account_and_can_sign_in_again(factory):
    with TestClient(app) as client:
        response = client.post('/api/v1/auth/register', json=registration(full_name='  New Patient  ', email='  NEW@example.test  '))
        assert response.status_code == 201, response.text
        data = response.json()
        patient_id = data['patient']['id']
        assert data['patient']['full_name'] == 'New Patient'
        assert data['patient']['email'] == 'new@example.test'
        assert not data['patient']['external_ai_consent']
        assert 'password_hash' not in data['patient']
        cookies = response.headers.get_list('set-cookie')
        assert any('health_session=' in cookie and 'HttpOnly' in cookie and 'SameSite=strict' in cookie for cookie in cookies)
        assert client.get('/api/v1/auth/session').json()['patient']['id'] == patient_id
        assert client.patch('/api/v1/patient/me', json={'blood_group': 'O+'}).status_code == 403
        client.headers['X-CSRF-Token'] = data['csrf_token']
        assert client.patch('/api/v1/patient/me', json={'blood_group': 'O+'}).status_code == 200
        assert client.post('/api/v1/auth/logout').status_code == 200
        assert client.get('/api/v1/auth/session').status_code == 401
    # A fresh client proves the credentials work independently of the signup session.
    with TestClient(app) as other:
        assert other.post('/api/v1/auth/login', json={'email': 'new@example.test', 'password': 'wrong-password'}).status_code == 401
        response = other.post('/api/v1/auth/login', json={'email': 'NEW@example.test', 'password': 'new-account-password'})
        assert response.status_code == 200
        assert response.json()['patient']['id'] == patient_id
        assert response.json()['patient']['blood_group'] == 'O+'
    with factory() as db:
        user = db.scalar(select(User).where(User.email == 'new@example.test'))
        assert user.password_hash != 'new-account-password'
        assert verify_password(user.password_hash, 'new-account-password')
        assert db.scalar(select(func.count()).select_from(User)) == 1
        assert db.scalar(select(func.count()).select_from(Patient)) == 1
        assert db.scalar(select(Audit).where(Audit.action == 'account_created')).user_id == user.id


def test_duplicate_registration_preserves_existing_password_and_profile(factory):
    with TestClient(app) as client:
        assert client.post('/api/v1/auth/register', json=registration()).status_code == 201
        client.cookies.clear()
        result = client.post('/api/v1/auth/register', json=registration(email='NEW@example.test', full_name='Replacement', password='replacement-password', confirm_password='replacement-password'))
        assert result.status_code == 409
        assert 'Sign in instead' in result.json()['detail']
        assert client.get('/api/v1/auth/session').status_code == 401
        assert client.post('/api/v1/auth/login', json={'email': 'new@example.test', 'password': 'replacement-password'}).status_code == 401
        result = client.post('/api/v1/auth/login', json={'email': 'new@example.test', 'password': 'new-account-password'})
        assert result.status_code == 200
        assert result.json()['patient']['full_name'] == 'New Patient'
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 1
        assert db.scalar(select(func.count()).select_from(Patient)) == 1


@pytest.mark.parametrize('changes', [
    {'full_name': '   '}, {'full_name': 'a' * 161},
    {'email': 'invalid'}, {'email': 'two@@example.test'}, {'email': 'a b@example.test'},
    {'password': 'short', 'confirm_password': 'short'},
    {'confirm_password': 'different-password'},
    {'password': 'a' * 201, 'confirm_password': 'a' * 201},
])
def test_invalid_registration_does_not_create_account(factory, changes):
    with TestClient(app) as client:
        assert client.post('/api/v1/auth/register', json=registration(**changes)).status_code == 422
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 0
        assert db.scalar(select(func.count()).select_from(Patient)) == 0
        assert db.scalar(select(func.count()).select_from(AuthSession)) == 0


def test_registration_rejects_untrusted_origins(factory):
    with TestClient(app) as client:
        assert client.post('/api/v1/auth/register', json=registration(), headers={'Origin': 'https://untrusted.test'}).status_code == 403
        assert client.post('/api/v1/auth/register', json=registration(), headers={'Origin': 'http://127.0.0.1:5173'}).status_code == 201


def test_registration_limits_attempts_without_blocking_existing_login(factory):
    with TestClient(app) as client:
        assert client.post('/api/v1/auth/register', json=registration()).status_code == 201
        for _ in range(4):
            assert client.post('/api/v1/auth/register', json=registration()).status_code == 409
        assert client.post('/api/v1/auth/register', json=registration(email='another@example.test')).status_code == 429
        assert client.post('/api/v1/auth/login', json={'email': 'new@example.test', 'password': 'new-account-password'}).status_code == 200
