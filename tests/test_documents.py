"""The policy library serves release documents verbatim, to every signed-in role, and never reads outside files/docs."""
import csv
import json
import duckdb
import pytest
from fastapi.testclient import TestClient
from app import main, storage

FIELDS = ['doc_id', 'doc_type', 'title', 'language', 'version', 'effective_date', 'superseded_by', 'owner', 'section_ids', 'file_path']
POLICY = """> Synthetic document created for the Maple Bank collections hackathon. Not legal advice; not a real policy.

# Collections Contact Policy (POL-COLL-001, v3.0)

## §5.1 Permitted hours
Calls between **07:00 and 21:00** local time.

## §5.4 Cease-communication requests and representatives
A written cease-communication request stops calls, texts and emails.
"""


@pytest.fixture
def client(tmp_path, monkeypatch):
    release = tmp_path/'release'
    (release/'files/docs/policy').mkdir(parents=True)
    (release/'data').mkdir()
    (release/'files/docs/policy/POL-COLL-001_v3.0_EN.md').write_text(POLICY, encoding='utf-8')
    (release/'files/docs/policy/POL-COLL-004_v4.1_EN.md').write_text('# Old\n\n## §4.2 Offer\nOld text.\n', encoding='utf-8')
    (tmp_path/'secret.md').write_text('## §1.1 Secret\nnot a release document\n', encoding='utf-8')
    rows = [
        {'doc_id': 'POL-COLL-001', 'doc_type': 'policy', 'title': 'Collections Contact Policy', 'language': 'EN', 'version': '3.0',
         'effective_date': '2026-01-01', 'superseded_by': '', 'owner': 'Policy Office', 'section_ids': '[]', 'file_path': 'docs/policy/POL-COLL-001_v3.0_EN.md'},
        {'doc_id': 'POL-COLL-004-V4.1', 'doc_type': 'policy', 'title': 'Hardship Policy', 'language': 'EN', 'version': '4.1',
         'effective_date': '2025-03-01', 'superseded_by': 'POL-COLL-004', 'owner': 'Policy Office', 'section_ids': '[]', 'file_path': 'docs/policy/POL-COLL-004_v4.1_EN.md'},
        {'doc_id': 'ESCAPE', 'doc_type': 'policy', 'title': 'Escape', 'language': 'EN', 'version': '1.0',
         'effective_date': '', 'superseded_by': '', 'owner': '', 'section_ids': '[]', 'file_path': '../../secret.md'},
    ]
    with (release/'data/reference_documents.csv').open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    monkeypatch.setattr(storage, 'STATE', tmp_path/'reviews.sqlite3')
    monkeypatch.setattr(main, 'DB', tmp_path/'test.duckdb')
    monkeypatch.setattr(main, 'DATASET', release)
    monkeypatch.setattr(main, 'QUALITY', tmp_path/'quality.json')
    main.QUALITY.write_text(json.dumps({'identity': {}, 'checks': []}))
    duckdb.connect(str(main.DB)).close()
    with TestClient(main.app) as api:
        yield api


def headers(client, role):
    r = client.post('/api/auth/login', json={'username': role, 'password': role+'-demo'})
    assert r.status_code == 200
    return {'Authorization': 'Bearer '+r.json()['token']}


def test_library_requires_sign_in(client):
    assert client.get('/api/documents').status_code == 401


@pytest.mark.parametrize('role', ['analyst', 'agent', 'supervisor'])
def test_every_role_can_read_the_library(client, role):
    assert client.get('/api/documents', headers=headers(client, role)).status_code == 200


def test_sections_are_served_verbatim_with_current_versions_first(client):
    docs = client.get('/api/documents', headers=headers(client, 'agent')).json()['documents']
    assert [d['doc_id'] for d in docs] == ['POL-COLL-001', 'POL-COLL-004-V4.1']
    policy = docs[0]
    assert policy['current'] and [s['id'] for s in policy['sections']] == ['§5.1', '§5.4']
    cease = policy['sections'][1]
    assert cease['heading'] == '§5.4 Cease-communication requests and representatives'
    assert cease['text'] == 'A written cease-communication request stops calls, texts and emails.'
    assert 'not a real policy' in policy['preamble'] and len(policy['sha256']) == 64
    assert docs[1]['current'] is False and docs[1]['superseded_by'] == 'POL-COLL-004'


def test_rows_pointing_outside_the_release_docs_are_never_read(client):
    body = client.get('/api/documents', headers=headers(client, 'supervisor')).text
    assert 'ESCAPE' not in body and 'Secret' not in body
