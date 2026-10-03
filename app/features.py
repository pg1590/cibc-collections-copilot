"""Versioned financial text cues and structured definitions reused offline/live."""
import json
import re
import unicodedata
from pathlib import Path

VERSION = "c360-financial-v1"
# Model input is these binary financial cues only. Raw free text and protected
# demographic/vulnerability fields never enter the classifier's input vector.
PATTERNS = {
    "income_loss": r"job loss|lost (my |their |his |her |the )?job|laid off|layoff|position eliminated|unemploy|perdu (mon |son |leur )?emploi|perte d.emploi|licenci",
    "income_reduction": r"hours (were |have been |got )?cut|reduced hours|fewer hours|hours reduced|reduced income|pay cut|reduction.*(hours|income)|heures.*redui|baisse.*revenu|salaire.*redui",
    "income_delay": r"pay.*late|payroll.*delay|salary.*delay|pay.*delay|waiting.*(pay|salary|income)|paye.*retard|salaire.*retard",
    "payment_difficulty": r"cannot (afford|pay)|can.t (afford|pay)|unable to pay|no money|not enough money|financial (hardship|difficult)|struggling.*pay|difficulte.*financ|ne peux pas payer|pas.*argent",
    "hardship_request": r"hardship|payment relief|payment deferral|reduced payment|payment reduction|allegement|report de paiement|paiement reduit",
    "expense_pressure": r"rent.*(increase|raised|higher)|unexpected (expense|bill)|cost.*(rise|increase)|loyer.*(hausse|augment)|depense.*imprevu",
}
TEXT_FEATURES = list(PATTERNS)


def normalize_text(text):
    return ''.join(c for c in unicodedata.normalize('NFD', (text or '').lower()) if unicodedata.category(c) != 'Mn')


def text_features(text):
    normalized = normalize_text(text)
    return {name: int(bool(re.search(pattern, normalized))) for name, pattern in PATTERNS.items()}


def evidence(text):
    """Return exact source spans, never invented explanations."""
    spans=[]
    for sentence in re.split(r'(?<=[.!?;])\s+|\n+', text or ''):
        if any(text_features(sentence).values()): spans.append(sentence.strip())
    return spans[:5]


def feature_sql(customer_filter=False):
    financial = ','.join(f"CAST(regexp_matches(lower(strip_accents(coalesce(n.note_text,''))),'{pattern.replace(chr(39), chr(39)*2)}') AS INTEGER) AS {name}" for name,pattern in PATTERNS.items())
    where = 'WHERE g.customer_id=?' if customer_filter else ''
    return f"""WITH cases AS (
      SELECT customer_id,count(*) FILTER(WHERE outcome IS NULL) open_cases,
      coalesce(sum(total_overdue) FILTER(WHERE outcome IS NULL),0) total_overdue,
      max(current_dpd) FILTER(WHERE outcome IS NULL) max_dpd
      FROM gold.cases WHERE case_open_date<=DATE '2026-09-28' GROUP BY 1
    ), promises AS (
      SELECT i.customer_id,count(*) FILTER(WHERE p.ptp_status IN ('kept','partially_kept','broken')) resolved_promises,
      count(*) FILTER(WHERE p.ptp_status='broken') broken_promises
      FROM curated.promises_to_pay p JOIN gold.crm_identity i USING(crm_customer_id)
      WHERE p.status_ts<=TIMESTAMP '2026-09-28 23:59:59' GROUP BY 1
    ), contacts AS (
      SELECT i.customer_id,count(*) contacts_7d FROM curated.contact_history h
      JOIN gold.crm_identity i USING(crm_customer_id)
      WHERE h.direction='outbound' AND coalesce(h.channel,h.channel_v2)!='system'
       AND h.contact_ts_utc>=TIMESTAMP '2026-09-22' AND h.contact_ts_utc<TIMESTAMP '2026-09-29' GROUP BY 1
    ) SELECT g.customer_id,coalesce(c.open_cases,0) open_cases,coalesce(c.total_overdue,0) total_overdue,c.max_dpd,
      coalesce(p.resolved_promises,0) resolved_promises,coalesce(p.broken_promises,0) broken_promises,
      CASE WHEN p.resolved_promises>0 THEN p.broken_promises::DOUBLE/p.resolved_promises ELSE NULL END broken_promise_ratio,
      coalesce(h.contacts_7d,0) contacts_7d,n.note_id,n.note_ts,{financial}
    FROM gold.customers g LEFT JOIN cases c USING(customer_id) LEFT JOIN promises p USING(customer_id)
    LEFT JOIN contacts h USING(customer_id) LEFT JOIN gold.latest_notes n USING(customer_id) {where}"""


def definitions():
    return [
        {'name':'open_cases','definition':"Number of cases with no recorded outcome at snapshot",'source':'gold.cases','type':'integer'},
        {'name':'total_overdue','definition':'Sum overdue on open cases (CAD)','source':'gold.cases','type':'number'},
        {'name':'max_dpd','definition':'Maximum days past due on open cases; null when no open case','source':'gold.cases','type':'integer'},
        {'name':'broken_promise_ratio','definition':'Broken / resolved promises, excludes open/cancelled; null for no resolved promise','source':'curated.promises_to_pay','type':'number'},
        {'name':'contacts_7d','definition':'Outbound contacts from 22–28 Sep inclusive; system events excluded','source':'curated.contact_history','type':'integer'},
    ] + [{'name':k,'definition':'Financial text cue: '+v,'source':'latest agent note before snapshot','type':'binary'} for k,v in PATTERNS.items()]


def build_store(conn, report_path):
    import polars as pl
    import pandera.polars as pa
    conn.execute('CREATE OR REPLACE TABLE gold.features AS '+feature_sql())
    # Real eager full-column validation, not schema-only LazyFrame validation.
    keys = conn.execute('SELECT customer_id,open_cases,total_overdue FROM gold.features').fetchall()
    frame = pl.DataFrame(keys,schema={'customer_id':pl.String,'open_cases':pl.Int64,'total_overdue':pl.Float64},orient='row')
    pa.DataFrameSchema({
        'customer_id':pa.Column(pl.String,nullable=False,unique=True),
        'open_cases':pa.Column(pl.Int64,checks=pa.Check.ge(0),nullable=False),
        'total_overdue':pa.Column(pl.Float64,nullable=False),
    }).validate(frame,lazy=True)
    del frame, keys
    selected=conn.execute('SELECT customer_id FROM gold.features ORDER BY hash(customer_id) LIMIT 100').fetchall()
    mismatch=0
    # Recompute with the serving definition, compare all numeric and text features.
    for (cid,) in selected:
        offline=conn.execute('SELECT * FROM gold.features WHERE customer_id=?',[cid]).fetchone()
        online=conn.execute(feature_sql(True),[cid]).fetchone()
        mismatch+=int(offline!=online)
    result={'version':VERSION,'definitions':definitions(),'parity':{'checked':len(selected),'mismatches':mismatch},'validated_rows':conn.execute('SELECT count(*) FROM gold.features').fetchone()[0]}
    Path(report_path).write_text(json.dumps(result,indent=2))
    if mismatch: raise ValueError('Offline/online feature mismatch')
    return result
