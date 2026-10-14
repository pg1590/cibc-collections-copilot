"""Reproducible immutable raw -> typed curated -> conservative C360 build.

Run from the repository root: .venv/bin/python scripts/build_data.py
No network calls. Original release remains intact. Interrupted table loads resume.
"""
import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import duckdb
from rapidfuzz import fuzz
from datetime import date, timedelta
from app import snapshot as snapshot_detect
from app.settings import DATASET, DB, QUALITY, ROOT, SNAPSHOT


def ident(value):
    return '"' + value.replace('"', '""') + '"'


def literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def date_expr(col, timestamp=False):
    # ISO first; the release includes slash dates and YYYYMMDD drift.
    fmt = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%Y/%m/%d", "%Y%m%d", "%d/%m/%Y", "%d-%m-%Y"]
    expr = f"coalesce(try_cast({col} as TIMESTAMP),try_strptime(cast({col} as VARCHAR),[{','.join(literal(x) for x in fmt)}]))"
    return expr if timestamp else f"cast({expr} as DATE)"


def norm(col):
    return f"regexp_replace(lower(strip_accents(coalesce({col},''))), '[^a-z0-9]', '', 'g')"


def phone(col):
    return f"right(regexp_replace(coalesce({col},''),'[^0-9]','','g'),10)"


def count(conn, sql):
    return conn.execute(sql).fetchone()[0]


def quality_handling(check):
    name, table = check['check'], check['table']
    if name.endswith('_unique_non_null'):
        return 'Check uniqueness and missing keys. No key is invented or silently reassigned; any failure requires review.'
    if name.startswith('invalid_'):
        return 'Normalize supported dates/types with TRY_CAST and TRY_STRPTIME. Keep unparseable values in raw data, set curated value to null and count the failure.'
    if name.endswith('_referential_integrity'):
        if table == 'collections_cases':
            return 'Retain source rows in raw/curated and portfolio totals. Exclude unlinked CRM references from golden C360 cases; report the coverage gap.'
        if table == 'agent_notes':
            return 'Retain raw/curated notes. Exclude notes without a resolved CRM link from the golden latest-note view.'
        return 'Retain raw/curated contacts and flag orphan case references. Do not invent a case link; case-joined queries cannot recover the missing case.'
    if name == 'dpd_missing':
        return 'Preserve null DPD. Exclude unknown DPD from delinquency-rate calculations and report the denominator; do not impute a DPD value.'
    if name.endswith('_disagrees_with_dpd'):
        return 'Count and retain both reported bucket and DPD. Use reported buckets for the applicable released benchmark and DPD where the metric specifies it; discrepancy remains unresolved.'
    if name in ['date_of_birth_missing', 'primary_phone_e164_missing']:
        return 'Preserve missing values. Match only when independent available evidence satisfies the identity rules; otherwise retain review/unmatched status.'
    if name == 'contact_ts_utc_missing':
        return 'Check timestamps and retain raw source values. Preserve missing values; do not fabricate a contact timestamp.'
    return 'Retain the source value, report the measured issue and require review before unsupported correction.'


