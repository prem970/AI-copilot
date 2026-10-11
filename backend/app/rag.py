import json
import hashlib
import re
from sqlalchemy import select
from qdrant_client import QdrantClient, models as qm
from app.core.config import settings
from app.models import Chunk, Document, Patient, User
from app.repository import confirmed_query
from app.ai import decide, embed, chat_json, translate, validate_answer, ProviderError

# Provider/model/dimension changes cannot search incompatible old vectors.
COLLECTION = 'reviewed_health_api_' + hashlib.sha256(
    f'gemini-retrieval-v1|{settings.gemini_base_url}|{settings.embedding_model}|{settings.embedding_dimensions}'.encode()).hexdigest()[:16]

def vector_client():
    return QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None, timeout=20)

def source_data(chunk, doc):
    fields = json.loads(chunk.text)
    excerpt = fields.pop('source_text', '')
    fields.pop('id', None)
    return {'id': chunk.id, 'document_id': doc.id, 'revision': chunk.revision, 'page': chunk.page,
        'filename': doc.original_filename, 'text': json.dumps(fields, ensure_ascii=False), 'excerpt': excerpt}

def current_chunks(db, patient_id):
    return select(Chunk, Document).join(Document, Document.id == Chunk.document_id).where(
        Chunk.patient_id == patient_id, Document.patient_id == patient_id, Document.deleted_at.is_(None),
        Document.revision == Chunk.revision, Document.approved_revision == Chunk.revision)

def probability(answer):
    choice = answer.get('choice')
    return float(answer.get('probabilities', {}).get(choice, answer.get('answer_confidence', 0)))

