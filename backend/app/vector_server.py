"""Portable Qdrant service for local Windows use, backed by the real Qdrant local engine.

Docker deployments use the official Qdrant server. This service implements only
the REST operations used by this application, and serializes local-engine access.
"""
import secrets
import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI, Header, HTTPException, Depends
from qdrant_client import QdrantClient, models as qm
from app.core.config import ROOT, settings

state = {}
lock = threading.Lock()

def authorize(api_key: str = Header('', alias='api-key')):
    if not settings.qdrant_api_key or not secrets.compare_digest(api_key, settings.qdrant_api_key):
        raise HTTPException(401, 'Vector service key required')

@asynccontextmanager
async def lifespan(app):
    if not settings.qdrant_api_key:
        raise RuntimeError('Configure QDRANT_API_KEY for the portable vector service')
    state['client'] = QdrantClient(path=str(ROOT/'data/qdrant'))
    yield
    state['client'].close()

app = FastAPI(lifespan=lifespan)

def result(value):
    return {'result': value, 'status': 'ok', 'time': 0.0}

@app.get('/')
def version():
    return {'title': 'qdrant-local', 'version': '1.19.1'}

@app.get('/healthz')
def health():
    return {'status': 'ready'}

@app.get('/collections/{name}/exists', dependencies=[Depends(authorize)])
def exists(name: str):
    with lock:
        return result({'exists': state['client'].collection_exists(name)})

@app.put('/collections/{name}', dependencies=[Depends(authorize)])
def create(name: str, payload: dict):
    with lock:
        state['client'].create_collection(name, vectors_config=qm.VectorParams.model_validate(payload['vectors']))
    return result(True)

@app.get('/collections/{name}', dependencies=[Depends(authorize)])
def collection_info(name: str):
    with lock:
        return result(state['client'].get_collection(name).model_dump(mode='json'))

@app.put('/collections/{name}/index', dependencies=[Depends(authorize)])
def index(name: str, payload: dict):
    # Local Qdrant evaluates payload filters directly; no server-side payload index is needed.
    return result({'operation_id': 0, 'status': 'completed'})

@app.delete('/collections/{name}', dependencies=[Depends(authorize)])
def remove_collection(name: str):
    with lock:
        return result(state['client'].delete_collection(name))

@app.put('/collections/{name}/points', dependencies=[Depends(authorize)])
def upsert(name: str, payload: dict):
    points = [qm.PointStruct.model_validate(point) for point in payload['points']]
    with lock:
        state['client'].upsert(name, points, wait=True)
    return result({'operation_id': 0, 'status': 'completed'})

@app.post('/collections/{name}/points/query', dependencies=[Depends(authorize)])
def query(name: str, payload: dict):
    filters = qm.Filter.model_validate(payload['filter']) if payload.get('filter') else None
    with lock:
        vector_query = qm.NearestQuery.model_validate(payload['query']) if isinstance(payload['query'], dict) else payload['query']
        response = state['client'].query_points(name, query=vector_query, query_filter=filters,
            limit=payload.get('limit', 10), with_payload=payload.get('with_payload', True))
    return result(response.model_dump(mode='json'))

@app.post('/collections/{name}/points/delete', dependencies=[Depends(authorize)])
def delete(name: str, payload: dict):
    selector = qm.FilterSelector(filter=qm.Filter.model_validate(payload['filter'])) if payload.get('filter') else qm.PointIdsList(points=payload['points'])
    with lock:
        state['client'].delete(name, points_selector=selector, wait=True)
    return result({'operation_id': 0, 'status': 'completed'})
