import hashlib
import secrets
from datetime import timedelta
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.config import settings
from app.db import get_db
from app.models import AuthSession, User, Patient, Document, Audit, now

hasher = PasswordHasher()
DUMMY_HASH = hasher.hash(secrets.token_urlsafe(32))

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

def verify_password(encoded, password):
    try:
        return hasher.verify(encoded, password)
    except (VerificationError, InvalidHashError):
        return False

def check_origin(request):
    origin = request.headers.get('origin')
    if origin and origin not in settings.origins:
        raise HTTPException(403, 'Origin is not allowed')

def current_patient(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get('health_session', '')
    session = db.get(AuthSession, digest(token)) if token else None
    if not session or session.expires_at <= now():
        raise HTTPException(401, 'Sign in to access your records')
    user = db.get(User, session.user_id)
    if not user or not user.enabled:
        raise HTTPException(401, 'Account is unavailable')
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        check_origin(request)
        csrf = request.headers.get('x-csrf-token', '')
        if not csrf or not secrets.compare_digest(session.csrf_hash, digest(csrf)):
            raise HTTPException(403, 'Session verification failed. Refresh and try again.')
    patient = db.scalar(select(Patient).where(Patient.user_id == user.id))
    if patient is None:
        raise HTTPException(401, 'Account profile is unavailable')
    return patient

def require_consent(patient):
    if not patient.external_ai_consent:
        raise HTTPException(409, 'Enable external AI processing consent in your profile before using hosted AI')

def owned_document(db, patient, document_id, lock=False):
    query = select(Document).where(Document.id == str(document_id), Document.patient_id == patient.id, Document.deleted_at.is_(None))
    if lock:
        query = query.with_for_update()
    document = db.scalar(query)
    if document is None:
        raise HTTPException(404, 'Document not found')
    return document

def audit(db, patient, action, resource_id=None, **details):
    db.add(Audit(user_id=patient.user_id if patient else None, action=action, resource_id=resource_id, details=details))

def issue_session(db, user):
    token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
    db.add(AuthSession(token_hash=digest(token), user_id=user.id, csrf_hash=digest(csrf), expires_at=now() + timedelta(hours=settings.session_hours)))
    return token, csrf
