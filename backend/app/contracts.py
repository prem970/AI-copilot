from datetime import date
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator

class LoginInput(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=200)

class RegisterInput(BaseModel):
    full_name: str = Field(min_length=1, max_length=160)
    email: str = Field(min_length=3, max_length=254, pattern=r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
    password: str = Field(min_length=12, max_length=200)
    confirm_password: str = Field(min_length=12, max_length=200)

    @field_validator('email', 'full_name', mode='before')
    @classmethod
    def normalize_identity(cls, value, info):
        if isinstance(value, str):
            value = value.strip()
            return value.lower() if info.field_name == 'email' else value
        return value

    @model_validator(mode='after')
    def matching_passwords(self):
        if self.password != self.confirm_password:
            raise ValueError('Passwords do not match')
        return self

class ProfileInput(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=160)
    date_of_birth: date | None = None
    gender: Literal['male', 'female', 'other', 'unknown'] | None = None
    blood_group: Literal['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'] | None = None
    contact_phone: str | None = Field(default=None, max_length=64)
    emergency_contact: str | None = Field(default=None, max_length=200)
    preferred_language: Literal['en', 'ta'] | None = None
    external_ai_consent: bool | None = None

class ObservationInput(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    id: str = Field(max_length=64)
    test_name: str = Field(min_length=1, max_length=200)
    value_numeric: float | None = None
    value_text: str | None = Field(default=None, max_length=1000)
    unit: str | None = Field(default=None, max_length=64)
    reference_low: float | None = None
    reference_high: float | None = None
    source_abnormal_flag: Literal['H', 'L', 'CRITICAL', 'NORMAL'] | None = None
    source_text: str = Field(min_length=1, max_length=10000)
    page: int | None = Field(default=None, ge=1)
    confidence: str = 'needs_review'
    validation_status: str = 'needs_review'

    @model_validator(mode='after')
    def valid_range(self):
        if self.reference_low is not None and self.reference_high is not None and self.reference_low > self.reference_high:
            raise ValueError('Reference low cannot exceed reference high')
        if self.value_numeric is not None:
            try:
                same = self.value_text is not None and float(self.value_text) == self.value_numeric
            except ValueError:
                same = False
            if not same:
                self.value_text = str(self.value_numeric)
        return self

class MedicationInput(BaseModel):
    id: str = Field(max_length=64)
    medication_name: str = Field(min_length=1, max_length=200)
    generic_name: str | None = Field(default=None, max_length=200)
    strength: str | None = Field(default=None, max_length=80)
    dose_instructions: str | None = Field(default=None, max_length=2000)
    route: str | None = Field(default=None, max_length=80)
    frequency: str | None = Field(default=None, max_length=120)
    duration: str | None = Field(default=None, max_length=120)
    prescription_date: date | None = None
    source_text: str = Field(min_length=1, max_length=10000)
    page: int | None = Field(default=None, ge=1)
    confidence: str = 'needs_review'
    validation_status: str = 'needs_review'

class Candidate(BaseModel):
    document_type: Literal['lab_report', 'prescription', 'discharge_summary', 'other'] = 'other'
    document_date: date | None = None
    healthcare_provider: str | None = None
    practitioner_name: str | None = None
    observations: list[ObservationInput] = Field(default_factory=list, max_length=1000)
    medications: list[MedicationInput] = Field(default_factory=list, max_length=1000)
    unreadable_segments: list[str] = Field(default_factory=list)

    @model_validator(mode='after')
    def unique_ids(self):
        for items in (self.observations, self.medications):
            if len({item.id for item in items}) != len(items):
                raise ValueError('Candidate identifiers must be unique')
        return self

class ExtractionEdit(BaseModel):
    revision: int = Field(ge=1)
    structured_candidate_data: Candidate

class Confirmation(BaseModel):
    revision: int = Field(ge=1)
    confirm_all: bool = False
    observation_ids: list[str] = Field(default_factory=list)
    medication_ids: list[str] = Field(default_factory=list)
    active_medications: list[str] = Field(default_factory=list)

class MedicationStatus(BaseModel):
    medication_status: Literal['prescribed', 'active', 'discontinued', 'completed']

class ConversationInput(BaseModel):
    title: str = Field(default='Health records', min_length=1, max_length=160)

class MessageInput(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    language: Literal['en', 'ta'] = 'en'
