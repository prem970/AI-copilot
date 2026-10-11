"""Isolated browser-test server; never writes to the pilot database or storage."""
import asyncio
import os
from pathlib import Path

root=Path(__file__).resolve().parents[1]
runtime=root/'.runtime/e2e'
runtime.mkdir(parents=True,exist_ok=True)
os.environ.update(ENVIRONMENT='test', DATABASE_URL='sqlite:///'+str(runtime/'browser.db'), STORAGE_DIR=str(runtime/'files'),
    SARVAM_API_KEY='', LAYA_API_KEY='', GEMINI_API_KEY='',
    CORS_ORIGINS='http://127.0.0.1:5174,http://localhost:5174', COOKIE_SECURE='false')

from app.main import app
from app.db import Base, engine, transaction
from app.models import User, Patient
from app.security import hasher
from app.worker import main as worker

Base.metadata.drop_all(engine)
Base.metadata.create_all(engine)
with transaction() as db:
    user=User(email='browser@example.test',password_hash=hasher.hash('browser-test-password'))
    db.add(user); db.flush()
    db.add(Patient(user_id=user.id,full_name='Browser Test Patient',email=user.email))

@app.on_event('startup')
async def start():
    app.state.worker=asyncio.create_task(worker())

@app.on_event('shutdown')
async def stop():
    app.state.worker.cancel()
    try: await app.state.worker
    except asyncio.CancelledError: pass

if __name__=='__main__':
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=8010)
