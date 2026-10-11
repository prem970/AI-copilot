"""Durable leased jobs; safe across retries, concurrent workers and server restarts."""
import asyncio
import json
import logging
from datetime import timedelta
from sqlalchemy import select, update, or_
from qdrant_client import models as qm
from app.db import transaction
from app.core.config import settings
from app.models import Job, Document, Extraction, Chunk, Summary, Patient, User, WorkerHeartbeat, now, uid
from app.repository import enqueue
from app.storage import file_path
from app.ai import extract_document, embed, chat_json, translate, validate_answer, ProviderError
from app.rag import vector_client, COLLECTION, source_data

log = logging.getLogger(__name__)
WORKER_ID = uid()

def record_heartbeat(db):
    pulse = db.get(WorkerHeartbeat, WORKER_ID)
    if pulse:
        pulse.last_seen = now()
    else:
        db.add(WorkerHeartbeat(id=WORKER_ID))

def claim_job():
    with transaction() as db:
        record_heartbeat(db)
        query = select(Job).where(or_(
            (Job.status == 'queued') & (Job.available_at <= now()),
            (Job.status == 'running') & (Job.lease_until < now())))
        job = db.scalar(query.order_by(Job.created_at).with_for_update(skip_locked=True).limit(1))
        if job is None:
            return None
        job.status = 'running'
        job.attempts += 1
        job.lease_token = uid()
        job.lease_until = now() + timedelta(seconds=settings.job_lease_seconds)
        return job.id, job.lease_token

def snapshot(job_id, token):
    with transaction() as db:
        job = db.get(Job, job_id)
        if not job or job.lease_token != token or job.status != 'running':
            return None
        document = db.get(Document, job.document_id)
        if not document:
            return None
        if job.kind != 'cleanup' and (document.deleted_at or (job.kind != 'extract' and document.revision != job.revision)):
            job.status = 'cancelled'
            return None
        patient = db.get(Patient, document.patient_id)
        consent = patient.external_ai_consent and db.get(User, patient.user_id).enabled
        if job.kind == 'extract':
            document.processing_status = 'processing'
        if job.kind == 'summary':
            document.summary_status = 'processing'
        if job.kind == 'index':
            document.index_status = 'processing'
        from app.repository import serialize
        chunks = db.scalars(select(Chunk).where(Chunk.document_id == document.id, Chunk.revision == document.revision)).all()
        return dict(job=serialize(job), document=serialize(document), consent=consent,
            sources=[source_data(chunk, document) for chunk in chunks])

async def heartbeat(job_id, token, done):
    while not done.is_set():
        try:
            await asyncio.wait_for(done.wait(), timeout=30)
        except asyncio.TimeoutError:
            with transaction() as db:
                record_heartbeat(db)
                db.execute(update(Job).where(Job.id == job_id, Job.lease_token == token, Job.status == 'running').values(
                    lease_until=now()+timedelta(seconds=settings.job_lease_seconds)))

def index_sync(sources, vectors):
    client = vector_client()
    try:
        if not client.collection_exists(COLLECTION):
            try:
                client.create_collection(COLLECTION, vectors_config=qm.VectorParams(size=settings.embedding_dimensions, distance=qm.Distance.COSINE))
                client.create_payload_index(COLLECTION, 'patient_id', field_schema=qm.PayloadSchemaType.KEYWORD)
            except Exception:
                if not client.collection_exists(COLLECTION):
                    raise
        info = client.get_collection(COLLECTION)
        if info.config.params.vectors.size != settings.embedding_dimensions:
            raise ProviderError('Vector collection dimensions do not match the embedding API')
        points = [qm.PointStruct(id=s['id'], vector=v, payload={k:s[k] for k in ('patient_id', 'document_id', 'revision', 'page')}) for s,v in zip(sources, vectors)]
        if points:
            client.upsert(COLLECTION, points, wait=True)
    finally:
        client.close()

def cleanup_sync(document_id):
    # Local file deletion succeeds even when vector storage is temporarily unavailable.
    file_path(document_id).unlink(missing_ok=True)
    client = vector_client()
    try:
        if client.collection_exists(COLLECTION):
            client.delete(COLLECTION, points_selector=qm.FilterSelector(filter=qm.Filter(must=[
                qm.FieldCondition(key='document_id', match=qm.MatchValue(value=document_id))])), wait=True)
    finally:
        client.close()

