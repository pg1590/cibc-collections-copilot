"""Source hardship and holds take priority without changing the classifier."""
import json

import duckdb
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import main, storage
from app.features import TEXT_FEATURES


class ReviewModel:
    def predict_proba(self, rows):
        return np.array([[0.73, 0.27] for _ in rows])


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, 'STATE', tmp_path / 'reviews.sqlite3')
    monkeypatch.setattr(main, 'DB', tmp_path / 'briefs.duckdb')
    monkeypatch.setattr(main, 'DATASET', tmp_path)
    monkeypatch.setattr(main, 'QUALITY', tmp_path / 'quality.json')
    monkeypatch.setattr(main, 'MODEL', tmp_path / 'mock-model.joblib')
    main.MODEL.write_bytes(b'test double')
    main.QUALITY.write_text(json.dumps({'identity': {}, 'checks': []}))
    monkeypatch.setattr(main.joblib, 'load', lambda _: {'model': ReviewModel(), 'features': TEXT_FEATURES})
    monkeypatch.setattr(main, 'feature_sql', lambda _: 'SELECT * FROM gold.test_features WHERE customer_id=?')
    monkeypatch.setenv('COPILOT_GEMINI_ENABLED', '0')
    monkeypatch.delenv('COPILOT_SUPERVISOR_PASSWORD', raising=False)
    with duckdb.connect(str(main.DB)) as c:
        c.execute('CREATE SCHEMA gold')
        c.execute('CREATE TABLE gold.customers(customer_id VARCHAR, cease_communication_flag BOOLEAN, internal_do_not_call_flag BOOLEAN, bankruptcy_flag BOOLEAN, consumer_proposal_flag BOOLEAN, deceased_flag BOOLEAN)')
        c.execute('CREATE TABLE gold.customer_summary(customer_id VARCHAR, open_cases INTEGER, total_overdue DOUBLE, max_dpd INTEGER, preferred_language VARCHAR)')
        c.execute('CREATE TABLE gold.cases(customer_id VARCHAR, case_id VARCHAR, outcome VARCHAR, hardship_flag BOOLEAN, cease_contact_flag BOOLEAN, insolvency_hold_flag BOOLEAN, deceased_hold_flag BOOLEAN)')
        c.execute('CREATE TABLE gold.latest_notes(customer_id VARCHAR, note_id VARCHAR, note_text VARCHAR, note_language VARCHAR, note_ts TIMESTAMP)')
        c.execute('CREATE TABLE gold.test_features(customer_id VARCHAR, note_id VARCHAR, ' + ', '.join(key + ' INTEGER' for key in TEXT_FEATURES) + ')')
        for cid in ['recorded', 'held', 'possible', 'unknown', 'closed']:
            c.execute('INSERT INTO gold.customers VALUES(?,false,false,false,false,false)', [cid])
            c.execute("INSERT INTO gold.customer_summary VALUES(?,1,100.0,20,'EN')", [cid])
            c.execute('INSERT INTO gold.cases VALUES(?,?,?,?,false,?,false)', [cid, 'CS-' + cid, 'closed' if cid == 'closed' else None, cid in ['recorded', 'held', 'closed'], cid == 'held'])
            cues = [int(cid == 'possible' and key == 'income_reduction') for key in TEXT_FEATURES]
            c.execute('INSERT INTO gold.test_features VALUES(' + ','.join('?' for _ in range(2 + len(cues))) + ')', [cid, 'NOTE-' + cid if cid == 'possible' else None, *cues])
        c.execute("INSERT INTO gold.latest_notes VALUES('possible','NOTE-possible','My hours were cut.','EN',TIMESTAMP '2026-09-28')")
    with TestClient(main.app) as client:
        token = client.post('/api/auth/login', json={'username': 'supervisor', 'password': 'supervisor-demo'}).json()['token']
        yield client, {'Authorization': 'Bearer ' + token}


