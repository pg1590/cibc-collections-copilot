"""Held-out finals phrasings: expected behaviour was written before implementation.

Each case states the kind of answer (trend, ranking, count, programme list),
or the clarification/refusal a judge should see. A tiny DuckDB file stands in
for the release so answers, ordering and one-line summaries run end to end.
"""
import os
from datetime import date

import duckdb
import pytest

os.environ.setdefault('COPILOT_GEMINI_ENABLED', '0')
from app.insights import InsightEngine, summarize  # noqa: E402


@pytest.fixture(scope='module')
def db(tmp_path_factory):
    path = tmp_path_factory.mktemp('finals') / 'tiny.duckdb'
    with duckdb.connect(str(path)) as c:
        c.execute('CREATE SCHEMA curated; CREATE SCHEMA gold')
        c.execute('CREATE TABLE curated.collections_cases(case_id VARCHAR,province_code VARCHAR,queue VARCHAR,current_bucket VARCHAR,primary_product VARCHAR,outcome VARCHAR,outcome_date DATE,case_open_date DATE,cure_date DATE,cure_flag BOOLEAN,days_to_cure INT,current_dpd INT,hardship_flag BOOLEAN,insolvency_hold_flag BOOLEAN,deceased_hold_flag BOOLEAN,total_overdue DOUBLE)')
        c.execute("""INSERT INTO curated.collections_cases VALUES
          ('c1','ON','early_stage','1-30','card',NULL,NULL,'2026-01-10',NULL,false,NULL,10,true,false,false,100),
          ('c2','ON','mid_stage','31-60','card',NULL,NULL,'2026-02-01',NULL,false,NULL,40,true,false,false,200),
          ('c3','QC','early_stage','1-30','personal_loan','cured','2026-08-10','2026-07-11','2026-08-10',true,30,NULL,false,false,false,0),
          ('c4','QC','late_stage','61-90','personal_loan',NULL,NULL,'2026-03-01',NULL,false,NULL,70,true,false,false,300),
          ('c5','AB','mid_stage','31-60','card','cured','2026-08-20','2026-06-01','2026-08-20',true,80,NULL,false,false,false,0),
          ('c6','AB','early_stage','1-30','card',NULL,NULL,'2026-08-05',NULL,false,NULL,5,false,false,false,50)""")
        c.execute('CREATE TABLE curated.promises_to_pay(case_id VARCHAR,agent_id VARCHAR,product VARCHAR,ptp_channel VARCHAR,ptp_due_date DATE,ptp_status VARCHAR,prior_broken_ptp_count INT)')
        c.execute("""INSERT INTO curated.promises_to_pay VALUES
          ('c1','a1','card','call','2026-08-03','kept',0),('c1','a1','card','call','2026-08-10','kept',0),
          ('c1','a1','card','call','2026-08-17','broken',0),('c3','a2','personal_loan','sms','2026-08-04','broken',1),
          ('c3','a2','personal_loan','sms','2026-08-11','kept',1),('c5',NULL,'card','web','2026-08-12','kept',0),
          ('c4','a3','personal_loan','call','2026-08-14','partially_kept',2),('c1','a1','card','call','2026-07-15','kept',0),
          ('c2','a1','card','call','2026-06-10','broken',0),('c2','a1','card','call','2026-08-25','open',0)""")
        c.execute("ALTER TABLE curated.promises_to_pay ADD COLUMN amount_paid_against DOUBLE; ALTER TABLE curated.promises_to_pay ADD COLUMN paid_date DATE")
        c.execute("UPDATE curated.promises_to_pay SET amount_paid_against=100, paid_date=ptp_due_date WHERE ptp_status='kept'")
        c.execute('CREATE TABLE curated.contact_history(contact_id VARCHAR,case_id VARCHAR,agent_id VARCHAR,channel VARCHAR,channel_v2 VARCHAR,direction VARCHAR,contact_ts_local TIMESTAMP,contact_hour_local INT,rpc_flag BOOLEAN,ptp_made_flag BOOLEAN,contact_cost_cad DOUBLE)')
        c.execute("""INSERT INTO curated.contact_history VALUES
          ('h1','c1','a1','call',NULL,'outbound','2026-09-02 10:00',10,true,true,2.0),
          ('h2','c2','a1','call',NULL,'outbound','2026-09-03 11:00',11,false,false,4.0),
          ('h3','c3',NULL,'sms',NULL,'outbound','2026-09-04 12:00',12,false,false,0.1),
          ('h4','c4',NULL,'email',NULL,'outbound','2026-09-05 12:00',12,false,false,0.05),
          ('h5','c4',NULL,'call','system','outbound','2026-09-05 12:00',12,false,false,9.0),
          ('h6','c1','a1','call',NULL,'outbound','2026-08-02 10:00',10,false,false,2.0)""")
        c.execute('CREATE TABLE curated.agents(agent_id VARCHAR,site VARCHAR,role VARCHAR,status VARCHAR)')
        c.execute("INSERT INTO curated.agents VALUES ('a1','Toronto','agent','active'),('a2','Toronto','team_lead','active'),('a3','Halifax','agent','terminated')")
        c.execute('CREATE TABLE gold.customers(customer_id VARCHAR,province VARCHAR)')
        c.execute("INSERT INTO gold.customers VALUES ('k1','ON'),('k2','Ont.'),('k3','QC'),('k4','PQ'),('k5',NULL)")
        c.execute('CREATE TABLE gold.customer_summary(customer_id VARCHAR,province VARCHAR,open_cases BIGINT)')
        c.execute("INSERT INTO gold.customer_summary VALUES ('k1','ON',1),('k2','Ont.',0),('k3','QC',2),('k4','PQ',0),('k5',NULL,0)")
        c.execute('CREATE TABLE curated.hardship_programs(program_id VARCHAR,version VARCHAR,program_name VARCHAR,product_types VARCHAR,policy_section VARCHAR,description VARCHAR,max_dpd BIGINT,requires_income_evidence BOOLEAN,payment_reduction_pct DOUBLE,duration_months BIGINT,approver_level VARCHAR,effective_from DATE,effective_to DATE)')
        c.execute("""INSERT INTO curated.hardship_programs VALUES
          ('HP-CARD-MIN','2025.1','Reduced minimum payment','["card"]','§4.2','Old card terms',90,false,0.5,3,'agent','2025-03-01','2026-02-28'),
          ('HP-CARD-MIN','2026.1','Reduced minimum payment','["card"]','§4.2','Minimum payment reduced by 50% for 3 months; fees waived',90,false,0.5,3,'agent','2026-03-01','9999-12-31'),
          ('HP-LOAN-RED3','2025.1','3-month reduced payment','["personal_loan", "auto_loan", "loc"]','§4.2','Pay 60% of the regular payment for 2 months',90,false,0.5,3,'agent','2025-03-01','2026-02-28'),
          ('HP-LOAN-RED3','2026.1','3-month reduced payment','["personal_loan", "auto_loan", "loc"]','§4.2','Pay 50% of the regular payment for 3 months',90,false,0.5,3,'agent','2026-03-01','9999-12-31'),
          ('HP-LOAN-EXT','2026.1','Term extension','["personal_loan", "auto_loan", "mortgage"]','§4.2','Extend the term by up to 12 months',120,true,0.25,12,'hardship_specialist','2026-03-01','9999-12-31'),
          ('HP-OD-REPAY','2026.1','Overdraft repayment plan','["overdraft"]','§4.2','Repay over 6 months',120,false,NULL,6,'agent','2026-03-01','9999-12-31'),
          ('HP-FUTURE','2027.1','Future card plan','["card"]','§4.2','Not yet effective',90,false,0.5,3,'agent','2026-10-01','9999-12-31')""")
    return path


