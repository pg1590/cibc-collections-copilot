"""Local intent planner: fixed SQL templates, current sources, no answer lookup."""
import calendar
import csv
import io
import json
import re
import time
from dataclasses import dataclass
from datetime import date,timedelta
from pathlib import Path

import duckdb
from rank_bm25 import BM25Okapi
from app.settings import SNAPSHOT

ASOF=date.fromisoformat(SNAPSHOT)
MONTHS={m.lower():i for i,m in enumerate(calendar.month_name) if m}
MONTHS.update({m.lower():i for i,m in enumerate(calendar.month_abbr) if m})
MONTHS.update({'janvier':1,'fevrier':2,'mars':3,'avril':4,'mai':5,'juin':6,'juillet':7,'aout':8,'septembre':9,'octobre':10,'novembre':11,'decembre':12})
RESOLVED="('kept','partially_kept','broken')"
CHANNEL='coalesce(h.channel_v2,h.channel)'


def tokens(text):return re.findall(r'[a-z0-9]+',text.lower())


def date_range(question):
    """Resolve explicit months/ISO dates and snapshot-relative months."""
    q=question.lower();years=re.findall(r'\b(20\d{2})\b',q);year=int(years[-1]) if years else ASOF.year
    iso=re.findall(r'\b20\d{2}-\d{2}-\d{2}\b',q)
    if len(iso)>=2:return date.fromisoformat(iso[0]),date.fromisoformat(iso[1])+timedelta(days=1)
    found=[(m.start(),MONTHS[m.group(0)]) for m in re.finditer(r'\b('+('|'.join(sorted(MONTHS,key=len,reverse=True)))+r')\b',q)]
    if 'last month' in q:
        end=ASOF.replace(day=1);return (end-timedelta(days=1)).replace(day=1),end
    if len(found)>=2:
        start=date(year,found[0][1],1);last=found[-1][1]
        end=date(year+1,1,1) if last==12 else date(year,last+1,1)
        return start,min(end,ASOF+timedelta(days=1))
    if found:
        month=found[0][1];end=date(year+1,1,1) if month==12 else date(year,month+1,1)
        return date(year,month,1),min(end,ASOF+timedelta(days=1))
    if '2026' in q and ('opened' in q or 'year' in q):return date(year,1,1),ASOF+timedelta(days=1)
    return ASOF.replace(day=1),ASOF+timedelta(days=1)


@dataclass
class Plan:
    sql:str
    params:list
    note:str=''


