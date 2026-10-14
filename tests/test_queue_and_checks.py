"""Work queue tiers, agent scoping and portfolio-check access through HTTP."""
import json
from datetime import date

import duckdb
import pytest
from fastapi.testclient import TestClient

from app import main, portfolio_checks, storage, work_queue


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, 'STATE', tmp_path / 'reviews.sqlite3')
    monkeypatch.setattr(main, 'DB', tmp_path / 'test.duckdb')
    monkeypatch.setattr(main, 'DATASET', tmp_path)
    monkeypatch.setattr(main, 'QUALITY', tmp_path / 'quality.json')
    main.QUALITY.write_text(json.dumps({'identity': {}, 'checks': []}))
    with duckdb.connect(str(main.DB)) as c:
        c.execute('CREATE SCHEMA gold')
        c.execute("CREATE TABLE gold.cases AS SELECT * FROM (VALUES ('C-1','CS-1',NULL,'A-1'),('C-2','CS-2',NULL,'A-2')) t(customer_id,case_id,outcome,assigned_agent_id)")
        c.execute("CREATE TABLE gold.checks AS SELECT 7 n")
    monkeypatch.setenv('COPILOT_AGENT_ID', 'A-1')
    seen = []
    monkeypatch.setattr(work_queue, 'build', lambda c, agent: seen.append(agent) or {'agent_id': agent, 'items': []})
    monkeypatch.setattr(portfolio_checks, 'CHECKS', [{'id': 'demo', 'title': 'Demo', 'sql': 'SELECT n FROM gold.checks'}])
    portfolio_checks._cache.clear()
    with TestClient(main.app) as api:
        yield api, seen


def headers(api, role):
    response = api.post('/api/auth/login', json={'username': role, 'password': role + '-demo'})
    return {'Authorization': 'Bearer ' + response.json()['token']}


def test_agent_queue_is_always_their_own(client):
    api, seen = client
    h = headers(api, 'agent')
    assert api.get('/api/queue?agent=A-2', headers=h).json()['agent_id'] == 'A-1'
    assert 'agents' not in api.get('/api/queue', headers=h).json()
    assert seen == ['A-1', 'A-1']


def test_supervisor_can_pick_an_agent_and_input_is_validated(client):
    api, seen = client
    h = headers(api, 'supervisor')
    body = api.get('/api/queue?agent=A-2', headers=h).json()
    assert body['agent_id'] == 'A-2' and body['agents'][0]['agent_id'] in ['A-1', 'A-2']
    assert api.get("/api/queue?agent=A-2' OR 1=1", headers=h).status_code == 422
    assert api.get('/api/queue').status_code == 401
    assert api.get('/api/queue', headers=headers(api, 'analyst')).status_code == 403


def test_portfolio_checks_return_sql_and_value_and_exclude_agents(client):
    api, _ = client
    assert api.get('/api/overview/checks', headers=headers(api, 'agent')).status_code == 403
    item = api.get('/api/overview/checks', headers=headers(api, 'analyst')).json()['items'][0]
    assert item['value'] == 7 and item['sql'] == 'SELECT n FROM gold.checks'


def row(**values):
    base = dict.fromkeys(['bankruptcy_flag', 'consumer_proposal_flag', 'insolvency_hold_flag', 'cease_communication_flag', 'cease_contact_flag',
                          'deceased_flag', 'deceased_hold_flag', 'hardship_flag', 'hardship_plan_type', 'ptp_due_date', 'ptp_amount'])
    return base | {'case_status': 'open', 'current_dpd': 30, 'total_overdue': 100.0} | values


def test_tier_rules_in_priority_order():
    today = date(2026, 9, 28)
    assert work_queue._tier(row(consumer_proposal_flag=True), today)[0] == 'stop_now'
    assert work_queue._tier(row(consumer_proposal_flag=True, case_status='insolvency_hold'), today)[0] == 'on_hold'
    assert work_queue._tier(row(cease_contact_flag=True), today)[0] == 'on_hold'
    assert work_queue._tier(row(ptp_due_date=date(2026, 10, 1), ptp_amount=50.0, hardship_flag=True), today)[0] == 'promise_due'
    assert work_queue._tier(row(hardship_flag=True, current_dpd=170), today)[0] == 'hardship_no_plan'
    assert work_queue._tier(row(hardship_flag=True, hardship_plan_type='reduced_payment', current_dpd=170), today)[0] == 'near_write_off'
    assert work_queue._tier(row(ptp_due_date=date(2026, 9, 10)), today)[0] == 'promise_overdue'
    assert work_queue._tier(row(current_dpd=181), today)[0] == 'standard'


def test_vulnerability_never_changes_the_tier():
    today = date(2026, 9, 28)
    for values in [{}, {'hardship_flag': True}, {'current_dpd': 160}]:
        assert work_queue._tier(row(**values), today) == work_queue._tier(row(vulnerable_customer_flag=True, **values), today)


def test_concurrent_requests_do_not_race_the_database_lockdown(client):
    from concurrent.futures import ThreadPoolExecutor
    api, _ = client
    h = headers(api, 'supervisor')
    with ThreadPoolExecutor(8) as pool:
        codes = list(pool.map(lambda _: api.get('/api/queue', headers=h).status_code, range(24)))
    assert set(codes) == {200}