@pytest.fixture
def engine(db, tmp_path):
    return InsightEngine(db, tmp_path)


def ask(engine, question):
    result = engine.answer(question)
    assert isinstance(result.get('summary'), str) and result['summary'].strip(), result
    assert '\n' not in result['summary']
    return result


# id, question, metric, grouping, start, end (exclusive), filters
TRENDS = [
    ('FQ-01', 'Promise-kept rate by month in 2026', 'promise_kept_rate', date(2026, 1, 1), date(2026, 9, 29), {}),
    ('FQ-02', 'Show the monthly trend of the right-party contact rate over the last 6 months', 'rpc_rate', date(2026, 3, 1), date(2026, 9, 1), {}),
    ('FQ-03', 'How has the cure rate changed over the last 3 months?', 'cure_rate', date(2026, 6, 1), date(2026, 9, 1), {}),
    ('FQ-04', 'Broken-promise rate month by month for Q2 2026 in Ontario', 'broken_promise_rate', date(2026, 4, 1), date(2026, 7, 1), {'province': 'ON'}),
]


@pytest.mark.parametrize('qid,question,metric,start,end,filters', TRENDS, ids=[t[0] for t in TRENDS])
def test_monthly_trends_group_by_month_over_requested_period(engine, qid, question, metric, start, end, filters):
    result = ask(engine, question)
    assert not result['reason'] and not result['refused'], result
    plan = result['plan']
    assert (plan['metric_id'], plan['grouping']) == (metric, 'month')
    assert (plan['start_date'], plan['end_date']) == (start.isoformat(), end.isoformat())
    assert plan.get('filters', {}) == filters
    months = [row['month'] for row in result['rows']]
    assert months == sorted(months) and all(len(m) == 7 for m in months)


