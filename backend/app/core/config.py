from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ROOT / '.env'), extra='ignore')
    environment: str = 'development'
    database_url: str = 'mysql+pymysql://health:health@127.0.0.1:3306/health_copilot'
    storage_dir: Path = ROOT / 'data' / 'storage'
    cors_origins: str = 'http://localhost:5173,http://127.0.0.1:5173'
    session_hours: int = 24
    cookie_secure: bool = False
    sarvam_api_key: str = ''
    sarvam_base_url: str = 'https://api.sarvam.ai'
    summary_model: str = 'sarvam-105b'
    qdrant_url: str = 'http://127.0.0.1:6333'
    qdrant_api_key: str = ''
    laya_api_key: str = ''
    laya_base_url: str = 'https://laya-model.com'
    laya_model: str = 'multilingual'
    gemini_api_key: str = ''
    gemini_base_url: str = 'https://generativelanguage.googleapis.com/v1beta'
    embedding_model: str = 'gemini-embedding-001'
    embedding_dimensions: int = 1536
    job_lease_seconds: int = 600
    max_job_attempts: int = 3

    @property
    def origins(self):
        return [s.strip() for s in self.cors_origins.split(',') if s.strip()]

settings = Settings()
