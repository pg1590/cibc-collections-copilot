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
from app.metric_plans import CATALOG, PlanError, PlanRefusal, compile_plan
from app.gemini import ProviderUnavailable
from app.policy_summary import summarize_policy, summarize_transcript

ASOF=date.fromisoformat(SNAPSHOT)
MONTHS={m.lower():i for i,m in enumerate(calendar.month_name) if m}
MONTHS.update({m.lower():i for i,m in enumerate(calendar.month_abbr) if m})
MONTHS.update({'janvier':1,'fevrier':2,'mars':3,'avril':4,'mai':5,'juin':6,'juillet':7,'aout':8,'septembre':9,'octobre':10,'novembre':11,'decembre':12})
RESOLVED="('kept','partially_kept','broken')"
CHANNEL='coalesce(h.channel_v2,h.channel)'
PROVINCE_NAMES={'ontario':'ON','quebec':'QC','québec':'QC','alberta':'AB','manitoba':'MB','saskatchewan':'SK','british columbia':'BC','nova scotia':'NS','new brunswick':'NB','newfoundland':'NL','labrador':'NL','prince edward island':'PE','yukon':'YT','northwest territories':'NT','nunavut':'NU'}


def province_filter(q):
    """Accept one positive province; clarify exclusions and combined regions."""
    provinces={code for name,code in PROVINCE_NAMES.items() if re.search(r'\b'+name+r'\b',q)}
    codes=r'(?:on|qc|ab|bc|mb|sk|ns|nb|nl|pe|yt|nt|nu)'
    for match in re.finditer(r'\b(?:in|from|provinces?)\s+('+codes+r'\b(?:\s*(?:,|/|&|\band\b|\bor\b)\s*'+codes+r'\b)*)',q):
        provinces.update(code.upper() for code in re.findall(r'\b'+codes+r'\b',match[1]))
    for name in PROVINCE_NAMES:
        for match in re.finditer(r'\b'+name+r'\s*(?:,|/|&|\band\b|\bor\b)\s*('+codes+r')\b',q):
            provinces.add(match[1].upper())
    if len(provinces)>1 or re.search(r'\b(toronto|halifax|montreal|montréal|winnipeg|vancouver|calgary|edmonton|ottawa)\b',q):
        raise PlanError('Only one province can be used as a filter. A named city or site needs clarification; request a single province or a supported grouping.')
    if provinces and re.search(r'\b(?:excluding|exclude|except|outside|without|other than|apart from|not in|not from)\b',q):
        raise PlanError('Province exclusions are unsupported. Request one included province or a supported grouping.')
    return {'province':provinces.pop()} if provinces else {}


def tokens(text):return re.findall(r'[a-z0-9]+',text.lower())


def month_mentions(q):
    return [m for m in re.finditer(r'\b('+('|'.join(sorted(MONTHS,key=len,reverse=True)))+r')\b',q)
            if m.group(0)!='may' or re.search(r'\b(in|for|during|of|end of|from|to|through)\s+may\b|\bmay\s+\d{1,4}\b|[-–]\s*may\b',q)]


def explicit_period(q):
    return bool(month_mentions(q) or re.search(r'\b20\d{2}\b|\bq[1-4]\b|last month|previous month|this month|this year|last year|since',q))


def prior_broken_cohort(q):
    return bool(re.search(r'(?:previously|prior|previous)\s+broken\s+(?:promises?|ptps?)',q))


def thirty_day_cure(q):
    return 'cure' in q and bool(re.search(r'within\s+30\s+days?|30[- ]day\s+cure|cure.*in\s+30\s+days?',q))


def date_range(question):
    """Resolve explicit months/ISO dates and snapshot-relative months."""
    q=question.lower();years=re.findall(r'\b(20\d{2})\b',q);year=int(years[-1]) if years else ASOF.year
    iso=re.findall(r'\b20\d{2}-\d{2}-\d{2}\b',q)
    if iso:
        try:parsed=[date.fromisoformat(x) for x in iso]
        except ValueError:raise PlanError('Please use valid ISO calendar dates.') from None
        if len(parsed)==2:
            if parsed[0]>parsed[1]:raise PlanError('The period start must precede the end.')
            return parsed[0],parsed[1]+timedelta(days=1)
        if len(parsed)>2:raise PlanError('Please specify exactly two period endpoints.')
        if re.search(r'\bsince\b|\bfrom\b',q):return parsed[0],ASOF+timedelta(days=1)
        if re.search(r'\bon\b|\bas of\b',q):return parsed[0],parsed[0]+timedelta(days=1)
        raise PlanError('For a single date, specify on that date or since that date; otherwise provide two ISO endpoints.')
    found=[(m.start(),MONTHS[m.group(0)]) for m in month_mentions(q)]
    if len(set(years))>1:raise PlanError('For a period spanning different years, please provide two ISO date endpoints.')
    if 'last month' in q or 'previous month' in q:
        end=ASOF.replace(day=1);return (end-timedelta(days=1)).replace(day=1),end
    quarter=re.search(r'\bq([1-4])\b',q)
    if quarter:
        month=(int(quarter[1])-1)*3+1;start=date(year,month,1)
        end=date(year+1,1,1) if month==10 else date(year,month+3,1)
        return start,min(end,ASOF+timedelta(days=1))
    if len(found)>=2:
        start=date(year,found[0][1],1);last=found[-1][1]
        end=date(year+1,1,1) if last==12 else date(year,last+1,1)
        return start,min(end,ASOF+timedelta(days=1))
    if found:
        month=found[0][1];end=date(year+1,1,1) if month==12 else date(year,month+1,1)
        return date(year,month,1),min(end,ASOF+timedelta(days=1))
    if 'last year' in q:return date(ASOF.year-1,1,1),date(ASOF.year,1,1)
    if years or 'this year' in q:return date(year,1,1),min(date(year+1,1,1),ASOF+timedelta(days=1))
    return ASOF.replace(day=1),ASOF+timedelta(days=1)