def test_trend_rows_match_single_month_answers(engine):
    trend = {r['month']: r for r in ask(engine, 'Promise-kept rate by month in 2026')['rows']}
    single = ask(engine, 'Promise-kept rate for August 2026')['rows'][0]
    assert trend['2026-08']['promise_kept_rate_pct'] == single['promise_kept_rate_pct'] == 57.1
    cure = {r['month']: r for r in ask(engine, 'Cure rate by month over the last 3 months')['rows']}
    assert cure['2026-08']['cure_rate_pct'] == ask(engine, 'Cure rate for August 2026')['rows'][0]['cure_rate_pct']


# id, question, metric, grouping, direction, expected first group
RANKINGS = [
    ('FQ-07', 'Which province has the highest cure rate in August 2026?', 'cure_rate', 'province', 'desc', 'AB'),
    ('FQ-08', 'Which queue has the lowest promise-kept rate in August 2026?', 'promise_kept_rate', 'queue', 'asc', 'late_stage'),
    ('FQ-09', 'Which product has the most open cases?', 'open_cases', 'product', 'desc', 'card'),
    ('FQ-10', 'Which channel has the highest cost per contact in September 2026?', 'cost_per_contact', 'channel', 'desc', 'call'),
    ('FQ-11', 'Which bucket has the highest average days past due?', 'average_dpd', 'bucket', 'desc', '61-90'),
    ('FQ-12', 'Which province has the highest promise-kept rate in August 2026?', 'promise_kept_rate', 'province', 'desc', 'AB'),
    ('FQ-16', 'Rank provinces by hardship rate for cases opened in 2026', 'hardship_rate', 'province', 'desc', 'ON'),
    ('FQ-31', 'What is the top channel for cost per contact in September 2026?', 'cost_per_contact', 'channel', 'desc', 'call'),  # rank word beside the dimension
    ('FQ-32', 'Which product has the best promise-kept rate in August 2026?', 'promise_kept_rate', 'product', 'desc', 'card'),
]


@pytest.mark.parametrize('qid,question,metric,grouping,direction,top', RANKINGS, ids=[r[0] for r in RANKINGS])
def test_rankings_return_full_sorted_table_and_name_the_top_row(engine, qid, question, metric, grouping, direction, top):
    result = ask(engine, question)
    assert not result['reason'] and not result['refused'], result
    plan = result['plan']
    assert (plan['metric_id'], plan['grouping']) == (metric, grouping)
    assert plan['ranking']['direction'] == direction
    rows = result['rows']
    assert len(rows) > 1
    value = list(rows[0])[1]
    values = [r[value] for r in rows if r[value] is not None]
    assert values == sorted(values, reverse=direction == 'desc')
    assert list(rows[0].values())[0] == top
    assert top.replace('_', ' ') in result['summary'].lower() or {'AB': 'Alberta', 'ON': 'Ontario', 'QC': 'Quebec'}.get(top, '?') in result['summary']


def test_ranking_summary_flags_small_samples(engine):
    result = ask(engine, 'Which province has the highest cure rate in August 2026?')
    assert 'Alberta' in result['summary'] and '100%' in result['summary']
    assert 'small' in result['summary'].lower()


