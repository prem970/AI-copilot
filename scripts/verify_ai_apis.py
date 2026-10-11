"""Explicit live API smoke; sends synthetic text only unless --ocr-file is supplied.

This uses provider credits. It verifies integration, not clinical accuracy.
"""
import argparse
import asyncio
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.ai import decide, embed, chat_json, translate, validate_answer, extract_document, ProviderError
from app.core.config import settings

async def main(ocr_file):
    missing = [name for name in ('laya_api_key', 'gemini_api_key', 'sarvam_api_key') if not getattr(settings, name).strip()]
    if missing:
        raise ProviderError('Set these backend .env keys first: ' + ', '.join(name.upper() for name in missing))
    questions = {'route': {'type': 'choice', 'instructions': 'Choose the source for the question.',
        'criteria': {'records': 'A specific reviewed record', 'unsupported': 'Outside reviewed records'}}}
    for question in ('What does my reviewed record say?', 'எனது சரிபார்க்கப்பட்ட அறிக்கை என்ன கூறுகிறது?'):
        await decide(question, questions)
    vectors = await embed(['Synthetic integration test in English', 'செயற்கை ஒருங்கிணைப்பு சோதனை'])
    await embed(['Synthetic retrieval question?'], query=True)
    sources = [{'id': 'integration-source', 'text': 'Synthetic test record: glucose 100 mg/dL.'}]
    claims = validate_answer(await chat_json(json.dumps({'question': 'Repeat the synthetic test value.', 'reviewed_sources': sources})), sources)
    for claim in claims:
        await translate(claim['text'], ['mg/dL'])
    if ocr_file:
        path = Path(ocr_file)
        mimes = {'.pdf': 'application/pdf', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg'}
        if path.suffix.lower() not in mimes or path.stat().st_size > 15 * 1024 * 1024:
            raise ProviderError('OCR smoke accepts PDF/PNG/JPEG up to 15 MB')
        # Running with this flag explicitly authorizes sending the supplied file to Sarvam.
        await extract_document(path.read_bytes(), path.name, mimes[path.suffix.lower()], True)
    print(json.dumps({'laya': 'live English/Tamil decisions validated', 'embeddings': len(vectors),
        'embedding_provider': 'gemini', 'dimensions': settings.embedding_dimensions,
        'sarvam': 'live cited generation and Tamil translation validated',
        'document_extraction': 'checked' if ocr_file else 'not requested'}, indent=2))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ocr-file', help='Optional real PDF/image to send for the document-extraction smoke')
    args = parser.parse_args()
    try:
        asyncio.run(main(args.ocr_file))
    except ProviderError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
