"""Exercise authorization and persistent review boundaries through HTTP."""
import json
import sqlite3
import duckdb
import pytest
from fastapi.testclient import TestClient
from app import main,storage


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'STATE',tmp_path/'reviews.sqlite3')
    monkeypatch.setattr(main,'DB',tmp_path/'test.duckdb')
    monkeypatch.setattr(main,'DATASET',tmp_path)
    monkeypatch.setattr(main,'QUALITY',tmp_path/'quality.json')
    main.QUALITY.write_text(json.dumps({'identity':{},'checks':[]}))
    c=duckdb.connect(str(main.DB))
    c.execute('CREATE SCHEMA gold')
    c.execute("CREATE TABLE gold.customers AS SELECT * FROM (VALUES ('C-1'),('C-2')) t(customer_id)")
    c.execute("CREATE TABLE gold.cases AS SELECT * FROM (VALUES ('C-1','CS-1','open','A-1'),('C-2','CS-2','open','A-2')) t(customer_id,case_id,case_status,assigned_agent_id)")
    c.execute("CREATE TABLE gold.customer_summary AS SELECT * FROM (VALUES ('C-1','Alpha Example','ON',1,100.0,10,1.0),('C-2','Beta Example','QC',1,200.0,20,1.0)) t(customer_id,name,province,open_cases,total_overdue,max_dpd,identity_confidence)")
    c.close();monkeypatch.setenv('COPILOT_AGENT_ID','A-1')
    with TestClient(main.app) as api:yield api


def headers(client,role):
    r=client.post('/api/auth/login',json={'username':role,'password':role+'-demo'})
    assert r.status_code==200
    return {'Authorization':'Bearer '+r.json()['token']}


def test_server_roles_and_session(client):
    assert client.get('/api/customers').status_code==401
    assert client.post('/api/auth/login',json={'username':'supervisor','password':'wrong'}).status_code==401
    h=headers(client,'analyst');h['X-Role']='supervisor'
    assert client.get('/api/audit',headers=h).status_code==403
    assert client.post('/api/reviews/any',headers=h,json={'decision':'approve','reason':'checked'}).status_code==403


def test_assigned_customer_scope_and_search_injection(client):
    h=headers(client,'agent')
    r=client.get('/api/customers',headers=h).json()
    assert [x['customer_id'] for x in r['items']]==['C-1']
    assert r['total']==1
    assert client.get('/api/customers/C-2',headers=h).status_code==404
    assert client.post('/api/ask',headers=h,json={'question':'List all customers'}).status_code==403
    assert client.get('/api/customers',params={'search':"%' OR 1=1 --"},headers=h).json()['items']==[]


def test_review_persistence_and_append_only_audit(client):
    payload={'brief_id':'B-1','customer_id':'C-1','summary':'Source facts','recommendation':'Review','draft':'Original'}
    with storage.connect() as c:c.execute('INSERT INTO briefs VALUES(?,?,?,?,?,?,?,?,?)',('B-1','C-1','agent',json.dumps(payload),'pending',storage.now(),None,None,None))
    h=headers(client,'supervisor')
    assert client.post('/api/reviews/B-1',headers=h,json={'decision':'approve','reason':'   '}).status_code==422
    assert client.post('/api/reviews/B-1',headers=h,json={'decision':'edit','reason':'verified source'}).status_code==422
    r=client.post('/api/reviews/B-1',headers=h,json={'decision':'edit','reason':'Verified the case and changed wording','draft':'Reviewed wording'})
    assert r.status_code==200;assert r.json()['draft']=='Reviewed wording'
    assert client.get('/api/reviews',headers=h).json()['items'][0]['status']=='edited'
    assert client.post('/api/reviews/B-1',headers=h,json={'decision':'approve','reason':'again'}).status_code==409
    events=client.get('/api/audit',headers=h).json()['items']
    review=next(e for e in events if e['action']=='review_edit')
    assert review['details']['previous_draft']=='Original'
    assert review['details']['final_draft']=='Reviewed wording'
    with storage.connect() as c:
        with pytest.raises(sqlite3.IntegrityError):c.execute("UPDATE audit SET actor='someone else'")


def test_raw_identifiers_and_null_tokens(tmp_path):
    p=tmp_path/'raw.csv';p.write_text('customer_id,outcome,note\n0000123456,NA,N/A\n0000000001,,na\n')
    c=duckdb.connect()
    rows=c.execute("SELECT * FROM read_csv(?,all_varchar=true,header=true,nullstr='')",[str(p)]).fetchall();c.close()
    assert rows==[('0000123456','NA','N/A'),('0000000001',None,'na')]


def test_timeline_and_calendar_respect_agent_scope(client):
    h=headers(client,'agent')
    assert client.get('/api/customers/C-2/timeline',headers=h).status_code==404
    assert client.get('/api/customers/C-2/calendar',headers=h).status_code==404