@dataclass
class Plan:
    sql:str
    params:list
    note:str=''
    metadata:dict=None


class InsightEngine:
    def __init__(self,db_path,dataset_root,planner=None):
        self.db_path=Path(db_path).resolve();self.dataset_root=Path(dataset_root).resolve()
        self.planner=planner
        self.sections=self._documents()
        self.index=BM25Okapi([tokens(x['text']) for x in self.sections]) if self.sections else None

    def _documents(self):
        path=self.dataset_root/'data/reference_documents.csv'
        if not path.exists():return []
        sections=[]
        with path.open(encoding='utf-8-sig',newline='') as f:
            for row in csv.DictReader(f):
                if row['superseded_by'] or row['effective_date']>SNAPSHOT:continue
                file=(self.dataset_root/'files'/row['file_path']).resolve()
                if not file.is_relative_to((self.dataset_root/'files/docs').resolve()) or not file.exists():continue
                text=file.read_text(encoding='utf-8')
                if not re.search(r'^## ',text,flags=re.M):
                    sections.append({'id':row['doc_id'],'version':row['version'],'type':row['doc_type'],'language':row['language'],'section':'document','text':text.strip(),'path':file.relative_to(self.dataset_root).as_posix()})
                for part in re.split(r'(?=^## )',text,flags=re.M):
                    heading=part.splitlines()[0] if part.splitlines() else ''
                    if not heading.startswith('## '):continue
                    section=re.search(r'(§[\d.]+|Q\d+)',heading)
                    sections.append({'id':row['doc_id'],'version':row['version'],'type':row['doc_type'],'language':row['language'],'section':section.group(0) if section else heading,'text':part.strip(),'path':file.relative_to(self.dataset_root).as_posix()})
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
        protected=re.search(r'\b(gender|marital|citizenship|newcomer|household|vulnerability|ethnic\w*|religion|accent|disability|accessibility|age|race|sex)\b|customers?\s+(?:over|under|older than|younger than)\s+\d+',q)
        decision=r'\brank|prioriti[sz]|\btarget|\bexclude|\bdeny|called first|call.*first'
        if protected and re.search(decision+r'|\blist|\bexport|\bshow|\bby\b|\bdisclose',q):return 'Protected attributes cannot be used to rank customers, make collection decisions or disclose individual sensitive attributes.'
        # Language is a servicing attribute; refuse it only as a decision input, not as a reporting breakdown.
        if re.search(r'\b(language|french|english|francophone|anglophone)\b',q) and re.search(decision,q):return 'Protected attributes cannot be used to rank customers, make collection decisions or disclose individual sensitive attributes.'
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
                    policy_first=bool(re.search(r'grace period|(?:considered|counts? as|treated as|deemed)\s+(?:a\s+)?broken|express consent|national do not call|consumer proposal',lower) or (re.search(r'\bpolicy|procedure|programme|program\b',lower) and not re.search(r'\brate\b|\bshare\b|\baverage\b',lower)))
                    plan=None if policy_first else self._plan(lower)
                    if plan is None and not policy_first and self.planner:
                        try:
                            plan=compile_plan(self.planner(q,CATALOG))
                        except ProviderUnavailable:
                            pass  # Optional provider failures keep local retrieval available.
                        except PlanError as exc:
                            self._policy(lower,result)
                            if not result.get('sources'):
                                if isinstance(exc,PlanRefusal):result.update(answer=str(exc),refused=True,reason='provider_refusal')
                                else:result.update(answer='Please specify a supported collections metric, grouping and period, or a policy topic.',refused=False,reason='clarification_required')
                    if plan:
                        with self._connect() as c:
                            cursor=c.execute(plan.sql,plan.params);columns=[x[0] for x in cursor.description]
                            rows=[dict(zip(columns,row)) for row in cursor.fetchall()]
                        result['rows']=rows;buf=io.StringIO();writer=csv.DictWriter(buf,fieldnames=columns,lineterminator='\n');writer.writeheader();writer.writerows(rows)
                        result['answer']=buf.getvalue().strip()+('\n'+plan.note if plan.note else '')
                        result['sql_or_sources']=plan.sql+'\nBound parameters: '+json.dumps(plan.params,default=str)
                        result['sources']=sorted(set(re.findall(r'curated\.([a-z_]+)',plan.sql)))
                        if getattr(plan,'metadata',None):result['plan']=plan.metadata
                    elif not result['answer']:self._policy(lower,result)
            except PlanError as exc:
                result.update(answer=str(exc),reason='clarification_required')
            except (duckdb.Error,OSError,ValueError,KeyError) as exc:
                result['answer']='The requested result is currently unavailable. '+str(exc)[:400]
                result['reason']='execution_error';result['refused']=False
        result['execution_ms']=round((time.perf_counter()-start)*1000,2)
        return result

    def _plan(self,q):
        q=q.lower()
        start,end=date_range(q);period=[start,end]
        if start>=end:raise PlanError('The requested period is reversed or falls after the dataset snapshot.')
        if re.search(r'\bpilot\b',q) and re.search(r'certified|randomi[sz]ed',q) and not ('certified' in q and 'cure' in q and 'hardship' in q):
            raise PlanError('The supported pilot comparison measures 30-day cure from first assignment on recorded-hardship cases, grouped by agent certification. Other pilot cohorts need clarification.')
        if re.search(r'champion|challenger',q) and not re.search(r'promise|ptp',q):raise PlanError('The supported randomized strategy comparison measures promise-kept rate; other strategy metrics need a defined cohort.')
        generic=self._generic_plan(q,start,end)
        if generic:return generic
        if 'late-fee' in q or 'late fee' in q:
            # Comparison uses explicit dates, prior interval has identical length.
            days=re.search(r'between (\d{1,2}) and (\d{1,2})',q)
            if not days:raise PlanError('Please specify the two days and month for the late-fee dispute comparison.')
            first=int(days[1]);last=int(days[2])
            if first>last:raise PlanError('The comparison end day must follow the start day.')
            try:a=start.replace(day=first);b=start.replace(day=last)+timedelta(days=1)
            except ValueError:raise PlanError('Please use valid calendar days for the comparison.') from None
            prior=a-(b-a)
            if b>ASOF+timedelta(days=1):raise PlanError('The requested dispute comparison extends beyond the dataset snapshot.')
            current_label=f'{a.day}-{(b-timedelta(days=1)).day} {calendar.month_abbr[a.month]}'
            previous_label=f'{prior.day}-{(a-timedelta(days=1)).day} {calendar.month_abbr[prior.month]}'
            return Plan("SELECT CASE WHEN contact_ts_local>=? THEN ? ELSE ? END period,count(*) disputes FROM curated.contact_history WHERE dispute_raised_flag AND contact_ts_local>=? AND contact_ts_local<? GROUP BY 1 ORDER BY 1",[a,current_label,previous_label,prior,b],'Counts use recorded dispute flags; the source does not supply a separate late-fee-only dispute category. Incident IR-2026-0914 describes the posting-delay context.')
        if ('broken' in q or 'break rate' in q) and ('promise' in q or 'ptp' in q):
            if prior_broken_cohort(q):
                dated=explicit_period(q)
                return Plan(f"SELECT least(prior_broken_ptp_count,3) prior_broken,round(100.0*avg(CASE WHEN ptp_status='broken' THEN 1 ELSE 0 END),1) broken_rate_pct,count(*) promises FROM curated.promises_to_pay WHERE ptp_status IN {RESOLVED}"+(' AND ptp_due_date>=? AND ptp_due_date<?' if dated else '')+' GROUP BY 1 ORDER BY 1',period if dated else [],'prior_broken=3 means three or more; open/cancelled promises excluded. '+('Uses the requested due-date period.' if dated else 'Uses all resolved promises in the extract; no period was supplied.'))
            if 'site' in q:
                return Plan(f"SELECT coalesce(a.site,'self_serve') site,round(100.0*avg(CASE WHEN p.ptp_status='broken' THEN 1 ELSE 0 END),1) broken_rate_pct,count(*) promises FROM curated.promises_to_pay p LEFT JOIN curated.agents a USING(agent_id) WHERE p.ptp_due_date>=? AND p.ptp_due_date<? AND p.ptp_status IN {RESOLVED} GROUP BY 1 ORDER BY 1",period)
            return Plan(f"SELECT round(100.0*avg(CASE WHEN ptp_status='broken' THEN 1 ELSE 0 END),1) broken_rate_pct,count(*) resolved_promises FROM curated.promises_to_pay WHERE ptp_due_date>=? AND ptp_due_date<? AND ptp_status IN {RESOLVED}",period)
        if re.search(r'average.*(days past due|dpd)|mean dpd',q):
            group='queue' if 'queue' in q else 'current_bucket' if 'bucket' in q else None
            return Plan(f"SELECT {group+',' if group else ''}round(avg(current_dpd),1) avg_dpd,count(*) open_cases FROM curated.collections_cases WHERE outcome IS NULL"+(" GROUP BY 1 ORDER BY 1" if group else ''),[])
        if re.search(r'\boutside\b|\bout[- ]of[- ]hours\b',q) and ('hours' in q or 'calling hours' in q):
            if re.search(r'\bby\b',q) and not re.search(r'\bby (?:customer )?province',q):raise PlanError('Out-of-hours calling supports grouping by customer province only.')
            return Plan(f"SELECT c.province_code,round(100.0*avg(CASE WHEN NOT h.within_permitted_hours_flag THEN 1 ELSE 0 END),2) out_of_hours_pct,count(*) calls FROM curated.contact_history h JOIN curated.collections_cases c USING(case_id) WHERE {CHANNEL}='call' AND h.direction='outbound' AND h.contact_ts_local>=? AND h.contact_ts_local<? GROUP BY 1 ORDER BY 1",period)
        if 'cost' in q and ('rpc' in q or 'right-party' in q or 'right party' in q):
            return Plan(f"SELECT {CHANNEL} channel,round(sum(h.contact_cost_cad)/nullif(sum(CASE WHEN h.rpc_flag THEN 1 ELSE 0 END),0),2) cost_per_rpc_cad FROM curated.contact_history h WHERE {CHANNEL}!='system' AND h.contact_ts_local>=? AND h.contact_ts_local<? GROUP BY 1 ORDER BY 1",period)
        if ('ptp rate' in q or 'promise rate' in q or 'promises taken per' in q):
            return Plan(f"SELECT {CHANNEL} channel,round(100.0*sum(CASE WHEN h.ptp_made_flag THEN 1 ELSE 0 END)/nullif(count(*),0),2) ptp_rate_pct,count(*) right_party_contacts FROM curated.contact_history h WHERE h.rpc_flag AND {CHANNEL}!='system' AND h.contact_ts_local>=? AND h.contact_ts_local<? GROUP BY 1 ORDER BY 1",period)
        if 'payroll' in q and ('delay' in q or 'late' in q or 'week' in q):
            if re.search(r'\bby\b',q) or explicit_period(q):raise PlanError(f'This payroll calculation supports an ungrouped {SNAPSHOT} customer snapshot. Historical or grouped payroll cohorts need clarification.')
            open_filter="AND EXISTS(SELECT 1 FROM gold.cases c WHERE c.customer_id=x.customer_id AND c.outcome IS NULL)" if 'open' in q else ''
            return Plan(f"WITH payroll AS(SELECT x.customer_id,bool_or(a.payroll_delay_days>7) delayed FROM curated.deposit_accounts a JOIN gold.identity_crosswalk x ON x.source_system='core' AND x.status='matched' AND x.source_key=a.src_customer_ref WHERE a.product_type='chequing' AND a.payroll_deposit_flag AND a.snapshot_date=? {open_filter} GROUP BY 1) SELECT count(*) payroll_customers,count(*) FILTER(WHERE delayed) delayed_customers,round(100.0*avg(CASE WHEN delayed THEN 1 ELSE 0 END),2) payroll_delay_share_pct FROM payroll",[ASOF],'Uses accepted core-to-C360 matches; unresolved identities are excluded and reported in data quality.')
        if 'right-party' in q or 'right party' in q or 'rpc rate' in q:
            group='h.contact_hour_local' if 'hour' in q else CHANNEL if 'channel' in q else None
            return Plan(f"SELECT {group+',' if group else ''}round(100.0*avg(CASE WHEN h.rpc_flag THEN 1 ELSE 0 END),1) rpc_rate_pct,count(*) attempts FROM curated.contact_history h WHERE {CHANNEL}='call' AND h.direction='outbound' AND h.contact_ts_local>=? AND h.contact_ts_local<?"+(' GROUP BY 1 ORDER BY 1' if group else ''),period)
        if ('past due' in q and ('share' in q or 'delinquency' in q) or 'delinquency rate' in q) and not ('roll' in q or 'worse bucket' in q):
            table='card_accounts' if 'card' in q else 'loan_accounts';group='product_code' if table=='card_accounts' else 'product_type'
            active="account_status IN ('active','blocked')" if table=='card_accounts' else 'NOT coalesce(chargeoff_flag,false)'
            return Plan(f"SELECT {group},round(100.0*avg(CASE WHEN dpd>=1 THEN 1 ELSE 0 END),2) delinquency_rate_pct,count(*) accounts FROM curated.{table} WHERE snapshot_date=? AND {active} AND dpd IS NOT NULL GROUP BY 1 ORDER BY 1",[ASOF],'Accounts with missing DPD are excluded and counted in the data-quality checks.')
        if re.search(r'\bpaid\b|\bcollect(?:ed)?\b',q) and 'promise' in q and not ('kept' in q or 'rate' in q):
            if re.search(r'\bby\b',q):raise PlanError('The supported promise-payment total is ungrouped. Please request the total or clarify the required payment cohort.')
            return Plan('SELECT round(sum(amount_paid_against),2) collected_cad FROM curated.promises_to_pay WHERE paid_date>=? AND paid_date<?',period,'Payment amounts recorded against promises only; this does not include all collection-account payments.')
        if 'certified' in q and ('pilot' in q or 'random' in q):
            if re.search(r'\bby\b',q) or explicit_period(q):raise PlanError('The supported pilot comparison uses all mature first assignments and groups only by agent certification; custom periods/groupings need clarification.')
            return Plan("""WITH first_assignment AS(SELECT case_id,certified_for_vulnerable_flag,assigned_ts,hardship_flag_at_assignment FROM curated.case_assignment_history WHERE assignment_method='randomised_pilot' QUALIFY row_number() OVER(PARTITION BY case_id ORDER BY assigned_ts,assignment_id)=1)
+SELECT a.certified_for_vulnerable_flag,round(100.0*avg(CASE WHEN c.cure_flag AND c.cure_date>=cast(a.assigned_ts AS DATE) AND c.cure_date<=cast(a.assigned_ts AS DATE)+30 THEN 1 ELSE 0 END),2) cure_30d_pct,count(*) cases FROM first_assignment a JOIN curated.collections_cases c USING(case_id) WHERE a.hardship_flag_at_assignment AND cast(a.assigned_ts AS DATE)<=? AND NOT coalesce(c.insolvency_hold_flag,false) AND NOT coalesce(c.deceased_hold_flag,false) GROUP BY 1 ORDER BY 1""".replace('\n+','\n'),[ASOF-timedelta(days=30)],'Observed 30-day cures measured from first randomized pilot assignment, when the certification treatment starts; only assignments with 30 observed days are included. Hardship is recorded at the first assignment. Current insolvency/deceased holds are excluded in line with the cure definition; historical hold status is unavailable. This descriptive comparison does not establish causality or customer eligibility.')
        if thirty_day_cure(q):
            if re.search(r'\bby\b|\bhardship\b|\b1\s*[-–]\s*30\b',q):raise PlanError('The 30-day opening cohort currently supports the ungrouped source population, excluding insolvency/deceased holds.')
            return Plan('SELECT round(100.0*avg(CASE WHEN cure_flag AND days_to_cure<=30 THEN 1 ELSE 0 END),2) cure_30d_pct,count(*) cases FROM curated.collections_cases WHERE case_open_date>=? AND case_open_date<? AND case_open_date<=? AND NOT coalesce(insolvency_hold_flag,false) AND NOT coalesce(deceased_hold_flag,false)',[*period,ASOF-timedelta(days=30)],'Cures within 30 days of opening; only cases with 30 observed days by the snapshot. Current insolvency/deceased holds excluded.')
        if 'cure rate' in q:
            return Plan('SELECT round(100.0*avg(CASE WHEN cure_date>=? AND cure_date<? THEN 1 ELSE 0 END),2) cure_rate_pct,count(*) cases_open_at_start FROM curated.collections_cases WHERE case_open_date<? AND (outcome_date>=? OR outcome IS NULL) AND NOT coalesce(insolvency_hold_flag,false) AND NOT coalesce(deceased_hold_flag,false)',[*period,start,start])
        if 'charged off' in q or 'charge-off' in q or 'write off' in q or 'write-off' in q:
            if re.search(r'\bby\b',q) and not re.search(r'\bby (?:primary )?product',q):raise PlanError('Charge-off counts and amounts support grouping by product only.')
            trailing=bool(re.search(r'12\s+months|last year',q)) or not explicit_period(q)
            since=date(ASOF.year-1,ASOF.month,ASOF.day)+timedelta(days=1) if trailing else start
            until=ASOF if trailing else end-timedelta(days=1)
            return Plan("""WITH accounts AS(SELECT 'card' product,chargeoff_date,chargeoff_amount FROM curated.card_accounts UNION ALL SELECT product_type,chargeoff_date,chargeoff_amount FROM curated.loan_accounts)
+SELECT product,count(*) accounts,round(sum(chargeoff_amount),2) chargeoff_cad FROM accounts WHERE chargeoff_date>=? AND chargeoff_date<=? GROUP BY 1 ORDER BY 1""".replace('\n+','\n'),[since,until],f'Charge-off counts and amounts by product from {since} through {until}; this is not the write-off rate.')
        if ('roll' in q or 'worse bucket' in q):
            months=[MONTHS[m.group(0)] for m in re.finditer(r'\b('+('|'.join(sorted(MONTHS,key=len,reverse=True)))+r')\b',q)]
            if len(months)!=2:raise PlanError('Roll rate needs two explicit month-end snapshots and a starting DPD bucket.')
            first=date(start.year,months[0],calendar.monthrange(start.year,months[0])[1]);last=date(start.year,months[1],calendar.monthrange(start.year,months[1])[1])
            if first>=last or last>date(2026,6,30):raise PlanError('Available monthly snapshots end on 30 June 2026. Choose two ordered month ends within that coverage.')
            if not re.search(r'1\s*[-–]\s*30',q):raise PlanError('This roll-rate calculation supports accounts starting at 1–30 DPD. Please specify that cohort.')
            buckets=re.findall(r'\b(\d+)\s*[-–]\s*(\d+)\b',q)
            if any((a,b) not in [('1','30'),('31','60')] for a,b in buckets):raise PlanError('Supported roll destinations are any worse bucket, or specifically 31–60 DPD; other destinations need a reviewed cohort.')
            if re.search(r'\bby\b',q) and not re.search(r'\bby\s+(?:primary\s+)?product',q):raise PlanError('This roll-rate calculation supports grouping by product only.')
            destination='b.dpd BETWEEN 31 AND 60' if re.search(r'31\s*[-–]\s*60',q) else 'b.dpd>30'
            return Plan("""WITH s AS(SELECT account_id,product_type,coalesce(try_cast(month_end_date AS DATE),cast(try_strptime(month_end_date,['%Y-%m-%d','%d/%m/%Y','%Y%m%d']) AS DATE)) me,dpd FROM curated.account_monthly_snapshot WHERE dpd IS NOT NULL)
+SELECT a.product_type,round(100.0*avg(CASE WHEN DESTINATION THEN 1 ELSE 0 END),1) roll_rate_pct,count(*) accounts FROM s a JOIN s b ON a.account_id=b.account_id AND b.me=? WHERE a.me=? AND a.dpd BETWEEN 1 AND 30 GROUP BY 1 ORDER BY 1""".replace('\n+','\n').replace('DESTINATION',destination),[last,first],'Matched-account cohort with known DPD at both requested month ends; missing endpoints are excluded. DPD defines buckets. This public-reference cohort does not reconstruct historical insolvency holds.')
        if ('outbound' in q or 'contact' in q) and ('attempts' in q or 'touches' in q) and ('average' in q or 'on average' in q or 'per case' in q):
            if explicit_period(q):raise PlanError('This all-open-case measure uses lifetime observed outbound attempts. For a contact-date period, ask for attempts per case in that period and specify its grouping.')
            if re.search(r'\bby\b',q) and not re.search(r'\bby (?:current )?bucket',q):raise PlanError('The all-open-case lifetime-attempts calculation supports grouping by current bucket. For contact-date period attempts, specify a period and supported grouping.')
            return Plan(f"""WITH attempts AS(SELECT case_id,count(*) n FROM curated.contact_history h WHERE h.direction='outbound' AND {CHANNEL}!='system' GROUP BY 1)
+SELECT c.current_bucket,round(avg(coalesce(a.n,0)),2) attempts_per_case,count(*) open_cases FROM curated.collections_cases c LEFT JOIN attempts a USING(case_id) WHERE c.outcome IS NULL GROUP BY 1 ORDER BY 1""".replace('\n+','\n'),[],'Includes open cases with zero outbound attempts in the denominator.')
        if 'cost' in q and ('contact' in q or 'channel' in q):
            return Plan(f"SELECT {CHANNEL} channel,round(avg(h.contact_cost_cad),2) cost_per_contact_cad,count(*) contacts FROM curated.contact_history h WHERE {CHANNEL}!='system' AND h.contact_ts_local>=? AND h.contact_ts_local<? GROUP BY 1 ORDER BY 1",period)
        if ('champion' in q or 'challenger' in q) and ('promise' in q or 'ptp' in q):
            if re.search(r'\bby\b',q) or explicit_period(q):raise PlanError('The supported randomized strategy comparison uses all resolved promises and groups by test cell; custom groups/periods need clarification.')
            return Plan(f"SELECT c.test_cell,round(100.0*avg(CASE WHEN p.ptp_status='kept' THEN 1 ELSE 0 END),1) kept_pct,count(*) promises FROM curated.promises_to_pay p JOIN curated.collections_cases c USING(case_id) WHERE c.assignment_method='random' AND c.test_cell IN ('champion','challenger_A','challenger_B') AND p.ptp_status IN {RESOLVED} GROUP BY 1 ORDER BY 1",[],'Only randomized cases are compared. Rule-based assignments are confounded.')
        if 'hardship' in q and ('rate' in q or 'share' in q) and not ('interest' in q):
            group='primary_product' if 'product' in q else 'province_code' if 'province' in q else None
            return Plan(f"SELECT {group+',' if group else ''}round(100.0*avg(CASE WHEN hardship_flag THEN 1 ELSE 0 END),1) hardship_rate_pct,count(*) cases FROM curated.collections_cases WHERE case_open_date>=? AND case_open_date<?"+(' GROUP BY 1 ORDER BY 1' if group else ''),period,'This measures recorded hardship flags, not independently verified true hardship.')
        if ('promise' in q or 'ptp' in q) and ('kept' in q or 'keep rate' in q):
            return Plan(f"SELECT round(100.0*avg(CASE WHEN ptp_status='kept' THEN 1 ELSE 0 END),1) promise_kept_rate_pct,count(*) resolved_promises FROM curated.promises_to_pay WHERE ptp_due_date>=? AND ptp_due_date<? AND ptp_status IN {RESOLVED}",period)
        if ('cases' in q and re.search(r'\bopen\b',q)) and ('how many' in q or 'count' in q or 'number' in q):
            group='current_bucket' if 'bucket' in q else 'queue' if 'queue' in q else 'primary_product' if 'product' in q else None
            return Plan(f"SELECT {group+',' if group else ''}count(*) open_cases FROM curated.collections_cases WHERE outcome IS NULL"+(' GROUP BY 1 ORDER BY 1' if group else ''),[],'Open means no recorded outcome. Reported current_bucket values are retained; DPD/bucket discrepancies are reported separately.')
        return None

    def _generic_plan(self,q,start,end):
        """Recognize common intents locally; compile the same allowlist as Gemini."""
        if 'cases' in q and re.search(r'\bopened\b',q) and re.search(r'how many|count|number',q):
            raise PlanError('Currently open cases and cases opened during a period are different populations. This count supports currently open cases; an opening-date count needs a separate cohort.')
        # These questions specify different cohorts and retain explicit templates.
        if (re.search(r'late[- ]fee|champion|challenger|randomi[sz]ed.*pilot|certified.*pilot|payroll|\broll\b|worse bucket',q)
            or ('broken' in q and prior_broken_cohort(q))
            or thirty_day_cure(q)
            or (re.search(r'outside|out[- ]of[- ]hours',q) and 'hours' in q)
            or (('paid' in q or 'collected' in q) and 'promise' in q)
            or (re.search(r'charged off|charge-off|write[- ]off',q) and not 'rate' in q)
            or ('open cases' in q and re.search(r'attempts|touches',q))):
            return None
        metric=None
        if re.search(r'broken[- ]promise|broken.*ptp|ptp.*break|promise.*break|break(?:ing)? rate.*(?:ptp|promise)',q):metric='broken_promise_rate'
        elif re.search(r'promise[- ]kept|ptp.*kept|kept.*promise|promise.*kept|keep rate',q):metric='promise_kept_rate'
        elif 'cost' in q and re.search(r'rpc|right[- ]party|right party',q):metric='cost_per_rpc'
        elif 'cost' in q and re.search(r'contact|channel|attempt',q):metric='cost_per_contact'
        elif re.search(r'ptp rate|promise rate|promises taken per|ptp per rpc',q):metric='ptp_rate'
        elif re.search(r'right[- ]party|right party|rpc rate|reach rate',q):metric='rpc_rate'
        elif re.search(r'average.*(days past due|dpd)|mean dpd|average arrears age',q):metric='average_dpd'
        elif re.search(r'delinquency rate|delinquent share|arrears rate',q) or ('past due' in q and re.search(r'share|active.*accounts',q)):metric='delinquency_rate'
        elif 'cure rate' in q:metric='cure_rate'
        elif re.search(r'write[- ]off rate|charge[- ]off rate|loss rate',q):metric='write_off_rate'
        elif 'hardship' in q and re.search(r'rate|share',q) and 'interest' not in q:metric='hardship_rate'
        elif re.search(r'attempts per case|contact intensity|touches per case',q):metric='contact_attempts_per_case'
        elif re.search(r'how much.*\bcollect\b|dollars collected|recoveries|amount collected',q):metric='collected_amount'
        elif 'cases' in q and re.search(r'\bopen\b',q) and re.search(r'how many|count|number',q):metric='open_cases'
        if metric is None:return None
        if metric=='broken_promise_rate' and re.search(r'\bnumber of broken|\bhow many broken|\bcount.*broken',q) and not re.search(r'\brate\b|\bshare\b',q):
            raise PlanError('Please clarify whether you need a count or a broken-promise rate; this metric compiler returns the rate among resolved promises.')
        if metric!='hardship_rate' and re.search(r'\bhardship\b',q):raise PlanError('Filtering this metric to hardship cases/accounts requires a separately defined cohort; please clarify the source flag and population.')
        filters=province_filter(q)
        if re.search(r'\b(?:for|among|only|with|without|excluding|exclude|where)\b.*\b(?:late[- ]stage|early[- ]stage|closed|certified|uncertified|french|english|mortgage|gold|platinum|silver|secured|unsecured|1\s*[-–]\s*30)\b',q):
            raise PlanError('The requested cohort filter is unsupported. Specify the metric population and a supported grouping without custom filters.')
        if re.search(r'\bopen\s+cases?\b',q) and metric not in ['open_cases','average_dpd']:
            raise PlanError('Filtering this metric to currently open cases is not part of its compiled definition; please clarify the intended cohort.')
        if metric=='cure_rate' and 'opened' in q:
            raise PlanError('The certified cure rate uses cases open at the start of a calendar period. For cases opened during a month, please specify the follow-up window, such as 30 days from opening.')
        if metric=='delinquency_rate' and re.search(r'loan|lending|all accounts|mortgage|lines? of credit|\bloc\b',q):
            raise PlanError('This snapshot calculation supports active card accounts. The lending extract has no authoritative active-status field for this denominator.')
        if metric=='delinquency_rate' and re.search(r'\b(?:[2-9]|\d{2,})\s*\+?\s*(?:days? past due|dpd)|\b90\+|\b30\+|\b60\+',q):
            raise PlanError('The certified delinquency rate is 1+ DPD. A different DPD threshold needs a separately defined metric.')
        if metric=='delinquency_rate':
            thresholds=re.findall(r'\b(\d+)\s*(?:\+|or more|and above)?\s*(?:days? past due|dpd)|\bdpd\s*[>=]{1,2}\s*(\d+)',q)
            if any(int(a or b)!=1 for a,b in thresholds):raise PlanError('The certified delinquency rate is 1+ DPD; other thresholds require a separately defined metric.')
        grouping='none'
        dims=r'(?:queue|bucket|province|product|channel|hour|site)s?\b'
        trigger=re.search(r'\bby\b|\b(?:each|every|per)\s+(?='+dims+r')|\bacross\s+(?:all\s+)?(?:the\s+)?(?='+dims+r')',q)
        if trigger:
            clause=q[trigger.end():]
            found=[]
            for dimension,pattern in [('queue',r'\bqueues?\b'),('bucket',r'\bbuckets?\b'),('province',r'\bprovinces?\b'),('product',r'\bproducts?\b'),('channel',r'\bchannels?\b'),('hour',r'\bhours?\b'),('site',r'\bsites?\b')]:
                if re.search(pattern,clause):found.append(dimension)
            if len(found)!=1:raise PlanError('Please choose one supported grouping: '+', '.join(CATALOG.get(metric,{}).get('groupings',[]))+'.')
            grouping=found[0]
            if grouping=='site' and metric in ['rpc_rate','ptp_rate','cost_per_contact','cost_per_rpc']:grouping='agent_site'
        if CATALOG.get(metric,{}).get('snapshot_only'):
            exact_snapshot=bool(re.search(r'\bas of\s+'+SNAPSHOT+r'\b|\bon\s+'+SNAPSHOT+r'\b',q))
            if explicit_period(q) and not exact_snapshot:
                raise PlanError(f'This calculation supports only the {SNAPSHOT} snapshot; historical reconstruction is unavailable.')
            start,end=ASOF,ASOF+timedelta(days=1)
        plan=compile_plan({'metric_id':metric,'grouping':grouping,'start_date':start.isoformat(),'end_date':end.isoformat(),'filters':filters,'clarification':None,'refuse':False,'refuse_reason':None})
        if not CATALOG[metric].get('snapshot_only') and not explicit_period(q):
            plan.note+=' No period was supplied; this answer uses the snapshot month to date.'
        return plan

    def _policy(self,q,result):
        if not re.search(r'collection|hardship|call|contact|promise|\bptp|broken|payment|phone|\bsms\b|text message|consent|bankrupt|consumer proposal|dispute|complaint|grace|metric|financial|dialer|agent|programme|program|policy|procedure|accommodation|accessibility|dncl|casl',q):
            reason='This question is outside the collections dataset and policies.'
            result.update(answer=reason,refused=True,reason=reason);return
        preferred=[]
        if 'casl' in q or 'email' in q and 'consent' in q:preferred=[('POL-COLL-001','§5.3')]
        elif 'national do not call' in q or 'dncl' in q:preferred=[('POL-COLL-001','§5.3')]
        elif 'consumer proposal' in q or 'bankruptcy' in q:preferred=[('POL-COLL-001','§7.3')]
        elif re.search(r'attempt|calls?\b|phone|contact|reach',q) and re.search(r'week|7[- ]days?|seven days',q):preferred=[('POL-COLL-001','§5.2')]
        elif re.search(r'calling hours|call.*(?:before|after)\s*\d|permitted.*hours',q):preferred=[('POL-COLL-001','§5.1')]
        elif 'hours' in q and ('cut' in q or 'reduced' in q) or 'before' in q and 'payment' in q:preferred=[('POL-COLL-004','§4.2')]
        elif '3-month' in q or 'reduced payment' in q:preferred=[('POL-COLL-004','§4.2'),('HPT-2026','document')]
        elif 'grace' in q or re.search(r'(?:considered|counts? as|treated as|deemed)\s+(?:a\s+)?broken',q):preferred=[('PRC-COLL-010','§3.3')]
        elif 'volume' in q and ('drop' in q or '23' in q or '24' in q):preferred=[('IR-2026-0923','document'),('IR-2026-0923','§1'),('IR-2026-0923','§2')]
        matches=[s for pair in preferred for s in self.sections if (s['id'],s['section'])==pair and s['language']=='EN']
        if not matches and self.index:
            scores=self.index.get_scores(tokens(q));ranked=sorted(range(len(scores)),key=lambda i:scores[i],reverse=True)
            matches=[self.sections[i] for i in ranked[:2] if scores[i]>2 and self.sections[i]['language']=='EN']
        if not matches:
            result['answer']='Please specify a supported collections metric, period, grouping, policy topic or case call summary.'
            result['reason']='clarification_required';return
        result['sources']=[{'document_id':s['id'],'version':s['version'],'section':s['section'],'path':s['path']} for s in matches]
        result['answer']='\n\n'.join(summarize_policy(s['text'],q) for s in matches)
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
        transcript=json.loads(path.read_text(encoding='utf-8'));turns=transcript.get('turns',[])
        result['answer']=f"Most recent recorded call on {case}: {row[1]}, transcript {row[0]}, language {row[3]}.\n"+summarize_transcript(turns)
        result['sources']=[{'case_id':case,'transcript_id':row[0],'call_start':str(row[1]),'file_path':row[2]}]
        result['sql_or_sources']=sql+'\nBound parameters: '+json.dumps([case])+f'\ntranscript:{row[0]} ({row[2]}); exact turn timestamps above'
