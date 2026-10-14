"""A different extract (another year, newer policy versions, a stricter contact cap) must
work without code changes: snapshot, holidays, citations, caps and the queue follow the data."""
from datetime import date, datetime, timezone

import duckdb
import pytest

from app import action_plan as ap
from app import holidays, snapshot, work_queue

# Wednesday 24 March 2027; Good Friday is 26 March 2027.
EXTRACT = datetime(2027, 3, 24, 3, 15)
LAST_CONTACT = datetime(2027, 3, 24, 5, 40)
AS_OF = datetime(2027, 3, 24, 6, 0, tzinfo=timezone.utc)


@pytest.fixture
def release(tmp_path):
    c = duckdb.connect(str(tmp_path / 'unseen.duckdb'))
    c.execute('CREATE SCHEMA curated; CREATE SCHEMA gold')
    c.execute("CREATE TABLE curated.collections_cases AS SELECT TIMESTAMP '2027-03-24 03:15' extract_ts")
    c.execute('''CREATE TABLE curated.contact_history(case_id VARCHAR, direction VARCHAR, channel VARCHAR, channel_v2 VARCHAR, contact_ts_utc TIMESTAMP)''')
    # Two attempts this week: with a per-case cap of 2, Wed and Thu are blocked; Fri is Good Friday.
    c.execute("""INSERT INTO curated.contact_history VALUES
        ('CS-1','outbound',NULL,'call',TIMESTAMP '2027-03-19 14:00'),('CS-1','outbound',NULL,'sms',TIMESTAMP '2027-03-24 05:40')""")
    c.execute('''CREATE TABLE curated.customers AS SELECT 'CRM-1' crm_customer_id, 'America/Halifax' time_zone, 'B3H' fsa, 'NS' province_code,
        'EN' preferred_language, true consent_call, true consent_sms, false consent_email, false internal_do_not_call_flag,
        false cease_communication_flag, '07:00' permitted_call_start_local, '21:00' permitted_call_end_local, false sunday_contact_permitted,
        'semi_monthly' pay_frequency, false credit_counselling_agency_flag, false legal_representative_flag, NULL::VARCHAR licensed_insolvency_trustee_name,
        NULL::VARCHAR third_party_relationship, false bankruptcy_flag, false consumer_proposal_flag, NULL::DATE insolvency_filed_date,
        false deceased_flag, false vulnerability_flag, TIMESTAMP '2027-03-24' extract_ts''')
    c.execute("CREATE TABLE gold.customers AS SELECT 'C-1' customer_id, 'CRM-1' crm_customer_id")
    c.execute("CREATE TABLE gold.customer_summary AS SELECT 'C-1' AS customer_id, 'Test Customer' AS name")
    c.execute('''CREATE TABLE gold.cases AS SELECT 'CS-1' case_id, 'C-1' customer_id, 'card' primary_product, 'C-9' primary_account_id,
        45 current_dpd, 420.0 total_overdue, 'open' case_status, true hardship_flag, NULL::VARCHAR hardship_plan_type, NULL::DATE hardship_plan_end,
        false dispute_flag, NULL::VARCHAR dispute_status, NULL::VARCHAR dispute_type, false complaint_flag, NULL::VARCHAR complaint_stage,
        false cease_contact_flag, false third_party_rep_flag, false insolvency_hold_flag, false deceased_hold_flag, false vulnerable_customer_flag,
        'AG-1' assigned_agent_id, NULL::VARCHAR current_ptp_id, NULL::DOUBLE current_ptp_amount, NULL::DATE current_ptp_due_date,
        DATE '2027-01-10' case_open_date, 2 contact_cap_7d, NULL::VARCHAR outcome, 'early' queue''')
    c.execute("CREATE TABLE curated.geo_reference(fsa VARCHAR, province_code VARCHAR, time_zone VARCHAR)")
    c.execute('CREATE TABLE curated.promises_to_pay(ptp_id VARCHAR, case_id VARCHAR, ptp_amount DOUBLE, ptp_due_date DATE, ptp_status VARCHAR)')
    c.execute('CREATE TABLE curated.offers(case_id VARCHAR, program_id VARCHAR, customer_response VARCHAR, plan_status VARCHAR, offer_ts TIMESTAMP, response_ts TIMESTAMP)')
    c.execute("CREATE TABLE curated.card_accounts AS SELECT 'C-9' card_account_id, DATE '2025-01-15' open_date")
    c.execute('CREATE TABLE curated.loan_accounts(loan_id VARCHAR, origination_date DATE)')
    c.execute('CREATE TABLE curated.deposit_accounts(deposit_account_id VARCHAR, open_date DATE)')
    c.execute('CREATE TABLE curated.salary_credit_history(crm_customer_id VARCHAR, employer_flag VARCHAR, last_credit_date DATE)')
    c.execute("CREATE TABLE curated.agents AS SELECT 'AG-1' agent_id, true vulnerable_customer_certified")
    c.execute('''CREATE TABLE curated.hardship_programs AS SELECT 'HP-CARD-MIN' program_id, '2027.1' AS "version", 'Reduced minimum payment' AS program_name,
        '["card"]' product_types, 'Minimum payment reduced' description, 'possible' min_hardship_level, 90 max_dpd, 6 min_months_on_book,
        1 max_uses_12m, true excludes_insolvency, true excludes_broken_plan_90d, false requires_income_evidence, 'agent' approver_level,
        DATE '2027-03-01' effective_from, DATE '9999-12-31' effective_to''')
    c.execute('''CREATE TABLE curated.reference_documents AS SELECT * FROM (VALUES
        ('POL-COLL-001','3.1','EN',DATE '2027-01-01',NULL),('POL-COLL-004','5.0','EN',DATE '2027-02-01',NULL),
        ('HPT-2027','2027.1','EN',DATE '2027-03-01',NULL),('POL-COLL-004-V4.2','4.2','EN',DATE '2026-03-01','POL-COLL-004'))
        t(doc_id,version,language,effective_date,superseded_by)''')
    ap._versions_loaded = False
    yield c
    c.close()
    ap._versions_loaded = False
    ap.use_document_versions({})


