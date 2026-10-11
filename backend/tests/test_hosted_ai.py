"""Provider protocol tests use HTTP fixtures, never paid APIs or patient data."""
import asyncio
import json
import httpx
import pytest
from app import ai
from app.ai import ProviderError
from app.core.config import settings

QUESTIONS = {'route': {'type': 'choice', 'instructions': 'Select a source',
    'criteria': {'records': 'Reviewed records', 'unsupported': 'No evidence'}}}

def configure(monkeypatch, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr(settings, 'laya_api_key', 'fixture-laya-key')
    monkeypatch.setattr(settings, 'laya_base_url', 'https://laya-model.com')
    monkeypatch.setattr(settings, 'laya_model', 'multilingual')
    monkeypatch.setattr(settings, 'gemini_api_key', 'fixture-gemini-key')
    monkeypatch.setattr(settings, 'gemini_base_url', 'https://generativelanguage.googleapis.com/v1beta')
    monkeypatch.setattr(settings, 'embedding_model', 'gemini-embedding-001')
    monkeypatch.setattr(settings, 'embedding_dimensions', 3)
    monkeypatch.setattr(ai.httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))

def test_laya_key_and_multilingual_body_without_optional_routing(monkeypatch):
    def handler(request):
        assert str(request.url) == 'https://laya-model.com/v1/decide'
        assert request.headers['Authorization'] == 'Bearer fixture-laya-key'
        body = json.loads(request.content)
        assert body['model'] == 'multilingual' and body['questions'] == QUESTIONS
        return httpx.Response(200, json={'answers': {'route': {'choice': 'records',
            'probabilities': {'records': .9, 'unsupported': .1}}}})
    configure(monkeypatch, handler)
    result = asyncio.run(ai.decide('எனது முடிவு?', QUESTIONS))
    assert result['answers']['route']['choice'] == 'records'
    assert result['routing']['model'] == 'multilingual'

@pytest.mark.parametrize('response', [
    [], {'answers': {}},
    {'demo': True, 'answers': {}},
    {'answers': {'route': {'choice': 'unknown', 'probabilities': {'records': .9, 'unsupported': .1}}}},
    {'answers': {'route': {'choice': 'records', 'probabilities': {'records': .9}}}},
    {'answers': {'route': {'choice': 'records', 'probabilities': {'records': 2, 'unsupported': -1}}}},
    {'answers': {'route': {'choice': 'records', 'probabilities': {'records': '0.9', 'unsupported': .1}}}},
])
def test_laya_rejects_invalid_or_demo_decisions(monkeypatch, response):
    configure(monkeypatch, lambda request: httpx.Response(200, json=response))
    with pytest.raises(ProviderError):
        asyncio.run(ai.decide('Question', QUESTIONS))

@pytest.mark.parametrize('value', [True, '0.9', -1, 2, None])
def test_laya_relevance_requires_numeric_probability(monkeypatch, value):
    configure(monkeypatch, lambda request: httpx.Response(200, json={'answers': {'relevant': {'noul': value}}}))
    with pytest.raises(ProviderError):
        asyncio.run(ai.decide('Evidence', {'relevant': {'type': 'noul', 'instructions': 'Relevant?'}}))

@pytest.mark.parametrize('status', [401, 402, 429, 503, 504])
def test_provider_failures_never_expose_response_or_credentials(monkeypatch, status):
    configure(monkeypatch, lambda request: httpx.Response(status, text='private provider payload fixture-laya-key'))
    with pytest.raises(ProviderError) as exc:
        asyncio.run(ai.decide('Question', QUESTIONS))
    assert 'private' not in str(exc.value) and 'fixture-laya-key' not in str(exc.value)

