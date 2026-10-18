"""Overdue-amount and days-past-due thresholds: applied as bound parameters, or clarified, never dropped.

Before this, "How many open cases have total overdue above 800?" silently answered the total for
every open case. A threshold the engine cannot apply must now ask for clarification instead.
"""
import os

import duckdb
import pytest

os.environ.setdefault('COPILOT_GEMINI_ENABLED', '0')
from app.insights import InsightEngine, Plan, amount_threshold, dpd_threshold  # noqa: E402
from app.metric_plans import PlanError, compile_plan  # noqa: E402
from app.settings import SNAPSHOT  # noqa: E402

NEXT_DAY = __import__('datetime').date.fromisoformat(SNAPSHOT) + __import__('datetime').timedelta(days=1)


@pytest.fixture(scope='module')
def db(tmp_path_factory):
    path = tmp_path_factory.mktemp('thresholds') / 'tiny.duckdb'
    with duckdb.connect(str(path)) as c:
        c.execute('CREATE SCHEMA curated; CREATE SCHEMA gold')
        c.execute('CREATE TABLE curated.collections_cases(case_id VARCHAR,province_code VARCHAR,queue VARCHAR,current_bucket VARCHAR,primary_product VARCHAR,'
                  'outcome VARCHAR,current_dpd INT,hardship_flag BOOLEAN,insolvency_hold_flag BOOLEAN,total_overdue DOUBLE)')
        # Open cases: overdue 100, 900, 1500, 2500, NULL; one closed case with 5000 overdue.
        c.execute("""INSERT INTO curated.collections_cases VALUES
          ('c1','ON','early_stage','1-30','card',NULL,10,false,false,100),
          ('c2','ON','late_stage','91-120','card',NULL,95,true,false,900),
          ('c3','QC','late_stage','121-150','personal_loan',NULL,130,false,false,1500),
          ('c4','ON','mid_stage','61-90','personal_loan',NULL,70,false,false,2500),
          ('c5','AB','early_stage','1-30','card',NULL,NULL,false,false,NULL),
          ('c6','ON','late_stage','151-180','card','cured',160,false,false,5000)""")
        c.execute('CREATE TABLE gold.customers(customer_id VARCHAR,province VARCHAR)')
        c.execute("INSERT INTO gold.customers VALUES ('k1','ON'),('k2','ON'),('k3','QC'),('k4','AB')")
        c.execute('CREATE TABLE gold.customer_summary(customer_id VARCHAR,province VARCHAR,open_cases BIGINT,total_overdue DOUBLE)')
        # Customer totals across open cases: 1000 (two cases), 1500, 0 open, NULL.
        c.execute("INSERT INTO gold.customer_summary VALUES ('k1','ON',2,1000),('k2','ON',0,0),('k3','QC',1,1500),('k4','AB',1,NULL)")
    return path


@pytest.fixture
def engine(db, tmp_path):
    return InsightEngine(db, tmp_path)


def answer(engine, question):
    result = engine.answer(question, 'supervisor')
    assert result['summary'] and '\n' not in result['summary']
    return result


def test_customers_over_an_amount_count_their_total_across_open_cases(engine):
    result = answer(engine, 'how many customers have overdue money of more than 800 dollars')
    assert result['rows'] == [{'customers_with_open_cases': 2}]  # k1 (1000 over two cases) and k3 (1500)
    assert result['plan']['filters'] == {'overdue': {'op': '>', 'value': 800}}
    sql, params = result['sql_or_sources'].split('\nBound parameters: ')
    assert '800' not in sql and params == '[800]'  # the amount is a bound parameter
    assert result['summary'].startswith('2 customers have more than $800 overdue in total')


