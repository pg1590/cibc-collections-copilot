"""Local Collections Copilot API. All customer facts come from the release."""
import json
import os
import secrets
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

import duckdb
import joblib
from fastapi import Depends,FastAPI,HTTPException,Query
from fastapi.security import HTTPAuthorizationCredentials,HTTPBearer
from pydantic import BaseModel,Field
from app import storage
from app.features import VERSION,TEXT_FEATURES,feature_sql,evidence,definitions
from app.settings import DATASET,DB,QUALITY,MODEL,MODEL_REPORT,ROOT,SNAPSHOT

app=FastAPI(title='Collections Copilot',version='0.1.0')
bearer=HTTPBearer(auto_error=False)


@contextmanager
def db():
    if not QUALITY.exists() or not DB.exists():raise HTTPException(503,'Dataset pipeline is not ready. Run scripts/build_data.py.')
    c=duckdb.connect(str(DB),read_only=True)
    c.execute("SET memory_limit='1GB'");c.execute('SET threads=2')
    trusted=str(DATASET/'data').replace("'","''")
    if c.execute("SELECT current_setting('enable_external_access')").fetchone()[0]:
        c.execute(f"SET allowed_directories=['{trusted}/']")
        c.execute('SET enable_external_access=false')
    try:yield c
    finally:c.close()


def records(c,sql,params=None):
    result=c.execute(sql,params or []);keys=[d[0] for d in result.description]
    return [dict(zip(keys,row)) for row in result.fetchall()]


def user(creds:HTTPAuthorizationCredentials=Depends(bearer)):
    if not creds:raise HTTPException(401,'Sign in to continue.')
    u=storage.session(creds.credentials)
    if not u:raise HTTPException(401,'Session expired. Sign in again.')
    return u


def supervisor(u=Depends(user)):
    if u['role']!='supervisor':raise HTTPException(403,'A supervisor must review this action.')
    return u


def agent_id(c):
    configured=os.getenv('COPILOT_AGENT_ID')
    if configured:return configured
    row=c.execute("SELECT assigned_agent_id FROM gold.cases WHERE outcome IS NULL AND assigned_agent_id IS NOT NULL GROUP BY 1 ORDER BY count(*) DESC,assigned_agent_id LIMIT 1").fetchone()
    return row[0] if row else '__no_assigned_cases__'


def scope(c,u,alias='s'):
    if u['role']=='agent':
        return f"EXISTS(SELECT 1 FROM gold.cases sc WHERE sc.customer_id={alias}.customer_id AND sc.assigned_agent_id=?)",[agent_id(c)]
    return 'TRUE',[]


def authorize_customer(c,u,cid):
    condition,params=scope(c,u,'s')
    if not c.execute(f'SELECT 1 FROM gold.customers s WHERE customer_id=? AND {condition}',[cid,*params]).fetchone():
        raise HTTPException(404,'Customer was not found in your permitted cases.')


class Login(BaseModel):
    username:str=Field(max_length=64)
    password:str=Field(max_length=256)


@app.get('/api/health')
def health():
    return {'status':'ok','dataset_ready':QUALITY.exists() and DB.exists(),'snapshot_date':SNAPSHOT,'runtime_mode':'local; no paid API calls'}


@app.post('/api/auth/login')
def login(body:Login):
    role=body.username if body.username in ['analyst','agent','supervisor'] else None
    expected=os.getenv('COPILOT_'+str(role).upper()+'_PASSWORD',str(role)+'-demo')
    if role is None or not secrets.compare_digest(body.password,expected):raise HTTPException(401,'Incorrect username or password.')
    return {'token':storage.create_session(body.username,role),'user':{'username':body.username,'role':role}}