async def perform(data):
    job, document = data['job'], data['document']
    def allowed_external():
        with transaction() as db:
            current = db.get(Document, document['id'])
            if not current or current.deleted_at or current.revision != document['revision']:
                return False
            patient = db.get(Patient, current.patient_id)
            return bool(patient.external_ai_consent and db.get(User, patient.user_id).enabled)
    if job['kind'] == 'extract':
        return await extract_document(file_path(document['id']).read_bytes(), document['original_filename'], document['mime_type'], data['consent'], allowed_external)
    if job['kind'] == 'cleanup':
        await asyncio.to_thread(cleanup_sync, document['id'])
        return {}
    if document['approved_revision'] != document['revision']:
        raise ProviderError('Document has not been approved')
    sources = data['sources']
    if job['kind'] == 'index':
        vectors = []
        for start in range(0, len(sources), 64):
            if not allowed_external():
                raise ProviderError('External AI consent is required for indexing')
            vectors.extend(await embed([s['text'] for s in sources[start:start+64]]))
        if not allowed_external():
            raise ProviderError('External processing consent or document access changed')
        for source in sources:
            source['patient_id'] = document['patient_id']
        await asyncio.to_thread(index_sync, sources, vectors)
        return {}
    if job['kind'] == 'summary':
        if not allowed_external():
            raise ProviderError('External AI consent is required for summaries')
        if not sources:
            raise ProviderError('No approved records to summarize')
        prompt = json.dumps({'task':'Summarize the reviewed findings in English. Use all supplied sources. No clinical inference or treatment advice.',
            'reviewed_sources':[{k:v for k,v in s.items() if k != 'excerpt'} for s in sources], 'note':'Reviewed fields supersede the original OCR when corrected.'}, ensure_ascii=False)
        claims = validate_answer(await chat_json(prompt), sources)
        used = {i for c in claims for i in c['source_ids']}
        citations = [{**s, 'url': '/api/v1/documents/'+s['document_id']+'/file'} for s in sources if s['id'] in used]
        english = {'overview': 'Reviewed document findings', 'key_findings': [c['text'] for c in claims], 'claims': claims,
            'citations': citations, 'safety_disclaimer': 'For understanding your records. Discuss diagnosis and treatment with your clinician.'}
        terms = []
        for source in sources:
            item = json.loads(source['text'])
            terms.extend(str(item[k]) for k in ('medication_name','generic_name','strength','unit') if item.get(k))
        try:
            tamil_claims = []
            for claim in claims:
                if not allowed_external():
                    raise ProviderError('External processing consent or document access changed')
                tamil_claims.append({'text': await translate(claim['text'], terms), 'source_ids':claim['source_ids']})
            tamil = {'overview': 'சரிபார்க்கப்பட்ட ஆவணத் தகவல்கள்', 'key_findings': [c['text'] for c in tamil_claims], 'claims': tamil_claims,
                'citations':citations, 'safety_disclaimer': 'நோயறிதல் மற்றும் சிகிச்சை குறித்து உங்கள் மருத்துவரிடம் ஆலோசிக்கவும்.'}
            return {'en':english, 'ta':tamil}
        except ProviderError:
            return {'en':english, 'translation_error':'Tamil translation failed validation. English summary is available; retry generation.'}
    raise ProviderError('Unknown job kind')

def save_result(job_id, token, data, output):
    with transaction() as db:
        job = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
        if not job or job.lease_token != token or job.status != 'running':
            return
        document = db.scalar(select(Document).where(Document.id == job.document_id).with_for_update())
        if job.kind != 'cleanup' and (document.deleted_at or document.revision != data['document']['revision']):
            job.status = 'cancelled'
            return
        if job.kind == 'extract':
            document.revision += 1
            db.add(Extraction(document_id=document.id, revision=document.revision, **output))
            candidate = output['structured_candidate_data']
            from datetime import date
            document.document_date = date.fromisoformat(candidate['document_date']) if candidate.get('document_date') else None
            document.document_type = candidate['document_type']
            document.processing_status = 'awaiting_review'
            document.error_message = None
        elif job.kind == 'index':
            patient = db.get(Patient, document.patient_id)
            if not patient.external_ai_consent or not db.get(User, patient.user_id).enabled:
                job.status = 'cancelled'
                document.index_status = 'consent_required'
                return
            document.index_status = 'completed'
            for chunk in db.scalars(select(Chunk).where(Chunk.document_id == document.id, Chunk.revision == document.revision)):
                chunk.indexed = True
        elif job.kind == 'summary':
            patient = db.get(Patient, document.patient_id)
            if not patient.external_ai_consent or not db.get(User, patient.user_id).enabled:
                job.status = 'cancelled'
                document.summary_status = 'consent_required'
                return
            for language in ('en', 'ta'):
                if language not in output:
                    continue
                summary = db.scalar(select(Summary).where(Summary.document_id == document.id, Summary.revision == document.revision, Summary.language == language))
                if summary:
                    summary.data = output[language]
                    summary.created_at = now()
                else:
                    db.add(Summary(document_id=document.id, revision=document.revision, language=language, data=output[language], provider_model=settings.summary_model))
            document.summary_status = 'translation_failed' if output.get('translation_error') else 'completed'
        job.status = 'completed'
        job.lease_until = None
        job.error = None

def fail_job(job_id, token, error):
    # Never store provider payloads, keys or raw medical content in error messages/logs.
    message = str(error) if isinstance(error, ProviderError) else 'Processing service failed. Check configuration and retry.'
    with transaction() as db:
        job = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
        if not job or job.lease_token != token or job.status != 'running':
            return
        job.error = message
        retry = job.attempts < settings.max_job_attempts
        job.status = 'queued' if retry else 'failed'
        job.available_at = now() + timedelta(seconds=min(60, 5 * 2**job.attempts))
        job.lease_until = None
        document = db.get(Document, job.document_id)
        if document and not document.deleted_at and document.revision == job.revision:
            if job.kind == 'extract':
                document.processing_status = 'queued' if retry else 'failed'
                document.error_message = message
            elif job.kind == 'summary':
                document.summary_status = 'queued' if retry else 'failed'
            elif job.kind == 'index':
                document.index_status = 'queued' if retry else 'failed'
    log.warning('Job %s failed (%s)', job_id, type(error).__name__)

async def run_job(job_id, token):
    done = asyncio.Event()
    pulse = asyncio.create_task(heartbeat(job_id, token, done))
    try:
        data = snapshot(job_id, token)
        if data:
            output = await perform(data)
            save_result(job_id, token, data, output)
    except Exception as exc:
        fail_job(job_id, token, exc)
    finally:
        done.set()
        await pulse

async def main():
    logging.basicConfig(level=logging.INFO)
    while True:
        try:
            job = claim_job()
            if job:
                await run_job(*job)
            else:
                await asyncio.sleep(2)
        except Exception as exc:
            log.error('Worker unavailable (%s)', type(exc).__name__)
            await asyncio.sleep(5)

if __name__ == '__main__':
    asyncio.run(main())