@pytest.mark.parametrize('query', [False, True])
def test_gemini_embeddings_authenticate_and_preserve_batch_order(monkeypatch, query):
    def handler(request):
        assert str(request.url) == 'https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:batchEmbedContents'
        assert request.headers['x-goog-api-key'] == 'fixture-gemini-key'
        assert 'Authorization' not in request.headers and not request.url.query
        assert json.loads(request.content) == {'requests': [{'model': 'models/gemini-embedding-001',
            'content': {'parts': [{'text': text}]}, 'taskType': 'RETRIEVAL_QUERY' if query else 'RETRIEVAL_DOCUMENT',
            'outputDimensionality': 3} for text in ['first', 'second']]}
        return httpx.Response(200, json={'embeddings': [{'values': [2, 0, 0]}, {'values': [0, 4, 0]}]})
    configure(monkeypatch, handler)
    assert asyncio.run(ai.embed(['first', 'second'], query=query)) == [[1, 0, 0], [0, 1, 0]]

@pytest.mark.parametrize('data', [[], [{'values': [1, 0]}],
    [{'values': [0, 0, 0]}], [{'wrong_field': [1, 0, 0]}],
    [{'values': [True, 0, 0]}], [{'values': ['1', 0, 0]}], [None]])
def test_embeddings_reject_invalid_vectors(monkeypatch, data):
    configure(monkeypatch, lambda request: httpx.Response(200, json={'embeddings': data}))
    with pytest.raises(ProviderError):
        asyncio.run(ai.embed(['evidence']))

def test_nonfinite_vectors_fail_closed(monkeypatch):
    configure(monkeypatch, lambda request: httpx.Response(200, content=b'{"embeddings":[{"values":[NaN,1,0]}]}'))
    with pytest.raises(ProviderError):
        asyncio.run(ai.embed(['evidence']))

@pytest.mark.parametrize('name,call', [('laya_api_key', lambda: ai.decide('question', QUESTIONS)),
    ('gemini_api_key', lambda: ai.embed(['evidence']))])
def test_missing_keys_make_no_request(monkeypatch, name, call):
    def forbidden(request):
        raise AssertionError('No anonymous API requests are allowed')
    configure(monkeypatch, forbidden)
    monkeypatch.setattr(settings, name, '')
    with pytest.raises(ProviderError, match='key is not configured'):
        asyncio.run(call())

def test_api_key_is_not_sent_to_insecure_embedding_url(monkeypatch):
    configure(monkeypatch, lambda request: pytest.fail('Key leaked to an insecure URL'))
    monkeypatch.setattr(settings, 'gemini_base_url', 'http://example.test/v1beta')
    with pytest.raises(ProviderError, match='HTTPS'):
        asyncio.run(ai.embed(['evidence']))

@pytest.mark.parametrize('scale', [1, 1e-300, 1e300])
def test_gemini_reduced_dimension_embeddings_are_normalized(monkeypatch, scale):
    configure(monkeypatch, lambda request: httpx.Response(200, json={'embeddings': [{'values': [3*scale, 4*scale, 0]}]}))
    vector = asyncio.run(ai.embed(['evidence']))[0]
    assert vector == pytest.approx([.6, .8, 0])

@pytest.mark.parametrize('status', [400, 403, 429, 503])
def test_gemini_failures_do_not_expose_keys_or_provider_payloads(monkeypatch, status):
    configure(monkeypatch, lambda request: httpx.Response(status, text='private fixture-gemini-key'))
    with pytest.raises(ProviderError) as exc:
        asyncio.run(ai.embed(['evidence']))
    assert 'Gemini' in str(exc.value) and 'private' not in str(exc.value) and 'fixture-gemini-key' not in str(exc.value)

@pytest.mark.parametrize('response', [[], {'choices': []}, {'choices': [{'message': {'content': None}}]}])
def test_sarvam_malformed_answers_are_explicit_failures(monkeypatch, response):
    configure(monkeypatch, lambda request: httpx.Response(200, json=response))
    monkeypatch.setattr(settings, 'sarvam_api_key', 'fixture-sarvam-key')
    with pytest.raises(ProviderError):
        asyncio.run(ai.chat_json('Synthetic test prompt'))

@pytest.mark.parametrize('translated', [None, '', 123])
def test_sarvam_invalid_translation_is_an_explicit_failure(monkeypatch, translated):
    configure(monkeypatch, lambda request: httpx.Response(200, json={'translated_text': translated}))
    monkeypatch.setattr(settings, 'sarvam_api_key', 'fixture-sarvam-key')
    with pytest.raises(ProviderError):
        asyncio.run(ai.translate('Synthetic test text'))