@app.get('/api/overview')
def overview(u=Depends(user)):
    with db() as c:
        condition,p=scope(c,u)
        row=records(c,f'SELECT count(*) customers,sum(open_cases) open_cases,sum(total_overdue) overdue_cad FROM gold.customer_summary s WHERE {condition}',p)[0]
        if u['role']!='agent':
            all_cases=records(c,'SELECT count(*) open_cases,sum(total_overdue) overdue_cad FROM curated.collections_cases WHERE outcome IS NULL')[0]
            row.update(all_cases)
    quality=json.loads(QUALITY.read_text())
    with storage.connect() as s:
        pending=s.execute("SELECT count(*) FROM briefs WHERE status='pending'"+(' AND actor=?' if u['role']=='agent' else ''),[u['username']] if u['role']=='agent' else []).fetchone()[0]
    row.update(identity={k:quality['identity'].get(k,0) for k in ['matched','review','unmatched']},quality_issues=sum(x['failed_rows'] for x in quality['checks']),pending_reviews=pending)
    return row


@app.get('/api/customers')
def customers(search:str=Query('',max_length=100),limit:int=Query(20,ge=1,le=100),u=Depends(user)):
    with db() as c:
        condition,p=scope(c,u)
        # LIKE search escapes user wildcards; bound values cannot become SQL.
        value='%'+search.replace('!','!!').replace('%','!%').replace('_','!_')+'%'
        where=f"{condition} AND (s.customer_id ILIKE ? ESCAPE '!' OR s.name ILIKE ? ESCAPE '!')"
        params=[*p,value,value]
        items=records(c,f'SELECT * FROM gold.customer_summary s WHERE {where} ORDER BY open_cases DESC,total_overdue DESC,customer_id LIMIT ?',[*params,limit])
        total=c.execute(f'SELECT count(*) FROM gold.customer_summary s WHERE {where}',params).fetchone()[0]
    return {'items':items,'total':total}


@app.get('/api/customers/{cid}')
def customer(cid:str,u=Depends(user)):
    with db() as c:
        authorize_customer(c,u,cid)
        profile=records(c,'SELECT * FROM gold.customer_summary WHERE customer_id=?',[cid])[0]
        accounts=records(c,'SELECT * FROM gold.accounts WHERE customer_id=? ORDER BY overdue DESC NULLS LAST',[cid])
        cases=records(c,'SELECT case_id,case_status,primary_product,current_bucket,current_dpd,total_overdue,queue,assigned_agent_id,case_open_date FROM gold.cases WHERE customer_id=? ORDER BY case_open_date DESC',[cid])
        links=records(c,'SELECT source_system,source_key,confidence,status,"method",fuzzy_name_similarity FROM gold.identity_crosswalk WHERE customer_id=?',[cid])
        notes=records(c,'SELECT note_id,note_ts,note_text,note_language,case_id FROM gold.latest_notes WHERE customer_id=?',[cid])
        features=records(c,'SELECT * FROM gold.features WHERE customer_id=?',[cid])[0] if c.execute("SELECT 1 FROM information_schema.tables WHERE table_schema='gold' AND table_name='features'").fetchone() else {}
    return {'customer':profile,'accounts':accounts,'cases':cases,'identity':links,'notes':notes,'features':features,'snapshot_date':SNAPSHOT}


class Ask(BaseModel):question:str=Field(min_length=3,max_length=1500)


@app.post('/api/ask')
def ask(body:Ask,u=Depends(user)):
    if u['role']=='agent':raise HTTPException(403,'Use a customer brief for your assigned cases. Portfolio questions require an analyst or supervisor.')
    if not QUALITY.exists():raise HTTPException(503,'Dataset pipeline is not ready.')
    try:from app.insights import InsightEngine
    except ImportError:raise HTTPException(503,'Question-answering module is not ready.')
    answer=InsightEngine(DB,DATASET).answer(body.question,role=u['role'])
    with storage.connect() as s:storage.audit(s,u['username'],'ask','portfolio',{'question':body.question,'refused':answer.get('refused',False),'sql_or_sources':answer.get('sql_or_sources','')})
    return answer


