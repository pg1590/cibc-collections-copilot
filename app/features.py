"""Versioned financial text cues and structured definitions reused offline/live."""
import json
import re
import unicodedata
from datetime import date, timedelta
from pathlib import Path

VERSION = "c360-financial-v2"
# Model input is these binary hardship cues only. Raw free text and protected
# demographic/vulnerability fields never enter the classifier's input vector.
# v2 cues follow POL-COLL-004 v4.2 s4.2 (hardship = inability to pay after a change in
# circumstances). Each regex must compile in Python re and DuckDB RE2: no lookaround or
# backreferences. '.' stands in for accented letters so mojibake (U+FFFD) still matches.
# Deliberately excluded: s4.5 vulnerability markers (crying, anxiety, "cust vulnerable -
# financial hardship" tag, serious illness in family, bereavement) and s4.6 protected
# grounds (disability as a status, marital status, pregnancy, religion, origin).
PATTERNS = {
    "income_loss": r"job loss|lost (my |their |his |her |the |a )?job|laid off|layoff|position (was )?eliminated|unemploy|out of work|no income|on strike|lockout|locked out|perdu (mon |son |leur |sa |un )?(emploi|travail)|perte d.emploi|licenci|mis . pied|sans emploi|ch.mage|pas de revenu|en gr.ve|lock-out",
    "income_reduction": r"(hours|shifts?) (were |was |have been |got |are )?(cut|reduced)|(reduced|fewer|less|cut) (hours|shifts|pay|income|wages?)|(pay|wages?|salary|income) (was |were |has been |got )?(cut|reduced|dropped)|pay cut|lost (his |her |their |my )?overtime|only getting \d+ days|(one|single) income|reduction.{0,30}(hours|income)|heures.{0,30}(r.dui|coup)|moins d.heures|baisse.{0,30}revenu|salaire.{0,30}r.dui|seul revenu|revenu.{0,20}(baisse|diminu)",
    "income_delay": r"\bpay(check|cheque|roll)? (is |was |has been |came )?late|late (pay|salary|wages)|payroll.{0,20}delay|salary.{0,20}delay|\bpay(check|cheque|day)? (is |was |has been )?delayed|waiting (on|for) (my |his |her |their )?(pay|salary|income|wages|ei|employment insurance|benefits)|\bei\b.{0,20}not started|applied for (ei|employment insurance|benefits)|\bei claim|paye.{0,20}retard|salaire.{0,20}retard|attend (l.)?(ae|assurance.emploi|prestations|paye|salaire)|en attente (de |des |d.)(l.)?(ae|assurance.emploi|prestations)",
    "payment_difficulty": r"cannot (afford|pay)|can.t (afford|pay)|unable to (afford|pay)|no money|not enough money|financial difficult|struggling|(money|budget|finances) (is |are )?(very |really |a bit )?tight|tight (budget|month)|things are (hard|tough|difficult)|difficult.{0,3}financ|difficile.{0,3}financ|financi.rement difficile|ne (peux|peut|pouvons) pas payer|c.est serr|serr. ce mois|pas.{0,15}argent|fins? de mois difficile",
    "hardship_request": r"hardship (te|ta|op|pro|pla|ass|rel|req|spe|app|arr)|(asked|asks|request(ed|s)?|applied) (about |for )?(a )?hardship|payment relief|payment deferral|defer(ral| the| my)? (payment|pmt)|(reduced|lower|smaller) (payment|pmt)|payment reduction|(pmt|payment) (can|could) be (reduced|lowered)|reduce (the |my |his |her |their )?(pmt|payment)|all.gement|report de paiement|paiement r.duit|(pmt|paiement) peut .tre r|r.duire (le |son |mon )?(pmt|paiement)|.quipe.{0,3}diff?icult",
    "expense_pressure": r"\brent.{0,20}(increase|raised|higher|went up)|unexpected (expense|bill|cost)|\bcosts?.{0,20}(rise|rising|increase)|rate reset|renewed at (a )?higher rate|(payment|pmt|mortgage)s? (went|has gone|goes|gone) up|payment (increase|shock)|higher (interest )?rate|loyer.{0,20}(hausse|augment)|d.pense.{0,20}impr.vu|taux plus .lev|hausse (du |de )?(taux|paiement)|renouvel.{0,40}taux",
    "illness_or_injury": r"off work sick|sick leave|on (medical|sick|disability) leave|medical leave|in (the )?hospital|hospitali|surgery|injur(y|ed)|(short|long).term disability|disability (claim|benefit|leave)|unable to work|accident (at work|de travail)|arr.t (de travail|maladie)|cong. (de )?maladie|invalidit. (de )?(courte|longue)|blessure|chirurgi",
    "separation": r"s.paration|separating|split (up )?(w/|with|from) (my |his |her |their )?(partner|spouse|husband|wife)|(getting|going through a|going thru a) divorce|divorcing",
    "disaster_or_evacuation": r"flood|wildfire|forest fire|house fire|evacu|natural disaster|hurricane|tornado|earthquake|storm damage|inond|feux de for.t|cause des feux|incendie|catastrophe|sinistr",
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
    from app.settings import SNAPSHOT
    day = date.fromisoformat(SNAPSHOT)
    week_start, next_day = day - timedelta(days=6), day + timedelta(days=1)
    return f"""WITH cases AS (
      SELECT customer_id,count(*) FILTER(WHERE outcome IS NULL) open_cases,
      coalesce(sum(total_overdue) FILTER(WHERE outcome IS NULL),0) total_overdue,
      max(current_dpd) FILTER(WHERE outcome IS NULL) max_dpd
      FROM gold.cases WHERE case_open_date<=DATE '{day}' GROUP BY 1
    ), promises AS (
      SELECT i.customer_id,count(*) FILTER(WHERE p.ptp_status IN ('kept','partially_kept','broken')) resolved_promises,
      count(*) FILTER(WHERE p.ptp_status='broken') broken_promises
      FROM curated.promises_to_pay p JOIN gold.crm_identity i USING(crm_customer_id)
      WHERE p.status_ts<TIMESTAMP '{next_day}' GROUP BY 1
    ), contacts AS (
      SELECT i.customer_id,count(*) contacts_7d FROM curated.contact_history h
      JOIN gold.crm_identity i USING(crm_customer_id)
      WHERE h.direction='outbound' AND coalesce(h.channel,h.channel_v2)!='system'
       AND h.contact_ts_utc>=TIMESTAMP '{week_start}' AND h.contact_ts_utc<TIMESTAMP '{next_day}' GROUP BY 1
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
        {'name':'contacts_7d','definition':'Outbound contacts in the 7 days ending on the snapshot date, inclusive; system events excluded','source':'curated.contact_history','type':'integer'},
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
