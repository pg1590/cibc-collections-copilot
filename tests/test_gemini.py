"""Provider failures or fabricated evidence must not become application facts."""
import json

import httpx
import pytest

from app.gemini import GeminiClient, ProviderUnavailable


def response(value, status=200):
    return httpx.Response(status, json={'status': 'completed', 'model': 'gemini-3.8-flash',
        'steps': [{'type': 'model_output', 'content': [{'type': 'text', 'text': json.dumps(value)}]}]})


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY', 'test-key-only')
    monkeypatch.setenv('COPILOT_GEMINI_ENABLED', '1')
    monkeypatch.setenv('COPILOT_GEMINI_MODEL', 'gemini-3.8-flash')
    monkeypatch.setenv('COPILOT_GEMINI_MAX_CALLS', '60')


def test_disabled_provider_makes_no_request(configured, monkeypatch):
    monkeypatch.setenv('COPILOT_GEMINI_ENABLED', '0')
    def forbidden(_):
        raise AssertionError('A disabled provider must not call the network')
    client = GeminiClient(httpx.MockTransport(forbidden))
    with pytest.raises(ProviderUnavailable):
        client.plan('question', {})
    assert not client.configured


def test_stateless_request_and_exact_evidence_cache(configured):
    calls = []
    def send(request):
        calls.append(request)
        body = json.loads(request.content)
        assert body['store'] is False
        assert 'tools' not in body
        assert 'test-key-only' not in request.url.query.decode()
        return response({'items': [{'source_id': 'policy-v2', 'quote': 'Grace period: Two business days.', 'label': 'Policy'}]})
    client = GeminiClient(httpx.MockTransport(send))
    args = ('policy', {'policy-v2': 'Grace period: Two business days.'})
    assert client.summarise(*args)['source_ids'] == ['policy-v2']
    assert client.summarise(*args)['generation']['status'] == 'generated'
    assert len(calls) == 1


@pytest.mark.parametrize('item', [
    {'source_id': 'missing-source', 'quote': 'Two business days.', 'label': 'Policy'},
    {'source_id': 'policy-v2', 'quote': 'Five business days.', 'label': 'Policy'},
    {'source_id': 'policy-v2', 'quote': 'Two business days.', 'label': {'invalid': True}},
])
def test_invented_citation_or_fact_is_rejected(configured, item):
    client = GeminiClient(httpx.MockTransport(lambda _: response({'items': [item]})))
    with pytest.raises(ProviderUnavailable):
        client.summarise('policy', {'policy-v2': 'Two business days.'})


def test_quota_failure_does_not_retry_or_expose_provider_response(configured):
    calls = []
    def send(request):
        calls.append(request)
        return httpx.Response(429, text='private backend error including test-key-only')
    client = GeminiClient(httpx.MockTransport(send))
    for _ in range(2):
        with pytest.raises(ProviderUnavailable) as error:
            client.plan('question', {})
        assert 'test-key-only' not in str(error.value)
    assert len(calls) == 1


def test_request_budget_limits_provider_calls(configured, monkeypatch):
    monkeypatch.setenv('COPILOT_GEMINI_MAX_CALLS', '1')
    plan = {'metric_id': 'open_cases', 'grouping': None, 'start_date': None, 'end_date': None,
            'filters': {}, 'clarification': None, 'refuse': False, 'refuse_reason': None}
    client = GeminiClient(httpx.MockTransport(lambda _: response(plan)))
    assert client.plan('first question', {})['metric_id'] == 'open_cases'
    with pytest.raises(ProviderUnavailable):
        client.plan('different question', {})


def test_provider_sql_is_not_accepted_as_a_plan(configured):
    client = GeminiClient(httpx.MockTransport(lambda _: response({'sql': 'SELECT * FROM curated.customers'})))
    with pytest.raises(ProviderUnavailable):
        client.plan('question', {})
    assert client.trace_metadata()['stages']['plan'] == 'fallback'


