from datetime import datetime
from uuid import uuid4
from sqlalchemy import String, Text, JSON, DateTime, Date, Integer, Float, Boolean, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.mysql import DATETIME

TIMESTAMP = DateTime().with_variant(DATETIME(fsp=6), "mysql")
from app.db import Base

def now():
    return datetime.utcnow()

def uid():
    return str(uuid4())

class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=now)

class Patient(Base):
    __tablename__ = 'patients'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), unique=True)
    full_name: Mapped[str] = mapped_column(String(160))
    date_of_birth: Mapped[datetime | None] = mapped_column(Date)
    gender: Mapped[str | None] = mapped_column(String(16))
    blood_group: Mapped[str | None] = mapped_column(String(8))
    contact_phone: Mapped[str | None] = mapped_column(String(64))
    email: Mapped[str | None] = mapped_column(String(254))
    emergency_contact: Mapped[str | None] = mapped_column(String(200))
    preferred_language: Mapped[str] = mapped_column(String(2), default='en')
    external_ai_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=now)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=now, onupdate=now)

class LoginAttempt(Base):
    __tablename__ = 'login_attempts'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=now, index=True)

class AuthSession(Base):
    __tablename__ = 'sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP, index=True)

class Document(Base):
    __tablename__ = 'documents'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    patient_id: Mapped[str] = mapped_column(ForeignKey('patients.id'), index=True)
    original_filename: Mapped[str] = mapped_column(String(200))
    storage_path: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(64))
    file_size_bytes: Mapped[int] = mapped_column(Integer)
    document_type: Mapped[str] = mapped_column(String(32), default='other')
    document_date: Mapped[datetime | None] = mapped_column(Date)
    processing_status: Mapped[str] = mapped_column(String(32), default='queued')
    summary_status: Mapped[str] = mapped_column(String(32), default='not_requested')
    index_status: Mapped[str] = mapped_column(String(32), default='not_requested')
    error_message: Mapped[str | None] = mapped_column(Text)
    deleted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    approved_revision: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=now)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=now, onupdate=now)
    __table_args__ = (Index('ix_patient_document_created', 'patient_id', 'created_at'),)

class Extraction(Base):
    __tablename__ = 'extractions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    document_id: Mapped[str] = mapped_column(ForeignKey('documents.id', ondelete='CASCADE'))
    revision: Mapped[int] = mapped_column(Integer)
    raw_ocr_text: Mapped[str] = mapped_column(Text)
    pages: Mapped[list] = mapped_column(JSON, default=list)
    structured_candidate_data: Mapped[dict] = mapped_column(JSON)
    extraction_provider: Mapped[str] = mapped_column(String(64))
    provider_model: Mapped[str] = mapped_column(String(120))
    validation_status: Mapped[str] = mapped_column(String(32), default='needs_review')
    review_status: Mapped[str] = mapped_column(String(32), default='pending')
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=now)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=now, onupdate=now)
    __table_args__ = (UniqueConstraint('document_id', 'revision'),)

class Observation(Base):
    __tablename__ = 'observations'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    patient_id: Mapped[str] = mapped_column(ForeignKey('patients.id'), index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey('documents.id', ondelete='CASCADE'), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    candidate_id: Mapped[str] = mapped_column(String(64))
    display_name: Mapped[str] = mapped_column(String(200))
    value_numeric: Mapped[float | None] = mapped_column(Float)
    value_text: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(String(64))
    reference_low: Mapped[float | None] = mapped_column(Float)
    reference_high: Mapped[float | None] = mapped_column(Float)
    source_abnormal_flag: Mapped[str | None] = mapped_column(String(16))
    source_text: Mapped[str] = mapped_column(Text)
    effective_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    validation_status: Mapped[str] = mapped_column(String(32), default='validated')
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=now)
    __table_args__ = (UniqueConstraint('document_id', 'candidate_id'),)

class Medication(Base):
    __tablename__ = 'medications'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    patient_id: Mapped[str] = mapped_column(ForeignKey('patients.id'), index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey('documents.id', ondelete='CASCADE'), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    candidate_id: Mapped[str] = mapped_column(String(64))
    medication_name: Mapped[str] = mapped_column(String(200))
    generic_name: Mapped[str | None] = mapped_column(String(200))
    strength: Mapped[str | None] = mapped_column(String(80))
    dose_instructions: Mapped[str | None] = mapped_column(Text)
    route: Mapped[str | None] = mapped_column(String(80))
    frequency: Mapped[str | None] = mapped_column(String(120))
    duration: Mapped[str | None] = mapped_column(String(120))
    prescription_date: Mapped[datetime | None] = mapped_column(Date)
    medication_status: Mapped[str] = mapped_column(String(32), default='prescribed')
    review_status: Mapped[str] = mapped_column(String(32), default='confirmed')
    source_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=now)
    __table_args__ = (UniqueConstraint('document_id', 'candidate_id'),)

class Summary(Base):
    __tablename__ = 'summaries'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    document_id: Mapped[str] = mapped_column(ForeignKey('documents.id', ondelete='CASCADE'))
    revision: Mapped[int] = mapped_column(Integer)
    language: Mapped[str] = mapped_column(String(2))
    data: Mapped[dict] = mapped_column(JSON)
    provider_model: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=now)
    __table_args__ = (UniqueConstraint('document_id', 'revision', 'language'),)

class Job(Base):
    __tablename__ = 'jobs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    document_id: Mapped[str] = mapped_column(ForeignKey('documents.id'), index=True)
    kind: Mapped[str] = mapped_column(String(24))
    revision: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(24), default='queued', index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=now)
    lease_until: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    lease_token: Mapped[str | None] = mapped_column(String(36))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=now)

class Chunk(Base):
    __tablename__ = 'source_chunks'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    patient_id: Mapped[str] = mapped_column(ForeignKey('patients.id'), index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey('documents.id', ondelete='CASCADE'), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    page: Mapped[int | None] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    indexed: Mapped[bool] = mapped_column(Boolean, default=False)

class Conversation(Base):
    __tablename__ = 'conversations'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    patient_id: Mapped[str] = mapped_column(ForeignKey('patients.id'), index=True)
    title: Mapped[str] = mapped_column(String(160), default='Health records')
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=now)

class Message(Base):
    __tablename__ = 'messages'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    conversation_id: Mapped[str] = mapped_column(ForeignKey('conversations.id', ondelete='CASCADE'), index=True)
    role: Mapped[str] = mapped_column(String(16))
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=now)

class Audit(Base):
    __tablename__ = 'audit_events'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str | None] = mapped_column(String(36), index=True)
    action: Mapped[str] = mapped_column(String(64))
    resource_id: Mapped[str | None] = mapped_column(String(36))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=now)

class WorkerHeartbeat(Base):
    __tablename__ = 'worker_heartbeats'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    last_seen: Mapped[datetime] = mapped_column(TIMESTAMP, default=now)