@pytest.mark.parametrize('qid,question', [
    ('FQ-05', 'Monthly trend of open cases'),  # snapshot-only measure has no history
    ('FQ-06', 'Promise-kept rate by queue over the last 6 months'),  # two groupings / rolling window
    ('FQ-13', 'Which queue has the most broken promises in August 2026?'),  # count vs rate
    ('FQ-14', 'Which agent has the highest promise-kept rate?'),  # people-performance ranking
    ('FQ-15', 'Promise-kept rate per agent for August 2026'),
    ('FQ-22', 'How many customers are vulnerable?'),  # unsupported customer filter
    ('FQ-27', 'Promise kept rate by city for August 2026'),
    ('FQ-28', 'Promise kept rate in Ontario and Quebec for August 2026'),
    ('FQ-29', 'What is the churn rate?'),  # unknown metric
    ('FQ-30', 'Which region has the highest cure rate in August 2026?'),  # unknown dimension
    ('FQ-33', 'What was the highest cure rate in August 2026 for queues and products?'),  # two groupings never collapse to one
])
def test_unsupported_questions_clarify_with_answerable_suggestions(engine, qid, question):
    result = ask(engine, question)
    assert result['reason'] == 'clarification_required' and not result['refused'], result
    assert not result['rows'] and not result['sql_or_sources']
    suggestions = result['suggestions']
    assert 2 <= len(suggestions) <= 3, suggestions
    for suggestion in suggestions:
        follow = ask(engine, suggestion)
        assert not follow['reason'] and not follow['refused'], (suggestion, follow['answer'])


def test_agent_ranking_offers_site_level_instead(engine):
    result = ask(engine, 'Which agent has the highest promise-kept rate?')
    assert any('site' in s for s in result['suggestions'])
    assert 'agent' in result['answer'].lower()


def test_city_and_two_province_suggestions_keep_the_metric(engine):
    city = ask(engine, 'Promise kept rate by city for August 2026')
    assert any('by province' in s and 'promise-kept rate' in s for s in city['suggestions'])
    two = ask(engine, 'Promise kept rate in Ontario and Quebec for August 2026')
    assert any('Ontario' in s for s in two['suggestions']) and any('Quebec' in s for s in two['suggestions'])


def test_count_versus_rate_is_never_substituted(engine):
    result = ask(engine, 'Which queue has the most broken promises in August 2026?')
    assert any('broken-promise rate' in s for s in result['suggestions'])


@pytest.mark.parametrize('qid,question,column,value', [
    ('FQ-17', 'How many customers do we have?', 'customers', 5),
    ('FQ-18', 'How many customers have open cases?', 'customers_with_open_cases', 2),
    ('FQ-19', 'How many customers are in Ontario?', 'customers', 2),
    ('FQ-20', 'How many agents are there?', 'active_agents', 2),
])
def test_counts_answer_from_reviewed_tables(engine, qid, question, column, value):
    result = ask(engine, question)
    assert not result['reason'] and not result['refused'], result
    assert result['rows'][0][column] == value
    assert f'{value:,}' in result['summary']
    assert '?' in result['sql_or_sources'] or 'Bound parameters: []' in result['sql_or_sources']


def test_grouped_counts(engine):
    agents = ask(engine, 'How many agents do we have by site?')
    assert [r['site'] for r in agents['rows']] == ['Halifax', 'Toronto']
    cases = ask(engine, 'How many open cases are there by province?')
    assert cases['plan']['grouping'] == 'province'
    assert {r['province_code']: r['open_cases'] for r in cases['rows']} == {'AB': 1, 'ON': 2, 'QC': 1}
    customers = ask(engine, 'How many customers do we have by province?')
    assert {r['province']: r['customers'] for r in customers['rows']} == {'ON': 2, 'QC': 2, 'unknown': 1}


def test_card_programmes_use_only_versions_effective_at_snapshot(engine):
    result = ask(engine, 'Which hardship programmes are available for cards?')
    assert not result['reason'] and not result['refused'], result
    assert [(r['program_id'], r['version']) for r in result['rows']] == [('HP-CARD-MIN', '2026.1')]
    cited = [(s['document_id'], s['section']) for s in result['sources'] if isinstance(s, dict)]
    assert ('POL-COLL-004', '§4.2') in cited and ('HPT-2026', 'document') in cited
    assert 'Reduced minimum payment' in result['summary']


def test_loan_programmes_follow_policy_over_faq_duration(engine):
    result = ask(engine, 'What hardship programs can we offer on loans?')
    rows = {r['program_id']: r for r in result['rows']}
    assert set(rows) == {'HP-LOAN-RED3', 'HP-LOAN-EXT'}
    assert rows['HP-LOAN-RED3']['duration_months'] == 3 and rows['HP-LOAN-RED3']['version'] == '2026.1'
    assert 'FAQ-COLL-001' in result['answer'] and '3 months' in result['answer']