def write_quality_report(report):
    lines = ['# Counted data quality report',
             f"Snapshot: {report['snapshot_date']}. Data built: {report['built_at']}.", '',
             'The table below distinguishes handling from repair. Missing source facts and contradictory values remain unresolved when no authoritative correction is available. Raw source files remain intact. A row can fail several checks, so failed counts must not be added as a count of distinct customers.', '',
             '| Table | Raw rows | Curated rows |', '|---|---:|---:|']
    lines += [f"| {table} | {n:,} | {report['curated_counts'][table]:,} |" for table, n in report['raw_counts'].items()]
    lines += ['', '| Check | Table | Affected rows | Total rows | Severity | Handling / correction |',
              '|---|---|---:|---:|---|---|']
    lines += [f"| {x['check']} | {x['table']} | {x['failed_rows']:,} | {x['total_rows']:,} | {x['severity']} | {quality_handling(x)} |" for x in report['checks']]
    identity = report['identity']
    lines += ['', '## Identity resolution and normalization', '',
              f"The pipeline creates {identity['golden_customers']:,} golden customer records from {identity['crm_records']:,} CRM rows. This is conservative identity resolution, not a claim of perfect recovery of the underlying one million people.", '',
              '| Source-key outcome | Count | Handling |', '|---|---:|---|',
              f"| Matched | {identity.get('matched', 0):,} | Accept only the documented identity rules and unique-candidate margin. Rule scores are not calibrated probabilities. |",
              f"| Review | {identity.get('review', 0):,} | Keep candidate evidence for review and exclude these links from golden account balances. |",
              f"| Unmatched | {identity.get('unmatched', 0):,} | Preserve source keys without fabricating a customer link; exclude these links from golden account balances. |", '',
              'These counts refer to source keys across systems, not distinct people. Declared CRM duplicates merge only when date of birth and independent name or phone evidence agree. RapidFuzz name similarity is a review diagnostic and cannot independently authorize a match.', '',
              'Mixed supported date formats become typed dates/timestamps. Customer IDs remain strings to preserve leading zeros. Only empty CSV fields become null; literal NA, N/A and na remain values. The question engine coalesces channel_v2 with channel for the recorded schema drift.', '',
              '## Remaining limitations', '',
              'No source row is dropped during typed curation. Golden views intentionally exclude unresolved links. Source-wide totals can therefore differ from linked C360 totals. Missing DPD, missing identity evidence, orphan references and bucket contradictions are reported rather than claimed as repaired. Matching precision and missed-match rates require independently labelled identity pairs; those measures are not available yet.']
    output = ROOT / 'docs/data-quality-report.md'
    output.write_text('\n'.join(lines) + '\n')
    return output


