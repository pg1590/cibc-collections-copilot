"""Pinned finals demo customers: one per action-plan path, against the real local
database. Skipped where the dataset is not built (CI, teammates without data)."""
import duckdb
import pytest

from app import action_plan
from app.settings import DB

pytestmark = pytest.mark.skipif(not DB.exists(), reason='local dataset database is not built')

DEMO = [
    # customer, hardship status, expected headline start, expected step keys in order
    ('HAC-4447', 'not_established', "Don't contact this customer", ['restriction', 'representative']),
    ('GER-7918', 'not_established', 'Only talk to their representative', ['representative', 'hardship', 'promise', 'contact_window', 'payment_ask']),
    ('JEV-1240', 'recorded', 'Offer one of these hardship programmes first', ['representative', 'hardship', 'contact_window', 'payment_ask']),
    ('EMJ-7005', 'not_established', 'Their promised payment is due Fri 2 Oct, so send a reminder', ['representative', 'hardship', 'promise', 'contact_window', 'payment_ask']),
    ('SAV-6847', 'not_established', 'Ask for the payment, timed to their payday (Thu 1 Oct', ['representative', 'vulnerability', 'hardship', 'contact_window', 'payment_ask']),
]


@pytest.fixture(scope='module')
def conn():
    c = duckdb.connect(str(DB), read_only=True)
    yield c
    c.close()


@pytest.mark.parametrize('customer,status,headline,steps', DEMO)
def test_demo_customer_plan(conn, customer, status, headline, steps):
    plan = action_plan.for_customer(conn, customer, status)
    assert plan['next_action'].startswith(headline)
    assert [s['key'] for s in plan['steps']] == steps
    assert all(s['policy'] or s['key'] == 'placement' for s in plan['steps'])


def test_cap_and_holiday_showcase(conn):
    window = action_plan.for_customer(conn, 'SAV-6847', 'not_established')['contact_window']
    reasons = [s['reason'] for s in window['skipped']]
    assert reasons[:2] == ['already 3 attempts in the last 7 days'] * 2
    assert reasons[2].startswith('statutory holiday') and window['date'] == '2026-10-01'


def test_hardship_demo_programmes(conn):
    offers = action_plan.for_customer(conn, 'JEV-1240', 'recorded')['programmes']
    eligible = {o['program_id'] for o in offers if o['status'] == 'likely_eligible'}
    assert {'HP-LOAN-RED3', 'HP-LOAN-EXT'} <= eligible
    assert next(o for o in offers if o['program_id'] == 'HP-LOAN-EXT')['approver'] == 'hardship_specialist'


def test_calendar_matches_the_plan_window(conn):
    from app import customer360
    days = {d['date']: d for d in customer360.calendar(conn, 'SAV-6847')['days']}
    assert days['2026-09-28']['status'] == 'cap' and days['2026-09-30']['status'] == 'holiday'
    assert days['2026-10-01']['status'] == 'open' and days['2026-10-04']['from_local'] == '13:00'
    assert customer360.calendar(conn, 'HAC-4447')['days'][0]['status'] == 'blocked'


def test_timeline_is_newest_first_and_scoped(conn):
    from app import customer360
    events = customer360.timeline(conn, 'SAV-6847')['events']
    assert events and all(a['ts'] >= b['ts'] for a, b in zip(events, events[1:]))
    assert {e['kind'] for e in events} <= {'contact', 'promise', 'note', 'offer', 'case'}