def generate(api, cid):
    client, headers = api
    response = client.post('/api/briefs', json={'customer_id': cid}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_recorded_hardship_survives_no_note_cue(api):
    brief = generate(api, 'recorded')
    assert brief['hardship_status'] == 'recorded'
    assert brief['recorded_hardship_cases'] == ['CS-recorded']
    assert brief['model']['review_probability'] < .5
    assert 'Financial hardship is recorded' in brief['recommendation']
    assert 'CS-recorded' in brief['recommendation_reason']
    assert any(signal['evidence'] == 'collections_cases:CS-recorded' for signal in brief['signals'])


def test_insolvency_hold_overrides_recorded_hardship(api):
    brief = generate(api, 'held')
    assert brief['hardship_status'] == 'recorded'
    assert brief['recommendation'].startswith('Hold contact')
    assert 'insolvency hold on case CS-held' in brief['recommendation_reason']
    assert brief['draft'].startswith('Internal review only')


def test_possible_cue_is_distinct_from_recorded_hardship(api):
    brief = generate(api, 'possible')
    assert brief['hardship_status'] == 'possible'
    assert not brief['recorded_hardship_cases']
    assert 'NOTE-possible' in brief['recommendation_reason']
    assert 'not a confirmed hardship' in brief['recommendation_reason']


@pytest.mark.parametrize('cid', ['unknown', 'closed'])
def test_no_signal_does_not_establish_absence_and_closed_flag_is_not_active(api, cid):
    brief = generate(api, cid)
    assert brief['hardship_status'] == 'not_established'
    assert not brief['recorded_hardship_cases']
    assert 'does not establish that hardship is absent' in brief['recommendation_reason']


def test_review_reason_does_not_replace_recommendation_reason(api):
    client, headers = api
    brief = generate(api, 'recorded')
    response = client.post('/api/reviews/' + brief['brief_id'], json={'decision': 'approve', 'reason': 'Checked source case'}, headers=headers)
    assert response.status_code == 200
    saved = response.json()
    assert saved['reason'] == 'Checked source case'
    assert saved['recommendation_reason'] == brief['recommendation_reason']
    event = next(item for item in client.get('/api/audit', headers=headers).json()['items'] if item['action'] == 'generate_brief')
    assert event['details']['recorded_hardship_cases'] == ['CS-recorded']


@pytest.mark.parametrize('flag',['bankruptcy_flag','consumer_proposal_flag','deceased_flag','cease_communication_flag'])
def test_customer_restrictions_override_recorded_hardship(api,flag):
    # Identifiers are test-controlled, never request input.
    with duckdb.connect(str(main.DB)) as c:
        c.execute(f"UPDATE gold.customers SET {flag}=true WHERE customer_id='recorded'")
    brief=generate(api,'recorded')
    assert brief['recommendation'].startswith('Hold contact')
    assert 'customer record' in brief['recommendation_reason']
    assert brief['hardship_status']=='recorded'


def test_closed_case_hold_does_not_apply_to_active_cases(api):
    with duckdb.connect(str(main.DB)) as c:
        c.execute("UPDATE gold.cases SET insolvency_hold_flag=true WHERE customer_id='closed'")
    brief=generate(api,'closed')
    assert not brief['recommendation'].startswith('Hold contact')


def test_do_not_call_restriction_remains_explicit(api):
    with duckdb.connect(str(main.DB)) as c:
        c.execute("UPDATE gold.customers SET internal_do_not_call_flag=true WHERE customer_id='recorded'")
    brief=generate(api,'recorded')
    assert 'do not initiate a call' in brief['recommendation']
    assert 'blocks calling' in brief['recommendation_reason']


def test_french_recorded_hardship_draft_does_not_invent_customer_statement(api):
    with duckdb.connect(str(main.DB)) as c:
        c.execute("UPDATE gold.customer_summary SET preferred_language='FR' WHERE customer_id='recorded'")
    brief=generate(api,'recorded')
    assert 'est enregistrée' in brief['draft']
    assert 'vous avez signalé' not in brief['draft'].lower()