def build(dataset=DATASET, db=DB, reload=False):
    dataset = Path(dataset).resolve(); db = Path(db).resolve()
    schema = json.loads((dataset / "schema/schema.json").read_text())
    db.parent.mkdir(parents=True, exist_ok=True)
    c = duckdb.connect(str(db))
    c.execute("SET memory_limit='2GB'"); c.execute("SET threads=2")
    c.execute("SET preserve_insertion_order=false")
    c.execute(f"SET temp_directory={literal(db.parent / 'duckdb-temp')}")
    for s in ["raw", "curated", "gold"]: c.execute(f"CREATE SCHEMA IF NOT EXISTS {s}")
    report = {"snapshot_date": SNAPSHOT, "raw_counts": {}, "curated_counts": {}, "checks": [], "identity": {}}
    started = time.monotonic()
    staging=db.parent/'quality-staging.json'
    cached=json.loads(staging.read_text()) if staging.exists() and not reload else {}
    for table, spec in schema.items():
        path = dataset / spec["path"]
        if spec["format"].lower() == "csv":
            if not path.exists(): raise FileNotFoundError(path)
            raw = f"raw.{ident(table)}"; curated = f"curated.{ident(table)}"
            c.execute(f"CREATE OR REPLACE VIEW {raw} AS SELECT * FROM read_csv({literal(path)},all_varchar=true,header=true,nullstr='',sample_size=20480)")
            exists = count(c, "SELECT count(*) FROM information_schema.tables WHERE table_schema='curated' AND table_name=" + literal(table))
            fingerprint=[path.stat().st_size,path.stat().st_mtime_ns]
            if exists and not reload and cached.get(table,{}).get('fingerprint')==fingerprint:
                previous=cached[table]
                report['raw_counts'][table]=previous['raw_count'];report['curated_counts'][table]=previous['curated_count']
                report['checks'].extend(previous['checks']);continue
            check_start=len(report['checks'])
            cols = [r[0] for r in c.execute(f"DESCRIBE {raw}").fetchall()]
            physical = {x["name"]: x.get("physical_type", "VARCHAR") for x in spec["columns"]}
            exprs=[]; checks=[]
            for name in cols:
                q=ident(name); dtype=physical.get(name,"VARCHAR")
                if dtype in ("DATE","TIMESTAMP"): expr=date_expr(q,dtype=="TIMESTAMP")
                elif dtype!="VARCHAR": expr=f"try_cast({q} as {dtype})"
                else: expr=q
                exprs.append(f"{expr} AS {q}")
                if dtype!="VARCHAR": checks.append((name,expr))
            if reload or not exists:
                print(f"Loading {table}...",flush=True)
                c.execute(f"CREATE OR REPLACE TABLE {curated} AS SELECT {','.join(exprs)} FROM {raw}")
            n=count(c,f"SELECT count(*) FROM {curated}")
            report["raw_counts"][table]=count(c,f"SELECT count(*) FROM {raw}")
            report["curated_counts"][table]=n
            if checks:
                # One scan per source, not one per column. Null conversion is counted.
                results=c.execute(f"SELECT {','.join(f'count(*) FILTER (WHERE {ident(k)} IS NOT NULL AND ({e}) IS NULL)' for k,e in checks)} FROM {raw}").fetchone()
                for (k,_), bad in zip(checks,results):
                    if bad: report["checks"].append({"check":f"invalid_{k}","table":table,"failed_rows":bad,"total_rows":n,"severity":"warning"})
            cached[table]={'fingerprint':fingerprint,'raw_count':report['raw_counts'][table],'curated_count':n,'checks':report['checks'][check_start:]}
            staging.write_text(json.dumps(cached))
            key=next((x["name"] for x in spec["columns"] if x.get("key")=="PK"),None)
            # Published dictionary omits key flags in schema JSON: curated PK checks below.
        elif spec["format"].lower().startswith("parquet"):
            pattern=dataset/spec["path"]/'*/*.parquet'
            c.execute(f"CREATE OR REPLACE VIEW curated.{ident(table)} AS SELECT * EXCLUDE(year) FROM read_parquet({literal(pattern)},hive_partitioning=true)")
            report["raw_counts"][table]=count(c,f"SELECT count(*) FROM curated.{ident(table)}")
            report["curated_counts"][table]=report["raw_counts"][table]
    print("Building customer identities...",flush=True)
    # Explicit CRM duplicate references are accepted only with independently agreeing DOB and identity evidence.
    c.execute(f"""CREATE OR REPLACE TABLE gold.crm_identity AS
      SELECT a.crm_customer_id,
      CASE WHEN b.crm_customer_id IS NOT NULL AND a.date_of_birth=b.date_of_birth
       AND ({phone('a.primary_phone_raw')}={phone('b.primary_phone_raw')} AND length({phone('a.primary_phone_raw')})=10
        OR {norm('a.full_name_raw')}={norm('b.full_name_raw')} AND length({norm('a.full_name_raw')})>3)
       THEN b.crm_customer_id ELSE a.crm_customer_id END customer_id,
      CASE WHEN a.duplicate_of_crm_id IS NOT NULL THEN 'declared_duplicate_checked' ELSE 'crm_primary' END AS "method"
      FROM curated.customers a LEFT JOIN curated.customers b ON a.duplicate_of_crm_id=b.crm_customer_id""")
    c.execute(f"""CREATE OR REPLACE TABLE gold.customers AS
      SELECT i.customer_id,c.crm_customer_id,c.first_name||' '||c.last_name AS "name",c.province_code AS province,
       c.preferred_language,c.date_of_birth,c.consent_call,c.consent_sms,c.consent_email,
       c.cease_communication_flag,c.internal_do_not_call_flag,c.bankruptcy_flag,c.consumer_proposal_flag,
       c.deceased_flag,c.last_profile_update_ts,
       {norm('c.full_name_raw')} nname,{norm('c.last_name')} surname,
       {norm('c.postal_code')} npostal,{phone('c.primary_phone_raw')} nphone,
       lower(substr(strip_accents(c.first_name),1,1)) first_initial
      FROM curated.customers c JOIN gold.crm_identity i USING(crm_customer_id)
      QUALIFY row_number() OVER(PARTITION BY i.customer_id ORDER BY (c.crm_customer_id=i.customer_id) DESC,c.last_profile_update_ts DESC,c.crm_customer_id)=1""")
    sources=[]
    for table, system, key, prefix in [('card_accounts','cards','src_customer_ref','cardholder'),('loan_accounts','lending','src_customer_ref','borrower'),('deposit_accounts','core','src_customer_ref','holder')]:
        sources.append(f"SELECT '{system}' source_system,{key} source_key,{norm(prefix+'_name_raw')} nname,{phone(prefix+'_phone_raw')} nphone,{norm(prefix+'_postal_raw')} npostal,{date_expr(prefix+'_dob_raw')} dob FROM curated.{table}")
    # Bureau keys also share CIF with core banking, but are not assumed to match a CRM ID.
    bureau_postal="regexp_extract(upper(subject_address_reported),'([A-Z][0-9][A-Z] ?[0-9][A-Z][0-9])',1)"
    sources.append(f"SELECT 'bureau' source_system,bank_subject_ref source_key,{norm('subject_name_reported')} nname,'' nphone,{norm(bureau_postal)} npostal,{date_expr('subject_dob_reported')} dob FROM curated.external")
    c.execute(f"CREATE OR REPLACE TABLE gold.source_identity AS SELECT DISTINCT * FROM ({' UNION ALL '.join(sources)})")
    # Block on DOB+phone or DOB+postal. Requiring two agreeing fields plus surname avoids a unique weak match.
    c.execute("""CREATE OR REPLACE TABLE gold.identity_candidates AS
      WITH pairs AS (
       SELECT s.*,g.customer_id,g.nname gname,g.nphone gphone,g.surname,g.first_initial
        FROM gold.source_identity s JOIN gold.customers g ON s.dob=g.date_of_birth AND s.nphone=g.nphone WHERE length(s.nphone)=10
       UNION
       SELECT s.*,g.customer_id,g.nname gname,g.nphone gphone,g.surname,g.first_initial
        FROM gold.source_identity s JOIN gold.customers g ON s.dob=g.date_of_birth AND s.npostal=g.npostal WHERE length(s.npostal)=6
       UNION
       SELECT s.*,g.customer_id,g.nname gname,g.nphone gphone,g.surname,g.first_initial
        FROM gold.source_identity s JOIN gold.customers g ON s.dob=g.date_of_birth AND s.nname=g.nname WHERE length(s.nname)>5
      ) SELECT *,
       CASE WHEN nphone=gphone AND length(nphone)=10 AND contains(nname,surname) THEN 0.99
       WHEN nname=gname AND length(npostal)=6 THEN 0.985
       WHEN length(npostal)=6 AND contains(nname,surname) AND contains(nname,first_initial) THEN 0.97
       WHEN nname=gname THEN 0.95 ELSE 0.7 END confidence
      FROM pairs""")
    c.execute("""CREATE OR REPLACE TABLE gold.identity_crosswalk AS
      WITH best AS (SELECT source_system,source_key,customer_id,max(confidence) confidence FROM gold.identity_candidates GROUP BY ALL),
       ranks AS(SELECT *,row_number() OVER(PARTITION BY source_system,source_key ORDER BY confidence DESC,customer_id) rn,
        lead(confidence) OVER(PARTITION BY source_system,source_key ORDER BY confidence DESC,customer_id) next_confidence FROM best)
      SELECT source_system,source_key,customer_id,confidence,
       CASE WHEN confidence>=0.97 AND (next_confidence IS NULL OR confidence-next_confidence>=0.04) THEN 'matched' ELSE 'review' END status,
       'DOB plus phone/name/postal agreement; unique candidate margin' AS "method" FROM ranks WHERE rn=1""")
    # Bureau-to-core agreement on CIF is accepted only when independent DOB and surname confirm it.
    c.execute("""INSERT INTO gold.identity_crosswalk
      SELECT s.source_system,s.source_key,x.customer_id,0.99,'matched','CIF plus independently agreeing DOB and surname'
      FROM gold.source_identity s JOIN gold.identity_crosswalk x ON s.source_key=x.source_key AND x.source_system='core' AND x.status='matched'
      JOIN gold.customers g ON x.customer_id=g.customer_id AND s.dob=g.date_of_birth AND contains(s.nname,g.surname)
      WHERE s.source_system='bureau' AND NOT EXISTS(SELECT 1 FROM gold.identity_crosswalk b WHERE b.source_system='bureau' AND b.source_key=s.source_key)
      QUALIFY row_number() OVER(PARTITION BY s.source_system,s.source_key ORDER BY x.customer_id)=1""")
    c.execute("""INSERT INTO gold.identity_crosswalk
      SELECT source_system,source_key,NULL,0,'unmatched','No strong candidate; source preserved'
      FROM gold.source_identity s WHERE NOT EXISTS(SELECT 1 FROM gold.identity_crosswalk x WHERE s.source_system=x.source_system AND s.source_key=x.source_key)
      GROUP BY source_system,source_key""")
    c.execute("""UPDATE gold.identity_crosswalk SET status='review',"method"='Conflicting source DOBs; independent review required'
      WHERE (source_system,source_key) IN(SELECT source_system,source_key FROM gold.source_identity GROUP BY 1,2 HAVING count(DISTINCT dob)>1)""")
    c.execute("""INSERT INTO gold.identity_crosswalk
      SELECT 'crm',crm_customer_id,customer_id,1.0,'matched','Verified CRM canonical reference' FROM gold.crm_identity
      UNION ALL SELECT DISTINCT 'collections',c.coll_customer_ref,i.customer_id,1.0,'matched','CRM reference copied at case open; referential check'
      FROM curated.collections_cases c JOIN gold.crm_identity i ON c.coll_customer_ref=i.crm_customer_id""")
    c.execute('ALTER TABLE gold.identity_crosswalk ADD COLUMN fuzzy_name_similarity DOUBLE')
    review_pairs=c.execute("""SELECT DISTINCT x.source_system,x.source_key,x.customer_id,p.nname,p.gname
      FROM gold.identity_crosswalk x JOIN gold.identity_candidates p USING(source_system,source_key,customer_id)
      WHERE x.status='review' ORDER BY x.source_system,x.source_key LIMIT 1000""").fetchall()
    for system,key,cid,left,right in review_pairs:
        c.execute('UPDATE gold.identity_crosswalk SET fuzzy_name_similarity=? WHERE source_system=? AND source_key=? AND customer_id=?',[fuzz.ratio(left,right),system,key,cid])
    report['identity']['review_name_similarity_sample_size']=len(review_pairs)
    c.execute("""CREATE OR REPLACE TABLE gold.cases AS SELECT i.customer_id,c.*
      FROM curated.collections_cases c JOIN gold.crm_identity i ON c.coll_customer_ref=i.crm_customer_id""")
    c.execute("""CREATE OR REPLACE TABLE gold.accounts AS
      SELECT x.customer_id,'cards' source_system,a.card_account_id account_id,a.src_customer_ref source_key,
      a.product_code product,a.current_balance balance,a.past_due_amount overdue,a.dpd,a.dpd_bucket,a.account_status status,x.confidence identity_confidence
      FROM curated.card_accounts a JOIN gold.identity_crosswalk x ON x.source_system='cards' AND a.src_customer_ref=x.source_key AND x.status='matched'
      UNION ALL SELECT x.customer_id,'lending',a.loan_id,a.src_customer_ref,a.product_type,a.total_outstanding,a.past_due_amount,a.dpd,a.dpd_bucket,
       CASE WHEN a.chargeoff_flag THEN 'charged_off' WHEN a.dpd>0 THEN 'delinquent' ELSE 'current' END,x.confidence
      FROM curated.loan_accounts a JOIN gold.identity_crosswalk x ON x.source_system='lending' AND a.src_customer_ref=x.source_key AND x.status='matched'
      UNION ALL SELECT x.customer_id,'core',a.deposit_account_id,a.src_customer_ref,a.product_type,a.current_balance,
       CASE WHEN a.overdraft_dpd>0 THEN a.overdraft_used ELSE 0 END,a.overdraft_dpd,a.overdraft_dpd_bucket,a.account_status,x.confidence
      FROM curated.deposit_accounts a JOIN gold.identity_crosswalk x ON x.source_system='core' AND a.src_customer_ref=x.source_key AND x.status='matched'""")
    # The as-of point is read from this extract, so a new release needs no code change.
    found = snapshot_detect.write(c, Path(db).with_name("snapshot.json"))
    report["snapshot_date"] = found["snapshot_date"]
    note_cutoff = date.fromisoformat(found["snapshot_date"]) + timedelta(days=1)
    c.execute(f"""CREATE OR REPLACE TABLE gold.latest_notes AS
      SELECT i.customer_id,n.* FROM curated.agent_notes n JOIN gold.crm_identity i USING(crm_customer_id)
      WHERE n.note_ts<TIMESTAMP '{note_cutoff}'
      QUALIFY row_number() OVER(PARTITION BY i.customer_id ORDER BY n.note_ts DESC,n.note_id DESC)=1""")
    c.execute("""CREATE OR REPLACE TABLE gold.customer_summary AS
      WITH cases AS(SELECT customer_id,count(*) FILTER(WHERE outcome IS NULL) open_cases,
       sum(total_overdue) FILTER(WHERE outcome IS NULL) total_overdue,max(current_dpd) FILTER(WHERE outcome IS NULL) max_dpd FROM gold.cases GROUP BY 1),
       ids AS(SELECT customer_id,min(confidence) identity_confidence FROM gold.identity_crosswalk WHERE status='matched' GROUP BY 1)
      SELECT g.customer_id,g.name,g.province,g.preferred_language,coalesce(c.open_cases,0) open_cases,
       coalesce(c.total_overdue,0) total_overdue,c.max_dpd,ids.identity_confidence
      FROM gold.customers g LEFT JOIN cases c USING(customer_id) LEFT JOIN ids USING(customer_id)""")
    for table,key in [('customers','crm_customer_id'),('contact_history','contact_id'),('collections_cases','case_id'),('promises_to_pay','ptp_id')]:
        n=report['curated_counts'][table]
        bad=count(c,f"SELECT count(*)-count(DISTINCT {key}) FROM curated.{table}")
        report['checks'].append({'check':f'{key}_unique_non_null','table':table,'failed_rows':bad,'total_rows':n,'severity':'error'})
    for table,key,target,tkey in [('contact_history','case_id','collections_cases','case_id'),('collections_cases','coll_customer_ref','customers','crm_customer_id'),('agent_notes','crm_customer_id','customers','crm_customer_id')]:
        bad=count(c,f"SELECT count(*) FROM curated.{table} a LEFT JOIN curated.{target} b ON a.{key}=b.{tkey} WHERE a.{key} IS NOT NULL AND b.{tkey} IS NULL")
        report['checks'].append({'check':f'{key}_referential_integrity','table':table,'failed_rows':bad,'total_rows':report['curated_counts'][table],'severity':'warning'})
    for table,col in [('customers','date_of_birth'),('customers','primary_phone_e164'),('card_accounts','dpd'),('loan_accounts','dpd'),('contact_history','contact_ts_utc')]:
        bad=count(c,f'SELECT count(*) FROM curated.{table} WHERE {col} IS NULL')
        report['checks'].append({'check':f'{col}_missing','table':table,'failed_rows':bad,'total_rows':report['curated_counts'][table],'severity':'warning'})
    bucket="CASE WHEN {d}=0 THEN 'current' WHEN {d}<=30 THEN '1-30' WHEN {d}<=60 THEN '31-60' WHEN {d}<=90 THEN '61-90' WHEN {d}<=120 THEN '91-120' WHEN {d}<=150 THEN '121-150' WHEN {d}<=180 THEN '151-180' ELSE '180+' END"
    for table,d,b in [('card_accounts','dpd','dpd_bucket'),('loan_accounts','dpd','dpd_bucket'),('collections_cases','current_dpd','current_bucket')]:
        bad=count(c,f'SELECT count(*) FROM curated.{table} WHERE {d} IS NOT NULL AND {b} IS DISTINCT FROM ({bucket.format(d=d)})')
        report['checks'].append({'check':f'{b}_disagrees_with_dpd','table':table,'failed_rows':bad,'total_rows':report['curated_counts'][table],'severity':'warning'})
    report['identity'].update({r[0]:r[1] for r in c.execute('SELECT status,count(*) FROM gold.identity_crosswalk GROUP BY 1').fetchall()})
    report['identity']['golden_customers']=count(c,'SELECT count(*) FROM gold.customers')
    report['identity']['crm_records']=report['curated_counts']['customers']
    report['identity']['confidence_kind']='Rule scores, not calibrated probabilities. Review/unmatched records are excluded from linked accounts.'
    report['built_at']=datetime.now(timezone.utc).isoformat(); report['duration_seconds']=round(time.monotonic()-started,2)
    c.execute('CHECKPOINT'); c.close()
    QUALITY.write_text(json.dumps(report,indent=2))
    write_quality_report(report)
    print(json.dumps({'duration_seconds':report['duration_seconds'],'identity':report['identity']},indent=2),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--reload',action='store_true')
    mode.add_argument('--report-only',action='store_true',help='Regenerate Markdown from the measured quality JSON without rebuilding the database.')
    args=parser.parse_args()
    if args.report_only:
        print(write_quality_report(json.loads(QUALITY.read_text())))
    else:
        build(reload=args.reload)
