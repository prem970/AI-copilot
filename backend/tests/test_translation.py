import asyncio
import httpx
import pytest
from app import ai
from app.ai import ProviderError
from app.core.config import settings

def transport(monkeypatch, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr(settings,'sarvam_api_key','test-only-key')
    monkeypatch.setattr(ai.httpx,'AsyncClient',lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))

def test_translation_protects_drug_and_unit_and_keeps_numbers(monkeypatch):
    import json
    def handler(request):
        payload = json.loads(request.content)
        assert payload['target_language_code'] == 'ta-IN'
        assert request.headers['api-subscription-key'] == 'test-only-key'
        return httpx.Response(200,json={'translated_text':payload['input'].replace('was','இருந்தது')})
    transport(monkeypatch,handler)
    result = asyncio.run(ai.translate('ExampleDrug was 5 mg.', ['ExampleDrug','mg']))
    assert 'ExampleDrug' in result and '5 mg' in result

def test_translation_rejects_changed_clinical_value(monkeypatch):
    transport(monkeypatch,lambda request:httpx.Response(200,json={'translated_text':'Glucose was 139 mg/dL.'}))
    with pytest.raises(ProviderError):
        asyncio.run(ai.translate('Glucose was 138 mg/dL.'))

def test_translation_rejects_lost_protected_drug_name(monkeypatch):
    transport(monkeypatch,lambda request:httpx.Response(200,json={'translated_text':'Medicine was 5 mg.'}))
    with pytest.raises(ProviderError):
        asyncio.run(ai.translate('ExampleDrug was 5 mg.', ['ExampleDrug']))
