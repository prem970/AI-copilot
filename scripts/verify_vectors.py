"""Verify real Qdrant filtering and persistence using a disposable collection."""
from uuid import uuid4
from qdrant_client import models as qm
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'backend'))
from app.rag import vector_client
from app.core.config import settings
from app import worker

client=vector_client()
name='health_copilot_verify'
try:
    if client.collection_exists(name):
        client.delete_collection(name)
    identifiers=[str(uuid4()),str(uuid4())]
    vector=[1.0]+[0.0]*(settings.embedding_dimensions-1)
    # Exercise the actual indexing writer using synthetic vectors in a disposable collection.
    worker.COLLECTION = name
    worker.index_sync([{'id': identifier, 'patient_id': patient, 'document_id': 'verification', 'revision': 1, 'page': 1}
        for identifier, patient in zip(identifiers, ['one','two'])], [vector, vector])
    assert client.get_collection(name).config.params.vectors.size == settings.embedding_dimensions
    result=client.query_points(name,query=vector,query_filter=qm.Filter(must=[qm.FieldCondition(key='patient_id',match=qm.MatchValue(value='one'))]))
    assert [str(point.id) for point in result.points]==[identifiers[0]]
    client.delete(name,points_selector=qm.FilterSelector(filter=qm.Filter(must=[qm.FieldCondition(key='document_id',match=qm.MatchValue(value='verification'))])),wait=True)
    assert not client.query_points(name,query=vector).points
    print(f'Real Qdrant indexing/filter/query/delete checks passed ({settings.embedding_dimensions} dimensions).')
finally:
    client.delete_collection(name)
    client.close()
