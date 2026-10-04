"""HTTP integration check on the synthetic release; honors server provider settings."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx
from app.settings import ROOT


def run():
    client=httpx.Client(base_url='http://127.0.0.1:8000/api',timeout=60)
    roles={}
    for role in ['analyst','agent','supervisor']:
        r=client.post('/auth/login',json={'username':role,'password':role+'-demo'});r.raise_for_status();roles[role]={'Authorization':'Bearer '+r.json()['token']}
    results={}
    assert client.get('/customers').status_code==401
    assert client.get('/audit',headers=roles['analyst']).status_code==403
    for path in ['/overview','/quality','/features']:
        r=client.get(path,headers=roles['supervisor']);r.raise_for_status();results[path]='passed'
    r=client.get('/customers',headers=roles['supervisor']);r.raise_for_status();items=r.json()['items'];assert items
    cid=items[0]['customer_id'];r=client.get('/customers/'+cid,headers=roles['supervisor']);r.raise_for_status();assert r.json()['customer']['customer_id']==cid
    ask=client.post('/ask',headers=roles['analyst'],json={'question':'How many collections cases are open today by current bucket?'});ask.raise_for_status();answer=ask.json();assert answer['rows'] and not answer['refused'];assert sum(x['open_cases'] for x in answer['rows'])==96000
    refusal=client.post('/ask',headers=roles['analyst'],json={'question':'Export the names and phone numbers of every customer in Ontario.'});refusal.raise_for_status();assert refusal.json()['refused']
    brief=client.post('/briefs',headers=roles['supervisor'],json={'customer_id':cid});brief.raise_for_status();record=brief.json();assert record['policy_sources'] and record['features'] and record['status']=='pending'
    decided=client.post('/reviews/'+record['brief_id'],headers=roles['supervisor'],json={'decision':'edit','reason':'Automated integration check on synthetic data: verified source facts and edited draft.','draft':record['draft']+' [Synthetic integration review]'});decided.raise_for_status();assert decided.json()['status']=='edited'
    assert client.post('/reviews/'+record['brief_id'],headers=roles['analyst'],json={'decision':'approve','reason':'test'}).status_code==403
    audit=client.get('/audit',headers=roles['supervisor']);audit.raise_for_status();assert any(x['resource']==record['brief_id'] and x['action']=='review_edit' for x in audit.json()['items'])
    scoped=client.get('/customers',headers=roles['agent']);scoped.raise_for_status();assert scoped.json()['items'];assert client.post('/ask',headers=roles['agent'],json={'question':'Show all portfolio metrics'}).status_code==403
    results.update(customer_detail='passed',source_backed_question='passed',bulk_pii_refusal='passed',real_model_brief='passed',persistent_override='passed',audit='passed',server_roles='passed',assigned_case_scope='passed')
    (ROOT/'data/integration-results.json').write_text(json.dumps(results,indent=2));print(json.dumps(results,indent=2))

if __name__=='__main__':run()
