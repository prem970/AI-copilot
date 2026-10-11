from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text, select
from sqlalchemy.exc import SQLAlchemyError
from app.core.config import settings
from app.db import engine
from app.api.pilot import router
from app.models import WorkerHeartbeat, now
from app.db import SessionLocal
from datetime import timedelta

if '*' in settings.origins:
    raise RuntimeError('Wildcard CORS is not allowed')
if settings.environment == 'production' and not settings.cookie_secure:
    raise RuntimeError('COOKIE_SECURE must be true in production')
if not settings.database_url.startswith('mysql') and settings.environment != 'test':
    raise RuntimeError('Runtime requires MySQL; SQLite is supported only for isolated tests')

app = FastAPI(title='Personal Health Copilot', version='2.0.0')
app.add_middleware(CORSMiddleware, allow_origins=settings.origins, allow_credentials=True,
    allow_methods=['GET', 'POST', 'PATCH', 'DELETE'], allow_headers=['Content-Type', 'X-CSRF-Token'])
app.include_router(router)

@app.middleware('http')
async def privacy_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['X-Frame-Options'] = 'DENY'
    return response

@app.exception_handler(SQLAlchemyError)
async def database_error(request, exc):
    return JSONResponse(status_code=503, content={'detail': 'Database unavailable. Verify MySQL and migrations.'})

@app.get('/health')
def health():
    return {'status': 'alive', 'version': '2.0.0'}

@app.get('/ready')
def ready():
    try:
        with engine.connect() as connection:
            connection.execute(text('SELECT 1 FROM users LIMIT 1'))
        with SessionLocal() as db:
            worker = db.scalar(select(WorkerHeartbeat).where(WorkerHeartbeat.last_seen > now()-timedelta(seconds=90)))
        data = {'status': 'ready' if worker else 'degraded', 'database': 'mysql',
            'worker': 'ready' if worker else 'unavailable', 'sarvam_configured': bool(settings.sarvam_api_key),
            'laya_configured': bool(settings.laya_api_key), 'embedding_configured': bool(settings.gemini_api_key),
            'embedding_provider': 'gemini'}
        return data if worker else JSONResponse(status_code=503, content=data)
    except SQLAlchemyError:
        return JSONResponse(status_code=503, content={'status': 'unavailable', 'database': 'unavailable'})
