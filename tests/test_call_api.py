"""Call Mode over HTTP: roles, assigned-case scope, submit gating and review hand-off."""
import json

import duckdb
import pytest
from fastapi.testclient import TestClient

from app import call_session, main, runtime, storage


def fake_session(ready=True):
    return {'stage': 'conversation', 'outcomes': call_session.normalise({'reached': 'customer'}),
            'plan': {'next_action': 'Ask for the payment', 'steps': []}, 'checks': [{'key': 'promise', 'status': 'ok', 'message': 'ok', 'policy': ['PRC-COLL-010 v2.1 §3.1']}],
            'wrap_up': {'note': 'Call Thu 01 Oct: Reached the customer.\nPromise to pay CAD 50.00.', 'outcome_codes': ['RPC', 'PTP'],
                        'follow_ups': [{'type': 'reminder', 'when': 'Fri', 'reason': 'r'}], 'ready_to_submit': ready, 'blocking': [] if ready else ['Verify identity first.']}}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, 'STATE', tmp_path / 'reviews.sqlite3')
    monkeypatch.setattr(main, 'DB', tmp_path / 'test.duckdb')
    monkeypatch.setattr(main, 'QUALITY', tmp_path / 'quality.json')
    main.QUALITY.write_text(json.dumps({'identity': {}, 'checks': []}))
    with duckdb.connect(str(main.DB)) as c:
        c.execute('CREATE SCHEMA gold')
        c.execute("CREATE TABLE gold.customers AS SELECT * FROM (VALUES ('C-1'),('C-2')) t(customer_id)")
        c.execute("CREATE TABLE gold.cases AS SELECT * FROM (VALUES ('C-1','CS-1','A-1'),('C-2','CS-2','A-2')) t(customer_id,case_id,assigned_agent_id)")
    monkeypatch.setenv('COPILOT_AGENT_ID', 'A-1')
    monkeypatch.setenv('COPILOT_GEMINI_ENABLED', '0')
    state = {'ready': True}
    monkeypatch.setattr(main, '_call_session', lambda c, cid, outcomes: fake_session(state['ready']))
    with TestClient(main.app) as api:
        yield api, state


def headers(api, role):
    return {'Authorization': 'Bearer ' + api.post('/api/auth/login', json={'username': role, 'password': role + '-demo'}).json()['token']}


def test_roles_and_scope(client):
    api, _ = client
    body = {'customer_id': 'C-1', 'outcomes': {}}
    assert api.post('/api/call/session', json=body, headers=headers(api, 'analyst')).status_code == 403
    assert api.post('/api/call/session', json=body, headers=headers(api, 'agent')).status_code == 200
    assert api.post('/api/call/session', json={'customer_id': 'C-2', 'outcomes': {}}, headers=headers(api, 'agent')).status_code == 404
    assert api.post('/api/call/session', json=body).status_code == 401


def test_submit_requires_ready_and_lands_in_review(client):
    api, state = client
    h = headers(api, 'agent')
    state['ready'] = False
    blocked = api.post('/api/call/submit', json={'customer_id': 'C-1', 'outcomes': {}}, headers=h)
    assert blocked.status_code == 422 and 'Verify identity first.' in blocked.text
    state['ready'] = True
    saved = api.post('/api/call/submit', json={'customer_id': 'C-1', 'outcomes': {}, 'note': '  '}, headers=h).json()
    assert saved['status'] == 'pending'
    items = api.get('/api/reviews', headers=headers(api, 'supervisor')).json()['items']
    record = next(i for i in items if i['brief_id'] == saved['brief_id'])
    assert record['kind'] == 'call' and record['draft'].startswith('Call Thu 01 Oct') and record['call']['outcome_codes'] == ['RPC', 'PTP']
    with storage.connect() as s:
        assert s.execute("SELECT count(*) FROM audit WHERE action='call_submit'").fetchone()[0] == 1


def test_extract_uses_rules_without_a_key(client):
    api, _ = client
    runtime.provider.cache_clear()
    result = api.post('/api/call/extract', json={'customer_id': 'C-1', 'note': 'I lost my job last month.'}, headers=headers(api, 'agent')).json()
    assert result['provider'] == 'rules' and result['proposals'][0]['field'] == 'hardship.stated'
    assert api.post('/api/call/extract', json={'customer_id': 'C-2', 'note': 'x'}, headers=headers(api, 'agent')).status_code == 404