def test_snapshot_is_read_from_the_extract(release, tmp_path):
    found = snapshot.write(release, tmp_path / 'snapshot.json')
    assert found['snapshot_date'] == '2027-03-24'
    assert datetime.fromisoformat(found['as_of_utc']) == AS_OF  # latest contact 05:40, rounded up
    assert snapshot.load(tmp_path / 'snapshot.json')['snapshot_date'] == '2027-03-24'


def test_holidays_are_computed_for_any_year():
    days = holidays.between(date(2027, 1, 1), date(2027, 12, 31))
    assert days[date(2027, 3, 26)] == 'Good Friday' and days[date(2027, 5, 24)] == 'Victoria Day'
    assert days[date(2027, 10, 11)] == 'Thanksgiving Day' and days[date(2027, 9, 30)].startswith('National Day')
    assert date(2020, 9, 30) not in holidays.between(date(2020, 1, 1), date(2020, 12, 31))  # observed from 2021


def test_plan_follows_the_new_release(release):
    plan = ap.build(ap.load(release, 'C-1', AS_OF), 'recorded', as_of=AS_OF)
    window = plan['contact_window']
    reasons = {s['date']: s['reason'] for s in window['skipped']}
    # Per-case cap of 2 (not the default 3) blocks Wed/Thu; Good Friday is computed, not listed.
    assert reasons['2027-03-24'] == 'already 2 attempts in the last 7 days'
    assert reasons['2027-03-26'] == 'statutory holiday (Good Friday)'
    assert window['date'] == '2027-03-27' and window['time_zone'] == 'America/Halifax'
    # Citations use the versions current in this release, not the reviewed defaults.
    cited = {p for s in plan['steps'] for p in s['policy']}
    assert 'POL-COLL-004 v5.0 §4.2' in cited and 'POL-COLL-001 v3.1 §5.2' in cited
    assert not any('v3.0' in p or 'v4.2' in p for p in cited)
    offers = {o['program_id']: o for o in plan['programmes']}
    assert offers['HP-CARD-MIN']['status'] == 'likely_eligible' and 'HPT-2027 v2027.1' in offers['HP-CARD-MIN']['source']
    assert plan['as_of'] == AS_OF.isoformat()
    assert plan['payday_estimate'] == '2027-03-31'


def test_queue_uses_the_case_cap_and_new_as_of(release):
    queue = work_queue.build(release, 'AG-1', as_of=AS_OF)
    item = queue['items'][0]
    assert item['tier'] == 'hardship_no_plan' and item['next_contact']['date'] == '2027-03-27'
    assert item['next_contact']['attempts_last_7d'] == 2