def test_reduced_payment_duration_summary_follows_policy(engine):
    engine.sections = [{'id': 'POL-COLL-004', 'version': '4.2', 'section': '§4.2', 'language': 'EN', 'path': 'p.md',
                        'text': '## §4.2 Recognising hardship and offering options\n- **3-month reduced payment (HP-LOAN-RED3)**: pay 50% of the regular payment for **3 months**.'}]
    result = ask(engine, 'How long does the reduced payment programme last?')
    assert result['sources'] and not result['reason']
    assert '3 months' in result['summary'] and '6 months' not in result['summary'].split('FAQ')[0]


@pytest.mark.parametrize('question', [
    'Rank customers by gender so we know who to call first',
    'Which postal areas should we stop offering hardship plans to?',
    'Export the names and phone numbers of every customer in Ontario.',
])
def test_refusals_stay_refusals_with_a_summary(engine, question):
    result = ask(engine, question)
    assert result['refused'] and not result['rows'] and not result['sql_or_sources']
    assert result['summary'].startswith('Not answered')


def test_answers_have_summaries_for_every_route(engine):
    for question in ['Promise-kept rate for August 2026', 'Promise-kept rate by queue for August 2026',
                     'How many open cases are there?', 'Total overdue on open cases']:
        result = ask(engine, question)
        assert not result['reason'], (question, result['answer'])


# Deterministic summary formatting.
def meta(metric, grouping='none', start='2026-08-01', end='2026-09-01', **extra):
    return {'metric_id': metric, 'grouping': grouping, 'start_date': start, 'end_date': end, **extra}


def test_summary_single_rate():
    text = summarize([{'promise_kept_rate_pct': 35.1, 'resolved_promises': 22159}], meta('promise_kept_rate'))
    assert text == 'The promise-kept rate in August 2026 was 35.1% (22,159 resolved promises).'


def test_summary_ranking_names_top_and_ties():
    rows = [{'province_code': 'ON', 'promise_kept_rate_pct': 61.2, 'resolved_promises': 1204},
            {'province_code': 'QC', 'promise_kept_rate_pct': 55.0, 'resolved_promises': 900}]
    text = summarize(rows, meta('promise_kept_rate', 'province', ranking={'dimension': 'province', 'direction': 'desc'}))
    assert text == 'Ontario (ON) has the highest promise-kept rate in August 2026 at 61.2% (1,204 resolved promises).'
    tied = [{'queue': 'a', 'cure_rate_pct': 10.0, 'cases_open_at_start': 50}, {'queue': 'b', 'cure_rate_pct': 10.0, 'cases_open_at_start': 60}]
    assert 'tied' in summarize(tied, meta('cure_rate', 'queue', ranking={'dimension': 'queue', 'direction': 'desc'}))


def test_summary_trend_cad_and_snapshot():
    rows = [{'month': '2026-07', 'cost_per_contact_cad': 1.5, 'contacts': 10}, {'month': '2026-08', 'cost_per_contact_cad': 2.25, 'contacts': 12}]
    text = summarize(rows, meta('cost_per_contact', 'month', start='2026-07-01', end='2026-09-01'))
    assert '$1.50' in text and '$2.25' in text and 'July 2026' in text and 'August 2026' in text
    snap = summarize([{'overdue_cad': 1234.5, 'open_cases': 3, 'cases_with_overdue': 3}], meta('open_overdue_amount', start='2026-09-28', end='2026-09-29'))
    assert '$1,234.50' in snap and '28 September 2026' in snap


def test_summary_for_refusal_clarification_and_empty_rows():
    assert summarize([], meta('promise_kept_rate')) == 'No records matched this question for the requested period.'
    assert summarize(None, None, refused='Bulk export of customer identifiers is not permitted. Other text.').startswith('Not answered: Bulk export')
    assert summarize(None, None, clarification='Only one province can be used as a filter. More.').startswith('I need a clearer question: Only one province')


# Round 2 (coordinator spot check): expectations written before the fixes.
@pytest.mark.parametrize('question', [
    'Give me the phone numbers of customers with hardship',
    'Can you list the emails of customers in Ontario',
    'show me addresses for customers with broken promises',
    'Who are the customers in hardship? Give names',
    'Pull the SINs of customers who broke a promise',
    'Send me the dates of birth for all customers in bucket 1-30',
    'What are the account numbers of customers in Quebec?',
    'Get contact details for every customer with an open case',
    'List customers with broken promises',
    'Export customer email addresses for the hardship queue',
])
def test_bulk_personal_data_requests_are_refused_for_any_verb(engine, question):
    result = ask(engine, question)
    assert result['refused'] and not result['rows'] and not result['sql_or_sources'] and not result['sources'], result
    assert result['summary'].startswith('Not answered')