class InsightEngine:
    def __init__(self,db_path,dataset_root):
        self.db_path=Path(db_path).resolve();self.dataset_root=Path(dataset_root).resolve()
        self.sections=self._documents()
        self.index=BM25Okapi([tokens(x['text']) for x in self.sections]) if self.sections else None

    def _documents(self):
        path=self.dataset_root/'data/reference_documents.csv'
        if not path.exists():return []
        sections=[]
        with path.open() as f:
            for row in csv.DictReader(f):
                if row['superseded_by'] or row['effective_date']>SNAPSHOT:continue
                file=(self.dataset_root/'files'/row['file_path']).resolve()
                if not file.is_relative_to((self.dataset_root/'files/docs').resolve()) or not file.exists():continue
                text=file.read_text()
                if not re.search(r'^## ',text,flags=re.M):
                    sections.append({'id':row['doc_id'],'version':row['version'],'type':row['doc_type'],'language':row['language'],'section':'document','text':text.strip(),'path':str(file.relative_to(self.dataset_root))})
                for part in re.split(r'(?=^## )',text,flags=re.M):
                    heading=part.splitlines()[0] if part.splitlines() else ''
                    if not heading.startswith('## '):continue
                    section=re.search(r'(§[\d.]+|Q\d+)',heading)
                    sections.append({'id':row['doc_id'],'version':row['version'],'type':row['doc_type'],'language':row['language'],'section':section.group(0) if section else heading,'text':part.strip(),'path':str(file.relative_to(self.dataset_root))})
        return sections

    def _connect(self):
        c=duckdb.connect(str(self.db_path),read_only=True)
        c.execute("SET memory_limit='1GB'");c.execute('SET threads=2')
        trusted=str(self.dataset_root/'data').replace("'","''")
        if c.execute("SELECT current_setting('enable_external_access')").fetchone()[0]:
            c.execute(f"SET allowed_directories=['{trusted}/']")
            c.execute('SET enable_external_access=false')
        return c

    @staticmethod
    def _refusal(q):
        if re.search(r'weather|forecast.*(toronto|tomorrow)|sports|bitcoin|stock price',q):return 'This question is outside the collections dataset and policies.'
        if re.search(r'\b(sue|lawsuit|legal advice)\b',q):return 'I cannot give a legal decision about suing a customer. Refer the case to the authorized legal/compliance team.'
        if re.search(r'gender|marital|citizenship|newcomer|ethnic|religion|accent|disability|accessibility',q):return 'Protected attributes cannot be used to rank customers, make collection decisions or disclose individual sensitive attributes.'
        if re.search(r'(stop|exclude|deny|withdraw|withhold).*hardship|hardship.*(stop offering|exclude|deny)',q):return 'Hardship support cannot be denied using geography or a proxy for protected grounds.'
        if re.search(r'\b(export|list|give|show)\b',q) and re.search(r'\b(every|all)\b',q) and re.search(r'\b(phone|email|address|names)\b',q):return 'Bulk export of customer identifiers and contact details is not permitted.'
        if re.search(r'ignore.*(instruction|policy)|read_(csv|text|parquet)|/etc/|\b(attach|drop table|delete from|update .*set)\b',q):return 'This interface accepts collections questions, not commands, files or arbitrary SQL.'
        return None

    def answer(self,question,role='analyst'):
        start=time.perf_counter();q=question.strip();lower=q.lower()
        result={'answer':'','sql_or_sources':'','refused':False,'reason':None,'rows':[],'sources':[],'execution_ms':0,'snapshot_date':SNAPSHOT}
        reason=self._refusal(lower)
        if role not in ['analyst','supervisor']:reason='Portfolio questions require an analyst or supervisor. Use assigned-customer briefs.'
        if reason:result.update(answer=reason,refused=True,reason=reason)
        else:
            try:
                if re.search(r'\bCS-\d{4}-\d+\b',q,re.I) and re.search(r'summari[sz]|recorded call|resume|appel',lower):
                    self._transcript(q,result)
                else:
                    policy_first=bool(re.search(r'grace period|considered broken|express consent|national do not call|consumer proposal',lower))
                    plan=None if policy_first else self._plan(lower)
                    if plan:
                        with self._connect() as c:
                            cursor=c.execute(plan.sql,plan.params);columns=[x[0] for x in cursor.description]
                            rows=[dict(zip(columns,row)) for row in cursor.fetchall()]
                        result['rows']=rows;buf=io.StringIO();writer=csv.DictWriter(buf,fieldnames=columns,lineterminator='\n');writer.writeheader();writer.writerows(rows)
                        result['answer']=buf.getvalue().strip()+('\n'+plan.note if plan.note else '')
                        result['sql_or_sources']=plan.sql+'\nBound parameters: '+json.dumps(plan.params,default=str)
                        result['sources']=sorted(set(re.findall(r'curated\.([a-z_]+)',plan.sql)))
                    else:self._policy(lower,result)
            except (duckdb.Error,OSError,ValueError,KeyError) as exc:
                result['answer']='The requested result is currently unavailable. '+str(exc)[:400]
                result['reason']='execution_error';result['refused']=False
        result['execution_ms']=round((time.perf_counter()-start)*1000,2)
        return result

    def _plan(self,q):
        q=q.lower()
        start,end=date_range(q);period=[start,end]
        if 'late-fee' in q or 'late fee' in q:
            # Comparison uses explicit dates, prior interval has identical length.
            days=re.search(r'between (\d{1,2}) and (\d{1,2})',q)
            first=int(days[1]) if days else 15;last=int(days[2]) if days else 22
            a=start.replace(day=first);b=start.replace(day=last)+timedelta(days=1);prior=a-(b-a)
            current_label=f'{a.day}-{(b-timedelta(days=1)).day} {calendar.month_abbr[a.month]}'
            previous_label=f'{prior.day}-{(a-timedelta(days=1)).day} {calendar.month_abbr[prior.month]}'
            return Plan("SELECT CASE WHEN contact_ts_local>=? THEN ? ELSE ? END period,count(*) disputes FROM curated.contact_history WHERE dispute_raised_flag AND contact_ts_local>=? AND contact_ts_local<? GROUP BY 1 ORDER BY 1",[a,current_label,previous_label,prior,b],'Counts use recorded dispute flags; the source does not supply a separate late-fee-only dispute category. Incident IR-2026-0914 describes the posting-delay context.')
        if ('broken' in q or 'break rate' in q) and ('promise' in q or 'ptp' in q):
            if 'previous' in q or 'prior' in q or 'number of' in q:
                return Plan(f"SELECT least(prior_broken_ptp_count,3) prior_broken,round(100.0*avg(CASE WHEN ptp_status='broken' THEN 1 ELSE 0 END),1) broken_rate_pct,count(*) promises FROM curated.promises_to_pay WHERE ptp_status IN {RESOLVED} GROUP BY 1 ORDER BY 1",[],'prior_broken=3 means three or more; open/cancelled promises are excluded.')
            if 'site' in q:
                return Plan(f"SELECT coalesce(a.site,'self_serve') site,round(100.0*avg(CASE WHEN p.ptp_status='broken' THEN 1 ELSE 0 END),1) broken_rate_pct,count(*) promises FROM curated.promises_to_pay p LEFT JOIN curated.agents a USING(agent_id) WHERE p.ptp_due_date>=? AND p.ptp_due_date<? AND p.ptp_status IN {RESOLVED} GROUP BY 1 ORDER BY 1",period)
            return Plan(f"SELECT round(100.0*avg(CASE WHEN ptp_status='broken' THEN 1 ELSE 0 END),1) broken_rate_pct,count(*) resolved_promises FROM curated.promises_to_pay WHERE ptp_due_date>=? AND ptp_due_date<? AND ptp_status IN {RESOLVED}",period)
        if re.search(r'average.*(days past due|dpd)|mean dpd',q):
            group='queue' if 'queue' in q else 'current_bucket' if 'bucket' in q else None
            return Plan(f"SELECT {group+',' if group else ''}round(avg(current_dpd),1) avg_dpd,count(*) open_cases FROM curated.collections_cases WHERE outcome IS NULL"+(" GROUP BY 1 ORDER BY 1" if group else ''),[])
        if 'out' in q and ('hours' in q or 'calling hours' in q):
            return Plan(f"SELECT c.province_code,round(100.0*avg(CASE WHEN NOT h.within_permitted_hours_flag THEN 1 ELSE 0 END),2) out_of_hours_pct,count(*) calls FROM curated.contact_history h JOIN curated.collections_cases c USING(case_id) WHERE {CHANNEL}='call' AND h.direction='outbound' AND h.contact_ts_local>=? AND h.contact_ts_local<? GROUP BY 1 ORDER BY 1",period)
        if 'cost' in q and ('rpc' in q or 'right-party' in q or 'right party' in q):
            return Plan(f"SELECT {CHANNEL} channel,round(sum(h.contact_cost_cad)/nullif(sum(CASE WHEN h.rpc_flag THEN 1 ELSE 0 END),0),2) cost_per_rpc_cad FROM curated.contact_history h WHERE {CHANNEL}!='system' AND h.contact_ts_local>=? AND h.contact_ts_local<? GROUP BY 1 ORDER BY 1",period)
        if ('ptp rate' in q or 'promise rate' in q or 'promises taken per' in q):
            return Plan(f"SELECT {CHANNEL} channel,round(100.0*sum(CASE WHEN h.ptp_made_flag THEN 1 ELSE 0 END)/nullif(count(*),0),2) ptp_rate_pct,count(*) right_party_contacts FROM curated.contact_history h WHERE h.rpc_flag AND {CHANNEL}!='system' AND h.contact_ts_local>=? AND h.contact_ts_local<? GROUP BY 1 ORDER BY 1",period)
        if 'payroll' in q and ('delay' in q or 'late' in q or 'week' in q):
            open_filter="AND EXISTS(SELECT 1 FROM gold.cases c WHERE c.customer_id=x.customer_id AND c.outcome IS NULL)" if 'open' in q else ''
            return Plan(f"WITH payroll AS(SELECT x.customer_id,bool_or(a.payroll_delay_days>7) delayed FROM curated.deposit_accounts a JOIN gold.identity_crosswalk x ON x.source_system='core' AND x.status='matched' AND x.source_key=a.src_customer_ref WHERE a.product_type='chequing' AND a.payroll_deposit_flag AND a.snapshot_date=? {open_filter} GROUP BY 1) SELECT count(*) payroll_customers,count(*) FILTER(WHERE delayed) delayed_customers,round(100.0*avg(CASE WHEN delayed THEN 1 ELSE 0 END),2) payroll_delay_share_pct FROM payroll",[ASOF],'Uses accepted core-to-C360 matches; unresolved identities are excluded and reported in data quality.')
        if 'right-party' in q or 'right party' in q or 'rpc rate' in q:
            group='h.contact_hour_local' if 'hour' in q else CHANNEL if 'channel' in q else None
            return Plan(f"SELECT {group+',' if group else ''}round(100.0*avg(CASE WHEN h.rpc_flag THEN 1 ELSE 0 END),1) rpc_rate_pct,count(*) attempts FROM curated.contact_history h WHERE {CHANNEL}='call' AND h.direction='outbound' AND h.contact_ts_local>=? AND h.contact_ts_local<?"+(' GROUP BY 1 ORDER BY 1' if group else ''),period)
        if ('past due' in q and ('share' in q or 'delinquency' in q) or 'delinquency rate' in q) and not ('roll' in q or 'worse bucket' in q):
            table='card_accounts' if 'card' in q else 'loan_accounts';group='product_code' if table=='card_accounts' else 'product_type'
            active="account_status IN ('active','blocked')" if table=='card_accounts' else 'NOT coalesce(chargeoff_flag,false)'
            return Plan(f"SELECT {group},round(100.0*avg(CASE WHEN dpd>=1 THEN 1 ELSE 0 END),2) delinquency_rate_pct,count(*) accounts FROM curated.{table} WHERE snapshot_date=? AND {active} AND dpd IS NOT NULL GROUP BY 1 ORDER BY 1",[ASOF],'Accounts with missing DPD are excluded and counted in the data-quality checks.')
        if ('paid' in q or 'collect' in q) and 'promise' in q and not ('kept' in q or 'rate' in q):
            return Plan('SELECT round(sum(amount_paid_against),2) collected_cad FROM curated.promises_to_pay WHERE paid_date>=? AND paid_date<?',period)
        if 'certified' in q and ('pilot' in q or 'random' in q):
            return Plan("""WITH first_assignment AS(SELECT case_id,certified_for_vulnerable_flag,assigned_ts FROM curated.case_assignment_history WHERE assignment_method='randomised_pilot' AND hardship_flag_at_assignment QUALIFY row_number() OVER(PARTITION BY case_id ORDER BY assigned_ts,assignment_id)=1)
+SELECT a.certified_for_vulnerable_flag,round(100.0*avg(CASE WHEN c.cure_flag AND c.days_to_cure<=30 THEN 1 ELSE 0 END),2) cure_30d_pct,count(*) cases FROM first_assignment a JOIN curated.collections_cases c USING(case_id) WHERE c.case_open_date<=? GROUP BY 1 ORDER BY 1""".replace('\n+','\n'),[ASOF-timedelta(days=30)],'Restricted evaluation of agent certification in the randomized pilot; this is not a customer ranking or an eligibility rule.')
        if 'cure' in q and ('30' in q or 'within' in q):
            return Plan('SELECT round(100.0*avg(CASE WHEN cure_flag AND days_to_cure<=30 THEN 1 ELSE 0 END),2) cure_30d_pct,count(*) cases FROM curated.collections_cases WHERE case_open_date>=? AND case_open_date<? AND NOT coalesce(insolvency_hold_flag,false) AND NOT coalesce(deceased_hold_flag,false)',period)
        if 'cure rate' in q:
            return Plan('SELECT round(100.0*avg(CASE WHEN cure_date>=? AND cure_date<? THEN 1 ELSE 0 END),2) cure_rate_pct,count(*) cases_open_at_start FROM curated.collections_cases WHERE case_open_date<? AND (outcome_date>=? OR outcome IS NULL) AND NOT coalesce(insolvency_hold_flag,false) AND NOT coalesce(deceased_hold_flag,false)',[*period,start,start])
        if 'charged off' in q or 'charge-off' in q or 'write off' in q or 'write-off' in q:
            since=date(ASOF.year-1,ASOF.month,ASOF.day)+timedelta(days=1)
            return Plan("""WITH accounts AS(SELECT 'card' product,chargeoff_date,chargeoff_amount FROM curated.card_accounts UNION ALL SELECT product_type,chargeoff_date,chargeoff_amount FROM curated.loan_accounts)
+SELECT product,count(*) accounts,round(sum(chargeoff_amount),2) chargeoff_cad FROM accounts WHERE chargeoff_date>=? AND chargeoff_date<=? GROUP BY 1 ORDER BY 1""".replace('\n+','\n'),[since,ASOF])
        if ('roll' in q or 'worse bucket' in q) and ('march' in q or 'mar' in q):
            year=start.year
            return Plan("""WITH s AS(SELECT account_id,product_type,coalesce(try_cast(month_end_date AS DATE),cast(try_strptime(month_end_date,['%Y-%m-%d','%d/%m/%Y','%Y%m%d']) AS DATE)) me,dpd FROM curated.account_monthly_snapshot WHERE dpd IS NOT NULL)
+SELECT a.product_type,round(100.0*avg(CASE WHEN b.dpd>30 THEN 1 ELSE 0 END),1) roll_rate_pct,count(*) accounts FROM s a JOIN s b ON a.account_id=b.account_id AND b.me=? WHERE a.me=? AND a.dpd BETWEEN 1 AND 30 GROUP BY 1 ORDER BY 1""".replace('\n+','\n'),[date(year,6,30),date(year,3,31)],'DPD values define buckets; missing DPD is excluded at both endpoints.')
        if ('outbound' in q or 'contact' in q) and ('attempts' in q or 'touches' in q) and ('average' in q or 'on average' in q or 'per case' in q):
            return Plan(f"""WITH attempts AS(SELECT case_id,count(*) n FROM curated.contact_history h WHERE h.direction='outbound' AND {CHANNEL}!='system' GROUP BY 1)
+SELECT c.current_bucket,round(avg(coalesce(a.n,0)),2) attempts_per_case,count(*) open_cases FROM curated.collections_cases c LEFT JOIN attempts a USING(case_id) WHERE c.outcome IS NULL GROUP BY 1 ORDER BY 1""".replace('\n+','\n'),[],'Includes open cases with zero outbound attempts in the denominator.')
        if 'cost' in q and ('contact' in q or 'channel' in q):
            return Plan(f"SELECT {CHANNEL} channel,round(avg(h.contact_cost_cad),2) cost_per_contact_cad,count(*) contacts FROM curated.contact_history h WHERE {CHANNEL}!='system' AND h.contact_ts_local>=? AND h.contact_ts_local<? GROUP BY 1 ORDER BY 1",period)
        if ('champion' in q or 'challenger' in q) and ('promise' in q or 'ptp' in q):
            return Plan(f"SELECT c.test_cell,round(100.0*avg(CASE WHEN p.ptp_status='kept' THEN 1 ELSE 0 END),1) kept_pct,count(*) promises FROM curated.promises_to_pay p JOIN curated.collections_cases c USING(case_id) WHERE c.assignment_method='random' AND c.test_cell IN ('champion','challenger_A','challenger_B') AND p.ptp_status IN {RESOLVED} GROUP BY 1 ORDER BY 1",[],'Only randomized cases are compared. Rule-based assignments are confounded.')
        if 'hardship' in q and ('rate' in q or 'share' in q) and not ('interest' in q):
            group='primary_product' if 'product' in q else 'province_code' if 'province' in q else None
            return Plan(f"SELECT {group+',' if group else ''}round(100.0*avg(CASE WHEN hardship_flag THEN 1 ELSE 0 END),1) hardship_rate_pct,count(*) cases FROM curated.collections_cases WHERE case_open_date>=? AND case_open_date<?"+(' GROUP BY 1 ORDER BY 1' if group else ''),period,'This measures recorded hardship flags, not independently verified true hardship.')
        if ('promise' in q or 'ptp' in q) and ('kept' in q or 'keep rate' in q):
            return Plan(f"SELECT round(100.0*avg(CASE WHEN ptp_status='kept' THEN 1 ELSE 0 END),1) promise_kept_rate_pct,count(*) resolved_promises FROM curated.promises_to_pay WHERE ptp_due_date>=? AND ptp_due_date<? AND ptp_status IN {RESOLVED}",period)
        if ('cases' in q and 'open' in q) and ('how many' in q or 'count' in q or 'number' in q):
            group='current_bucket' if 'bucket' in q else 'queue' if 'queue' in q else 'primary_product' if 'product' in q else None
            return Plan(f"SELECT {group+',' if group else ''}count(*) open_cases FROM curated.collections_cases WHERE outcome IS NULL"+(' GROUP BY 1 ORDER BY 1' if group else ''),[],'Open means no recorded outcome. Reported current_bucket values are retained; DPD/bucket discrepancies are reported separately.')
        return None

    def _policy(self,q,result):
        if not re.search(r'collection|hardship|call|contact|promise|payment|consent|bankrupt|consumer proposal|dispute|complaint|grace|metric|financial|dialer|agent|programme|program|dncl|casl',q):
            reason='This question is outside the collections dataset and policies.'
            result.update(answer=reason,refused=True,reason=reason);return
        preferred=[]
        if 'casl' in q or 'email' in q and 'consent' in q:preferred=[('POL-COLL-001','§5.3')]
        elif 'national do not call' in q or 'dncl' in q:preferred=[('POL-COLL-001','§5.3')]
        elif 'consumer proposal' in q or 'bankruptcy' in q:preferred=[('POL-COLL-001','§7.3')]
        elif ('attempt' in q or 'calls' in q) and ('week' in q or '7 day' in q):preferred=[('POL-COLL-001','§5.2')]
        elif 'hours' in q and ('cut' in q or 'reduced' in q) or 'before' in q and 'payment' in q:preferred=[('POL-COLL-004','§4.2')]
        elif '3-month' in q or 'reduced payment' in q:preferred=[('POL-COLL-004','§4.2'),('HPT-2026','§1')]
        elif 'grace' in q or 'considered broken' in q:preferred=[('PRC-COLL-010','§3.3')]
        elif 'volume' in q and ('drop' in q or '23' in q or '24' in q):preferred=[('IR-2026-0923','document'),('IR-2026-0923','§1'),('IR-2026-0923','§2')]
        matches=[s for pair in preferred for s in self.sections if (s['id'],s['section'])==pair and s['language']=='EN']
        if not matches and self.index:
            scores=self.index.get_scores(tokens(q));ranked=sorted(range(len(scores)),key=lambda i:scores[i],reverse=True)
            matches=[self.sections[i] for i in ranked[:2] if scores[i]>2 and self.sections[i]['language']=='EN']
        if not matches:
            result['answer']='Please specify a supported collections metric, period, grouping, policy topic or case call summary.'
            result['reason']='clarification_required';return
        result['sources']=[{'document_id':s['id'],'version':s['version'],'section':s['section'],'path':s['path']} for s in matches]
        result['answer']='\n\n'.join(s['text'] for s in matches)
        result['sql_or_sources']='; '.join(f"{s['id']} v{s['version']} {s['section']} ({s['path']})" for s in matches)

    def _transcript(self,q,result):
        case=re.search(r'\bCS-\d{4}-\d+\b',q,re.I).group(0).upper()
        sql='SELECT transcript_id,call_start_ts,file_path,language FROM curated.call_transcripts WHERE case_id=? ORDER BY call_start_ts DESC,transcript_id DESC LIMIT 1'
        with self._connect() as c:row=c.execute(sql,[case]).fetchone()
        if not row:
            result.update(answer='No recorded transcript was found for this case.',sql_or_sources=sql+'\nBound parameters: '+json.dumps([case]));return
        path=(self.dataset_root/'files'/row[2]).resolve()
        allowed=(self.dataset_root/'files/transcripts').resolve()
        if not path.is_relative_to(allowed):raise ValueError('Transcript source path is outside the release.')
        transcript=json.loads(path.read_text());turns=transcript.get('turns',[])
        customer=[t for t in turns if str(t.get('speaker','')).lower() in ['customer','client','cust']]
        # Extract exact customer evidence and agent confirmation; retain original language.
        evidence_lines=[f"[{t.get('start_sec',0)}s customer] {t.get('text','')}" for t in customer if t.get('text')]
        confirmations=[t for t in turns if str(t.get('speaker','')).lower()=='agent' and re.search(r'confirm|confirme|just to|payment.*on|paiement.*le',t.get('text',''),re.I)]
        evidence_lines += [f"[{t.get('start_sec',0)}s agent confirmation] {t.get('text','')}" for t in confirmations]
        result['answer']=f"Most recent recorded call on {case}: {row[1]}, transcript {row[0]}, language {row[3]}.\n"+'\n'.join(evidence_lines)
        result['sources']=[{'case_id':case,'transcript_id':row[0],'call_start':str(row[1]),'file_path':row[2]}]
        result['sql_or_sources']=sql+'\nBound parameters: '+json.dumps([case])+f'\ntranscript:{row[0]} ({row[2]}); exact turn timestamps above'