class Brief(BaseModel):customer_id:str=Field(min_length=1,max_length=100)


@app.post('/api/briefs')
def brief(body:Brief,u=Depends(user)):
    if not MODEL.exists():raise HTTPException(503,'Local model is not trained. Run scripts/train_model.py.')
    with db() as c:
        authorize_customer(c,u,body.customer_id)
        facts=records(c,'SELECT * FROM gold.customer_summary WHERE customer_id=?',[body.customer_id])[0]
        profile=records(c,'SELECT cease_communication_flag,internal_do_not_call_flag,bankruptcy_flag,consumer_proposal_flag,deceased_flag FROM gold.customers WHERE customer_id=?',[body.customer_id])[0]
        case_hold=c.execute('SELECT coalesce(bool_or(cease_contact_flag OR insolvency_hold_flag OR deceased_hold_flag),false) FROM gold.cases WHERE customer_id=? AND outcome IS NULL',[body.customer_id]).fetchone()[0]
        features=records(c,feature_sql(True),[body.customer_id])[0]
        note=records(c,'SELECT note_id,note_text,note_language,note_ts FROM gold.latest_notes WHERE customer_id=?',[body.customer_id])
    bundle=joblib.load(MODEL)
    vector=[[features[k] for k in bundle['features']]]
    probability=float(bundle['model'].predict_proba(vector)[0,1])
    spans=evidence(note[0]['note_text']) if note else []
    signals=[{'name':k,'value':features[k],'evidence':f"agent_notes:{features.get('note_id')}"} for k in TEXT_FEATURES if features[k]]
    signals += [{'name':'overdue_cad','value':facts['total_overdue'],'evidence':'collections_cases: open cases at snapshot'}, {'name':'max_dpd','value':facts['max_dpd'],'evidence':'collections_cases: current_dpd'}]
    hold=case_hold or any(profile[k] for k in ['bankruptcy_flag','consumer_proposal_flag','deceased_flag','cease_communication_flag'])
    french=(facts.get('preferred_language') or '').lower().startswith('fr')
    if hold:
        recommendation='Hold contact and route to a supervisor to verify the recorded restriction.'
        draft='Internal review only. Check the recorded contact or insolvency restriction before taking any action.'
        policy_sources=['POL-COLL-001 v3.0 §7.3','POL-COLL-004 v4.2 §4.2']
    elif probability>=.5 or spans:
        recommendation='Review the financial hardship evidence. Confirm affordability and eligible support options before requesting payment.'
        draft=('Je comprends que vos finances sont difficiles en ce moment. Nous pouvons examiner les options de soutien et un paiement abordable avec vous.' if french else 'I understand that money is difficult right now. We can review support options and an affordable payment together.')
        policy_sources=['POL-COLL-004 v4.2 §4.2','POL-COLL-004 v4.2 §4.3']
    else:
        recommendation='Review the latest case and confirm the customer’s circumstances before agreeing on a next step.'
        draft=('Examinons votre situation et discutons de la prochaine etape qui vous convient.' if french else 'Let’s review your situation and discuss a suitable next step together.')
        policy_sources=['POL-COLL-001 v3.0 §5.1','PRC-COLL-010 v2.1 §3.1']
    if profile['internal_do_not_call_flag']:
        recommendation+=' Internal do-not-call flag is recorded; do not initiate a call.'
    payload={'brief_id':str(uuid.uuid4()),'customer_id':body.customer_id,'summary':f"{facts['open_cases']} open case(s), CAD {facts['total_overdue']:,.2f} overdue. "+('Financial evidence: '+' '.join(spans) if spans else 'No supported financial text cue found in the latest note.'),'signals':signals,'recommendation':recommendation,'policy_sources':policy_sources,'draft':draft,'status':'pending','model':{'name':'Financial hardship review triage','version':VERSION,'review_probability':round(probability,4),'input_features':bundle['features']},'features':features}
    with storage.connect() as s:
        s.execute('INSERT INTO briefs(brief_id,customer_id,actor,payload,status,created_at) VALUES(?,?,?,?,?,?)',(payload['brief_id'],body.customer_id,u['username'],json.dumps(payload,default=str),'pending',storage.now()))
        storage.audit(s,u['username'],'generate_brief',payload['brief_id'],{'customer_id':body.customer_id,'model_version':VERSION,'policy_sources':policy_sources})
    return payload