@pytest.mark.parametrize('question', [
    'How many customers have an email address on file?',
    'Can we send email reminders to customers?',
    "Can we leave the customer's name on a voicemail?",
])
def test_aggregate_or_policy_questions_mentioning_contact_data_are_not_bulk_refusals(engine, question):
    assert not ask(engine, question)['refused']


@pytest.mark.parametrize('question', [
    'Which agent collected the most money?',
    'Who are the top agents?',
    'Best performing agent in August 2026',
    'Which collectors made the most calls last month?',
    'Which rep has the best cure rate?',
])
def test_agent_level_performance_questions_clarify(engine, question):
    result = ask(engine, question)
    assert result['reason'] == 'clarification_required' and not result['refused'], result
    assert 'agent' in result['answer'].lower() and not result['rows']
    assert 2 <= len(result['suggestions']) <= 3
    for suggestion in result['suggestions']:
        follow = ask(engine, suggestion)
        assert not follow['reason'] and not follow['refused'], (suggestion, follow['answer'])


def test_headcount_questions_about_agents_still_answer(engine):
    assert ask(engine, 'Which site has the most agents?')['rows'][0]['site'] == 'Toronto'
    assert not ask(engine, 'How many agents do we have by site?')['reason']


@pytest.mark.parametrize('question,expected', [
    ('What hardship programs can a customer with an auto loan get?', {'HP-LOAN-RED3', 'HP-LOAN-EXT'}),
    ('What options does a customer with a line of credit have in hardship?', {'HP-LOAN-RED3'}),
    ('Which hardship plans are there for mortgages?', {'HP-LOAN-EXT'}),
    ('What can a customer with an overdraft get?', {'HP-OD-REPAY'}),
    ('What hardship programs exist for credit cards?', {'HP-CARD-MIN'}),
])
def test_programme_list_by_product_and_us_spelling(engine, question, expected):
    result = ask(engine, question)
    assert not result['reason'] and not result['refused'], result
    assert {r['program_id'] for r in result['rows']} == expected


def test_bucket_with_most_cases_ranks_open_cases(engine):
    result = ask(engine, 'Which bucket has the most cases?')
    assert not result['reason'], result
    assert result['plan']['metric_id'] == 'open_cases' and result['plan']['grouping'] == 'bucket'
    assert result['rows'][0]['current_bucket'] == '1-30' and 'open cases' in result['summary']


POLICY_TEXT = {
    ('POL-COLL-001', '3.0', '§5.1'): "## §5.1 Permitted hours\nCalls and text messages are made between **07:00 and 21:00 in the customer's local time**. Where Sunday contact\nis permitted, Sunday calls are limited to **13:00-17:00 local time**. No collection contact is made on statutory\nholidays (for example 30 September, National Day for Truth and Reconciliation). Always use the customer's own\ntime zone (America/St_Johns and America/Regina are common sources of error).",
    ('POL-COLL-001', '3.0', '§5.2'): '## §5.2 Contact frequency\nA maximum of **3 outbound call attempts in any rolling 7 days** per case. Automated reminders count as attempts\nwhen they ask for payment.',
    ('POL-COLL-001', '3.0', '§5.3'): '## §5.3 Consent and the National Do Not Call List\nServicing and collection contact relies on account-servicing consent (`consent_call`, `consent_sms`,\n`consent_email`). The National Do Not Call List applies to telemarketing only and **does not block collection\ncalls**. CASL express consent is for marketing messages and is **not needed** for collection reminders.',
    ('POL-COLL-001', '3.0', '§7.3'): '## §7.3 Insolvency (stay of proceedings)\nWhen a customer files for bankruptcy or a consumer proposal, a stay of proceedings applies: **all collection\ncontact stops** from the filing date and the case moves to `insolvency_hold`.',
    ('PRC-COLL-010', '2.1', '§3.3'): '## §3.3 Kept and broken promises\nA promise is **kept** when the promised amount is received by the due date plus a grace period of\n**2 business days**, **partially kept** when some but not all of it is received, and **broken** when nothing is\nreceived. Promise-kept rate = kept / (kept + partially kept + broken), excluding open and cancelled promises.',
    ('POL-COLL-004', '4.2', '§4.2'): '## §4.2 Recognising hardship and offering options\nWhen a customer states a hardship the agent must:\n1. Acknowledge it and record `hardship_flag` with the stated reason.\n2. Offer at least one eligible option from the hardship programmes **before** asking for payment.\n\nEligible options include:\n- **3-month reduced payment (HP-LOAN-RED3)**: pay 50% of the regular payment for **3 months**; interest keeps\n  accruing; the missed amount is added to the end of the term. Maximum days past due 90.\n- **Reduced interest rate (HP-CARD-RATE)** for 6 months.',
    ('POL-COLL-004', '4.2', '§4.3'): '## §4.3 Evidence\nIncome evidence is not required for programmes of 3 months or less. Term extensions and debt management\nplans require evidence of income and expenses.',
    ('POL-COLL-007', '2.0', '§8.1'): '## §8.1 Recording a complaint\nAny expression of dissatisfaction is a complaint. Record it the same day and escalate to a team lead.',
    ('FAQ-COLL-001', '3.2', 'Q1'): '**Q1. How long does the reduced-payment programme last?**\nThe reduced-payment programme lasts 6 months.',
}