async def answer(db, patient, question, language):
    patient_id = patient.id
    def check_external(sources=()):
        # End any MySQL repeatable-read snapshot before checking current consent/access.
        db.rollback()
        db.expire_all()
        fresh = db.get(Patient, patient_id)
        if not fresh or not fresh.external_ai_consent or not db.get(User, fresh.user_id).enabled:
            raise ProviderError('External AI consent or account access changed')
        if sources:
            valid = {chunk.id for chunk, _doc in db.execute(current_chunks(db, patient_id).where(Chunk.id.in_([s['id'] for s in sources])))}
            if any(s['id'] not in valid for s in sources):
                raise ProviderError('Source records changed. Ask again.')
        db.rollback()
    if len(question) > 1000:
        return {'status': 'clarification_needed', 'answer': 'Please ask a shorter, specific question about your records.', 'language': language, 'citations': []}
    check_external()
    routing = await decide(question, {'route': {'type': 'choice', 'instructions': 'Which source can answer this question about reviewed records?',
        'criteria': {'records': 'Exact test results, dates, or prescribed medicines', 'trends': 'Changes in test results over time',
            'narrative': 'Explain or summarize information in uploaded records', 'unsupported': 'Diagnosis, treatment changes, or information outside uploaded records'}}})
    decision = routing['answers'].get('route', {})
    route = decision.get('choice')
    if probability(decision) < 0.6 or route not in ('records', 'trends', 'narrative'):
        return {'status': 'clarification_needed', 'answer': 'Ask about a specific result, medicine, or change shown in your reviewed records.', 'language': language, 'citations': [], 'decision_model': routing.get('routing')}
    # Finish the current SQL snapshot before external work; subsequent source checks see fresh state.
    if route in ('records', 'trends'):
        # Exact clinical values come from reviewed SQL rows, never reconstructed by the model.
        rows = db.execute(current_chunks(db, patient.id).order_by(Document.document_date.desc(), Document.created_at.desc()).limit(100)).all()
        sources = [source_data(chunk, doc) for chunk, doc in rows]
        terms = [term.casefold() for term in re.findall(r'[\w]+', question) if len(term) > 2]
        sources.sort(key=lambda s: sum(term in s['text'].casefold() for term in terms), reverse=True)
        sources = sources[:12]
    else:
        check_external()
        vector = (await embed([question], query=True))[0]
        client = vector_client()
        try:
            result = client.query_points(collection_name=COLLECTION, query=vector, limit=12,
                query_filter=qm.Filter(must=[qm.FieldCondition(key='patient_id', match=qm.MatchValue(value=patient.id))]))
            ids = [str(p.id) for p in result.points]
            rows = db.execute(current_chunks(db, patient.id).where(Chunk.id.in_(ids))).all() if ids else []
            by_id = {chunk.id: source_data(chunk, doc) for chunk, doc in rows}
            sources = [by_id[i] for i in ids if i in by_id]
        except Exception as exc:
            raise ProviderError('Record search is unavailable. Verify indexing status and Qdrant.') from exc
        finally:
            client.close()
    db.rollback()
    if not sources:
        return {'status': 'insufficient_evidence', 'answer': 'No reviewed evidence is available for this question. Upload and confirm relevant records first.', 'language': language, 'citations': []}
    relevant = []
    for source in sources:
        # Evaluate short passages individually instead of overfilling the Laya context.
        check_external([source])
        state = json.dumps({'question': question[:500], 'evidence': source['text'][:900]}, ensure_ascii=False)
        scored = await decide(state, {'relevant': {'type': 'noul', 'instructions': 'Does this evidence contain facts relevant to answering the question?'}})
        if float(scored['answers'].get('relevant', {}).get('noul', 0)) >= 0.7:
            relevant.append(source)
        if len(relevant) == 6:
            break
    if not relevant:
        return {'status': 'insufficient_evidence', 'answer': 'Your reviewed records do not contain enough relevant evidence to answer this question.', 'language': language, 'citations': []}
    check_external(relevant)
    prompt = json.dumps({'question': question, 'reviewed_sources': [{k:v for k,v in s.items() if k != 'excerpt'} for s in relevant],
        'note': 'Reviewed field values are authoritative; source_text is the original excerpt and may differ after user correction.'}, ensure_ascii=False)
    claims = validate_answer(await chat_json(prompt), relevant)
    by_id = {s['id']: s for s in relevant}
    for claim in claims:
        check_external([by_id[i] for i in claim['source_ids']])
        cited = '\n'.join(by_id[i]['text'] for i in claim['source_ids'])
        gate = await decide(json.dumps({'finding': claim['text'], 'reviewed_evidence': cited}, ensure_ascii=False),
            {'supported': {'type': 'choice', 'instructions': 'Is every factual claim directly supported by the reviewed evidence without diagnosing or changing treatment?',
                'criteria': {'answer': 'All claims are supported by the supplied evidence', 'abstain': 'One or more claims are missing evidence, diagnose, or change treatment'}}})
        support = gate['answers'].get('supported', {})
        if support.get('choice') != 'answer' or probability(support) < 0.6:
            return {'status': 'insufficient_evidence', 'answer': 'I cannot provide a sufficiently supported answer. Review this question with your clinician.', 'language': language, 'citations': []}
    if language == 'ta':
        terms = []
        for source in relevant:
            item = json.loads(source['text'])
            terms.extend(str(item[k]) for k in ('medication_name', 'generic_name', 'strength', 'unit') if item.get(k))
        for claim in claims:
            check_external([by_id[i] for i in claim['source_ids']])
            claim['text'] = await translate(claim['text'], terms)
    used = {i for claim in claims for i in claim['source_ids']}
    citations = [{**source, 'url': '/api/v1/documents/'+source['document_id']+'/file'} for source in relevant if source['id'] in used]
    return {'status': 'answered', 'language': language, 'answer': '\n\n'.join(c['text'] for c in claims), 'claims': claims,
        'citations': citations, 'provider_model': settings.summary_model, 'decision_model': routing.get('routing'),
        'safety_disclaimer': 'For understanding your records. Discuss diagnosis and treatment with your clinician.'}