def review_record(row):
    result=json.loads(row['payload']);result.update({k:row[k] for k in ['status','created_at','decision','reason','reviewer']});return result


@app.get('/api/reviews')
def reviews(u=Depends(user)):
    with storage.connect() as s:
        rows=s.execute('SELECT * FROM briefs'+(' WHERE actor=?' if u['role']=='agent' else '')+' ORDER BY created_at DESC LIMIT 100',[u['username']] if u['role']=='agent' else []).fetchall()
    return {'items':[review_record(r) for r in rows]}


class Review(BaseModel):
    decision:Literal['approve','reject','edit']
    reason:str=Field(min_length=3,max_length=1000)
    draft:str|None=Field(None,max_length=3000)


@app.post('/api/reviews/{brief_id}')
def decide(brief_id:str,body:Review,u=Depends(supervisor)):
    if not body.reason.strip():raise HTTPException(422,'A review reason is required.')
    if body.decision=='edit' and (not body.draft or not body.draft.strip()):raise HTTPException(422,'An edited draft is required.')
    with storage.connect() as s:
        s.execute('BEGIN IMMEDIATE')
        row=s.execute('SELECT * FROM briefs WHERE brief_id=?',(brief_id,)).fetchone()
        if not row:raise HTTPException(404,'Brief not found.')
        if row['status']!='pending':raise HTTPException(409,'This brief has already been reviewed.')
        payload=json.loads(row['payload'])
        if body.decision=='edit':payload['draft']=body.draft
        status={'approve':'approved','reject':'rejected','edit':'edited'}[body.decision]
        s.execute('UPDATE briefs SET payload=?,status=?,decision=?,reason=?,reviewer=? WHERE brief_id=?',(json.dumps(payload),status,body.decision,body.reason,u['username'],brief_id))
        storage.audit(s,u['username'],'review_'+body.decision,brief_id,{'customer_id':row['customer_id'],'reason':body.reason,'previous_draft':json.loads(row['payload'])['draft'],'final_draft':payload['draft']})
        updated=s.execute('SELECT * FROM briefs WHERE brief_id=?',(brief_id,)).fetchone()
    return review_record(updated)


@app.get('/api/audit')
def audit_log(u=Depends(supervisor)):
    with storage.connect() as s:items=[dict(r) for r in s.execute('SELECT event_id,at,actor,action,resource,details FROM audit ORDER BY event_id DESC LIMIT 100')]
    for item in items:item['details']=json.loads(item['details'])
    return {'items':items}


@app.get('/api/quality')
def quality(u=Depends(user)):
    if u['role']=='agent':raise HTTPException(403,'Data quality reports require an analyst or supervisor.')
    if not QUALITY.exists():raise HTTPException(503,'Dataset pipeline is not ready.')
    return json.loads(QUALITY.read_text())


@app.get('/api/features')
def feature_registry(u=Depends(user)):
    if u['role']=='agent':raise HTTPException(403,'The feature registry requires an analyst or supervisor.')
    p=ROOT/'data/features-report.json'
    result=json.loads(p.read_text()) if p.exists() else {'version':VERSION,'definitions':definitions(),'parity':{'checked':0,'mismatches':None}}
    if MODEL_REPORT.exists():
        report=json.loads(MODEL_REPORT.read_text());report.pop('restricted_fairness_audit',None);result['model']=report
    else:result['model']={'status':'not_trained'}
    return result