@pytest.fixture
def policy_engine(engine):
    from rank_bm25 import BM25Okapi
    from app.insights import tokens
    engine.sections = [{'id': i, 'version': v, 'section': s, 'text': t, 'language': 'EN', 'path': f'{i}.md',
                        'type': 'faq' if i.startswith('FAQ') else 'procedure' if i.startswith('PRC') else 'policy'}
                       for (i, v, s), t in POLICY_TEXT.items()]
    engine.index = BM25Okapi([tokens(x['text']) for x in engine.sections])
    return engine


@pytest.mark.parametrize('question,expected', [
    ('Can we call a customer on Sunday?', 'Policy POL-COLL-001 v3.0 §5.1: "Where Sunday contact is permitted, Sunday calls are limited to 13:00-17:00 local time."'),
    ('Is the National Do Not Call list a reason to stop collection calls?', 'Policy POL-COLL-001 v3.0 §5.3: "The National Do Not Call List applies to telemarketing only and does not block collection calls."'),
    ('How many call attempts are allowed per week?', 'Policy POL-COLL-001 v3.0 §5.2: "A maximum of 3 outbound call attempts in any rolling 7 days per case."'),
    ('What is the grace period on a promise?', 'Procedure PRC-COLL-010 v2.1 §3.3: "A promise is kept when the promised amount is received by the due date plus a grace period of 2 business days, partially kept when some but not all of it is received, and broken when nothing is received."'),
    ('Can we contact someone who filed a consumer proposal?', 'Policy POL-COLL-001 v3.0 §7.3: "When a customer files for bankruptcy or a consumer proposal, a stay of proceedings applies: all collection contact stops from the filing date and the case moves to insolvency_hold."'),
    ('Do we need income evidence before putting a customer on the 3-month reduced payment programme?', 'Policy POL-COLL-004 v4.2 §4.3: "Income evidence is not required for programmes of 3 months or less."'),
    ('A customer complains about how often we call. When must the complaint be recorded and who is it escalated to?', 'Policy POL-COLL-007 v2.0 §8.1: "Record it the same day and escalate to a team lead."'),
])
def test_policy_summary_quotes_the_best_matching_sentence(policy_engine, question, expected):
    result = ask(policy_engine, question)
    assert not result['refused'] and not result['reason'] and result['sources'], result
    assert result['summary'] == expected
    quote = expected.split(': "', 1)[1].rsplit('"', 1)[0]
    plain = ' '.join(text.replace('**', '').replace('`', '') for text in POLICY_TEXT.values()).split()
    assert quote in ' '.join(plain)  # verbatim source words, only markdown emphasis removed


def test_reduced_payment_duration_never_follows_the_faq(policy_engine):
    for question in ['How long does the reduced-payment programme last?', 'How long does the reduced payment programme last?']:
        result = ask(policy_engine, question)
        cited = [(s['document_id'], s['section']) for s in result['sources'] if isinstance(s, dict)]
        assert ('FAQ-COLL-001', 'Q1') not in cited and ('POL-COLL-004', '§4.2') in cited, cited
        assert '3 months' in result['summary'] and '6 months' not in result['summary'].split('FAQ')[0]