@pytest.mark.parametrize('province', [None, [], {}, 1, 'ZZ', "ON' OR 1=1 --"])
def test_invalid_provider_province_uses_safe_fallback(configured, province):
    plan = {'metric_id': 'open_cases', 'grouping': 'none', 'start_date': '2026-09-28', 'end_date': '2026-09-29',
            'filters': {'province': province}, 'clarification': None, 'refuse': False, 'refuse_reason': None}
    client = GeminiClient(httpx.MockTransport(lambda _: response(plan)))
    with pytest.raises(ProviderUnavailable):
        client.plan('Open cases in Ontario', {})


def test_read_timeout_becomes_safe_fallback(configured):
    def send(request):
        raise httpx.ReadTimeout('sensitive transport details', request=request)
    client = GeminiClient(httpx.MockTransport(send))
    with pytest.raises(ProviderUnavailable) as error:
        client.plan('question', {})
    assert 'sensitive' not in str(error.value)


def test_enabled_without_key_makes_no_network_call(monkeypatch,tmp_path):
    monkeypatch.delenv('GEMINI_API_KEY',raising=False)
    monkeypatch.setenv('GEMINI_API_KEY_FILE',str(tmp_path/'missing-key'))
    monkeypatch.setenv('COPILOT_GEMINI_ENABLED','1')
    def forbidden(_):raise AssertionError('No key must mean no network')
    client=GeminiClient(httpx.MockTransport(forbidden))
    assert not client.configured
    with pytest.raises(ProviderUnavailable):client.plan('question',{})


def test_fragment_cannot_remove_policy_negation(configured):
    client=GeminiClient(httpx.MockTransport(lambda _:response({'items':[{'source_id':'policy-v2','quote':'eligible for payment reduction','label':'Policy'}]})))
    with pytest.raises(ProviderUnavailable):
        client.summarise('policy',{'policy-v2':'Not eligible for payment reduction unless all programme conditions are verified.'})


def test_invalid_config_uses_bounded_defaults(configured,monkeypatch):
    monkeypatch.setenv('COPILOT_GEMINI_TIMEOUT','NaN')
    monkeypatch.setenv('COPILOT_GEMINI_MAX_CALLS','invalid')
    client=GeminiClient()
    assert client.timeout==15. and client.max_calls==60


def test_identical_concurrent_requests_share_one_call(configured):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    started,release=Event(),Event();calls=[]
    plan={'metric_id':'open_cases','grouping':'none','start_date':'2026-09-28','end_date':'2026-09-29','filters':{},'clarification':None,'refuse':False,'refuse_reason':None}
    def send(request):
        calls.append(request);started.set()
        assert release.wait(2)
        return response(plan)
    client=GeminiClient(httpx.MockTransport(send))
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(client.plan,'same question',{})
        assert started.wait(2)
        second=pool.submit(client.plan,'same question',{})
        release.set()
        assert first.result()['metric_id']==second.result()['metric_id']=='open_cases'
    assert len(calls)==1


def test_unrelated_requests_do_not_hold_network_lock(configured):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    barrier=Barrier(2)
    plan={'metric_id':'open_cases','grouping':'none','start_date':'2026-09-28','end_date':'2026-09-29','filters':{},'clarification':None,'refuse':False,'refuse_reason':None}
    def send(_):
        barrier.wait(timeout=2)
        return response(plan)
    client=GeminiClient(httpx.MockTransport(send))
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(client.plan,'first question',{})
        second=pool.submit(client.plan,'second question',{})
        assert first.result()['metric_id']==second.result()['metric_id']=='open_cases'


def test_policy_label_is_only_offered_with_a_policy_source(configured):
    offered = []
    def send(request):
        schema = json.loads(request.content)['response_format']['schema']
        offered.append(schema['properties']['items']['items']['properties']['label']['enum'])
        return response({'items': [{'source_id': 'review-rule', 'quote': 'Hardship is recorded on the case.', 'label': 'Evidence'}]})
    client = GeminiClient(httpx.MockTransport(send))
    client.summarise('review brief', {'review-rule': 'Hardship is recorded on the case.'})
    client.summarise('policy', {'review-rule': 'Hardship is recorded on the case.', 'POL-COLL-004 v4.2 §4.2': 'Offer hardship options first.'})
    assert offered == [['Evidence'], ['Evidence', 'Policy']]