def test_open_case_counts_and_totals_apply_the_amount_per_case(engine):
    count = answer(engine, 'How many open cases have more than $800 overdue?')
    assert count['rows'][0]['open_cases'] == 3 and 'more than $800 overdue each' in count['summary']
    total = answer(engine, 'How many open cases have total overdue above 800?')  # the phrasing that used to drop the threshold
    assert total['rows'][0]['overdue_cad'] == 4900 and total['rows'][0]['open_cases'] == 3
    at_least = answer(engine, 'How many customers owe 1500 dollars or more?')
    assert at_least['rows'] == [{'customers_with_open_cases': 1}] and at_least['plan']['filters']['overdue'] == {'op': '>=', 'value': 1500}


def test_days_past_due_thresholds_and_combinations(engine):
    over_90 = answer(engine, 'How many open cases are over 90 days past due?')
    assert over_90['rows'][0]['open_cases'] == 2 and over_90['plan']['filters'] == {'dpd': {'op': '>', 'value': 90}}
    combined = answer(engine, 'How many open cases in Ontario have more than $1,000 overdue and are over 60 days past due?')
    assert combined['rows'][0]['open_cases'] == 1  # c4 only
    assert combined['plan']['filters'] == {'province': 'ON', 'overdue': {'op': '>', 'value': 1000}, 'dpd': {'op': '>', 'value': 60}}
    grouped = answer(engine, 'How many open cases are 90+ days past due by queue?')
    assert grouped['rows'] == [{'queue': 'late_stage', 'open_cases': 2}]


def test_day_counts_are_not_read_as_money():
    assert amount_threshold('total overdue on open cases more than 150 days past due') == {}
    assert dpd_threshold('total overdue on open cases more than 150 days past due') == {'op': '>', 'value': 150}
    assert amount_threshold('customers with more than 2 overdue cases') == {}
    assert amount_threshold('how many customers owe over $1.5k') == {'op': '>', 'value': 1500}


def test_card_delinquency_definition_is_not_a_threshold():
    assert dpd_threshold('what share of active card accounts are 1 or more days past due today, by card product?') == {}


@pytest.mark.parametrize('question', [
    'What was the promise kept rate for promises over $500 in August 2026?',  # threshold on an unsupported measure
    'How many customers owe between $500 and $1000?',                         # ranges
    'How many customers have more than 2 open cases?',                        # a non-money count condition
    'How many customers are over 90 days past due?',                          # DPD is a case measure
    'How many open cases have more than $800 overdue and more than $2,000 overdue?',
])
def test_conditions_that_cannot_be_applied_clarify_instead_of_answering(engine, question):
    result = answer(engine, question)
    assert result['reason'] == 'clarification_required' and not result['rows']
    assert result['summary'].startswith('I need a clearer question')


def test_a_plan_that_drops_the_threshold_is_rejected():
    template = Plan('SELECT count(*) open_cases FROM curated.collections_cases WHERE outcome IS NULL', [])
    with pytest.raises(PlanError):
        InsightEngine._verify(template, 'how many open cases have more than $800 overdue?')
    with pytest.raises(PlanError):
        InsightEngine._verify(template, 'how many open cases are over 90 days past due?')


@pytest.mark.parametrize('filters', [
    {'overdue': {'op': '>', 'value': '800'}}, {'overdue': {'op': '!=', 'value': 800}}, {'overdue': {'op': '>', 'value': True}},
    {'overdue': {'op': '>', 'value': -1}}, {'dpd': {'op': '>', 'value': 90.5}}, {'overdue': {'op': '>', 'value': 800, 'sql': 'x'}},
])
def test_compiler_rejects_malformed_thresholds(filters):
    with pytest.raises(PlanError):
        compile_plan({'metric_id': 'open_cases', 'grouping': 'none', 'start_date': SNAPSHOT, 'end_date': NEXT_DAY.isoformat(), 'filters': filters})


def test_compiler_rejects_thresholds_on_other_measures():
    with pytest.raises(PlanError):
        compile_plan({'metric_id': 'promise_kept_rate', 'grouping': 'none', 'start_date': '2026-08-01', 'end_date': '2026-09-01',
                      'filters': {'overdue': {'op': '>', 'value': 500}}})
