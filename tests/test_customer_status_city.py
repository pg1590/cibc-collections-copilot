"""Customer counts by recorded status and city, with small-cell suppression, and related follow-ups."""
import os

import duckdb
import pytest

os.environ.setdefault('COPILOT_GEMINI_ENABLED', '0')
from app.insights import InsightEngine, customer_status  # noqa: E402
from app.metric_plans import PlanError  # noqa: E402


@pytest.fixture(scope='module')
def db(tmp_path_factory):
    path = tmp_path_factory.mktemp('status') / 'tiny.duckdb'
    with duckdb.connect(str(path)) as c:
        c.execute('CREATE SCHEMA curated; CREATE SCHEMA gold')
        c.execute('CREATE TABLE gold.customers(customer_id VARCHAR,crm_customer_id VARCHAR,province VARCHAR,bankruptcy_flag BOOLEAN,'
                  'consumer_proposal_flag BOOLEAN,deceased_flag BOOLEAN,cease_communication_flag BOOLEAN)')
        c.execute('CREATE TABLE curated.customers(crm_customer_id VARCHAR,city VARCHAR)')
        c.execute('CREATE TABLE gold.customer_summary(customer_id VARCHAR,province VARCHAR,open_cases BIGINT,total_overdue DOUBLE)')
        rows = []
        # Toronto: 230 customers, 15 bankrupt (10 with open cases), 12 with a consumer proposal.
        for i in range(230):
            rows.append((f'k{i}', f'C{i}', 'ON', i < 15, 15 <= i < 27, False, False, 'Toronto', 1 if i < 10 else 0, 900.0 if i < 10 else 0.0))
        # Montréal (two spellings): 210 customers, 3 bankrupt (a small cell).
        for i in range(230, 440):
            rows.append((f'k{i}', f'C{i}', 'QC', i < 233, False, False, False, 'Montréal' if i % 2 else 'Montreal', 0, 0.0))
        c.executemany('INSERT INTO gold.customers VALUES (?,?,?,?,?,?,?)', [r[:7] for r in rows])
        c.executemany('INSERT INTO curated.customers VALUES (?,?)', [(r[1], r[7]) for r in rows])
        c.executemany('INSERT INTO gold.customer_summary VALUES (?,?,?,?)', [(r[0], r[2], r[8], r[9]) for r in rows])
        c.execute('CREATE TABLE curated.collections_cases(case_id VARCHAR,province_code VARCHAR,queue VARCHAR,current_bucket VARCHAR,primary_product VARCHAR,'
                  'outcome VARCHAR,current_dpd INT,hardship_flag BOOLEAN,insolvency_hold_flag BOOLEAN,total_overdue DOUBLE)')
    return path


@pytest.fixture
def engine(db, tmp_path):
    return InsightEngine(db, tmp_path)


def ask(engine, question):
    result = engine.answer(question, 'supervisor')
    assert result['summary'] and '\n' not in result['summary']
    return result


def test_people_in_a_city_by_status(engine):
    result = ask(engine, 'how many people in toronto are bankrupt')
    assert result['rows'] == [{'customers': 15}]
    assert result['plan']['filters'] == {'status': 'bankrupt', 'city': 'Toronto'}
    assert result['summary'].startswith('15 customers in Toronto are recorded as bankrupt')
    sql, params = result['sql_or_sources'].split('\nBound parameters: ')
    assert 'toronto' not in sql.lower() and params == '["toronto"]'  # the city is a bound parameter


def test_status_city_and_open_cases_combine(engine):
    assert ask(engine, 'How many customers in Toronto filed a consumer proposal?')['rows'] == [{'customers': 12}]
    assert ask(engine, 'How many bankrupt customers in Toronto have open cases?')['rows'] == [{'customers_with_open_cases': 10}]
    assert ask(engine, 'How many customers are bankrupt or in a consumer proposal?')['rows'] == [{'customers': 30}]


def test_city_spellings_merge_and_small_counts_are_suppressed(engine):
    result = ask(engine, 'How many bankrupt customers are in Montreal?')
    assert result['rows'] == [{'customers': 'fewer than 10'}]  # 3, across both spellings
    assert result['summary'].startswith('Fewer than 10 customers in Montr')
    assert ask(engine, 'How many customers live in Montréal?')['rows'] == [{'customers': 210}]


@pytest.mark.parametrize('question', [
    'how many people in toronto',                          # customers or agents?
    'How many customers in Toronto and Montreal are bankrupt?',
    'how many bankrupt customers in toronto by province',  # a city is in one province
])
def test_ambiguous_customer_questions_clarify(engine, question):
    result = ask(engine, question)
    assert result['reason'] == 'clarification_required' and not result['rows']


def test_status_words():
    assert customer_status('how many customers are bankrupt') == 'bankrupt'
    assert customer_status('bankrupt or in a consumer proposal') == 'insolvent'
    assert customer_status('customers who asked us to stop calling') == 'cease'
    with pytest.raises(PlanError):
        customer_status('customers who are deceased or bankrupt')


def test_answers_offer_related_answerable_followups(engine):
    result = ask(engine, 'how many people in toronto are bankrupt')
    followups = result['followups']
    assert 1 <= len(followups) <= 3 and all(f.endswith('?') for f in followups)
    assert 'How many customers in Toronto have filed a consumer proposal?' in followups
    for question in followups:
        assert engine.answer(question, 'supervisor')['reason'] != 'clarification_required', question
