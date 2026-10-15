"""Live Call Mode rules: gating, promise and callback checks, pricing, wrap-up and note
proposals (model quotes must be verbatim)."""
from datetime import date, datetime

import pytest

from app import action_plan as ap
from app import call_session as cs
from tests.test_action_plan import HOLIDAYS, PROGRAMS, ctx as plan_ctx

LOAN_PROGRAMS = [
    {'program_id': 'HP-LOAN-RED3', 'version': '2026.1', 'program_name': '3-month reduced payment', 'product_types': '["personal_loan"]',
     'description': 'Pay 50% of the regular payment for 3 months', 'min_hardship_level': 'possible', 'max_dpd': 90, 'min_months_on_book': 6,
     'max_uses_12m': 1, 'excludes_insolvency': True, 'excludes_broken_plan_90d': True, 'requires_income_evidence': False, 'approver_level': 'agent',
     'effective_from': date(2026, 3, 1), 'effective_to': date(9999, 12, 31), 'payment_reduction_pct': 0.5, 'rate_override': None,
     'duration_months': 3, 'term_extension_max_months': None},
    {'program_id': 'HP-LOAN-EXT', 'version': '2026.1', 'program_name': 'Term extension', 'product_types': '["personal_loan"]',
     'description': 'Extend the term by up to 12 months', 'min_hardship_level': 'clear', 'max_dpd': 120, 'min_months_on_book': 12,
     'max_uses_12m': 1, 'excludes_insolvency': True, 'excludes_broken_plan_90d': True, 'requires_income_evidence': True,
     'approver_level': 'hardship_specialist', 'effective_from': date(2026, 3, 1), 'effective_to': date(9999, 12, 31),
     'payment_reduction_pct': 0.25, 'rate_override': None, 'duration_months': 12, 'term_extension_max_months': 12},
]


def ctx(customer=None, case=None, **extra):
    value = plan_ctx(customer, case, **extra)
    value['customer'].setdefault('name', 'Test Customer')
    value['case'].setdefault('customer_id', 'C-1')
    value.setdefault('extras', {'account': {'product': value['case']['primary_product'], 'balance': 1200.0, 'regular_payment': 60.0,
                                            'apr': 0.2099, 'remaining_term_months': None, 'source': 'card_accounts:C-9'},
                                'declared_annual_income': 48000.0, 'housing': 1500.0, 'income_verified': True, 'obligations': 300.0})
    return value


def talking(**more):
    return {'reached': 'customer', 'identity_verified': True, 'recording_notice': True} | more


@pytest.fixture(autouse=True)
def fixed_holidays(monkeypatch):
    monkeypatch.setattr(ap, 'holidays', lambda start=None, days=0: HOLIDAYS)


def keys(result, level=None):
    return {c['key'] for c in result['checks'] if level is None or c['status'] == level}


def test_unknown_values_are_normalised_not_trusted():
    o = cs.normalise({'reached': 'robot', 'hardship': {'stated': 1, 'reason': 'lottery'}, 'dispute': {'type': 'x'}, 'evil': True})
    assert o['reached'] is None and o['hardship'] == {'stated': 1, 'reason': 'other'} and 'evil' not in o
    assert o['dispute']['type'] == 'other' and o['complaint'] is False


def test_restriction_blocks_the_call():
    r = cs.session(ctx(case={'insolvency_hold_flag': True}), 'not_established', talking())
    assert r['stage'] == 'blocked' and not r['can_discuss_debt'] and 'blocked' in keys(r, 'block')
    assert r['wrap_up']['ready_to_submit'] is False and r['script'] == []
    assert r['wrap_up']['note'].startswith('No call made') and r['wrap_up']['outcome_codes'] == ['NO_CONTACT_RESTRICTION']


def test_debt_is_locked_until_notice_and_identity():
    r = cs.session(ctx(), 'not_established', {'reached': 'customer', 'recording_notice': True, 'promise': {'amount': 50, 'date': '2026-10-02'}})
    assert r['stage'] == 'verification' and not r['can_discuss_debt']
    assert {'verification', 'promise'} <= keys(r, 'block')
    third = cs.session(ctx(), 'not_established', {'reached': 'third_party'})
    assert 'third_party' in keys(third, 'block') and third['wrap_up']['outcome_codes'][0] == 'THIRD_PARTY'


def test_promise_rules():
    def promise(amount, day, **more):
        return cs.session(ctx(), 'not_established', talking(promise={'amount': amount, 'date': day}, **more))
    assert 'promise' in keys(promise(50, '2026-11-30'), 'block')  # beyond 21 days
    assert 'promise' in keys(promise(50, '2026-09-01'), 'block')  # past
    assert 'promise' in keys(promise(0, '2026-10-02'), 'block')
    early = promise(50, '2026-09-29')  # before semi-monthly payday Wed 30 Sep
    assert 'promise_payday' in keys(early, 'warn')
    ok = promise(50, '2026-10-02')
    assert ok['wrap_up']['ready_to_submit'] and 'PTP' in ok['wrap_up']['outcome_codes']
    assert any(s['key'] == 'payment_ask' and s['title'].startswith('Promise taken') for s in ok['plan']['steps'])
    assert ok['wrap_up']['follow_ups'][0]['type'] in ('reminder', 'check_payment')
    assert 'promise_afford' in keys(promise(50, '2026-10-02', cannot_afford=True), 'warn')
    assert 'promise_dispute' in keys(promise(50, '2026-10-02', dispute={'raised': True, 'type': 'fee'}), 'warn')


def test_stated_hardship_unlocks_programmes_and_offer_first():
    r = cs.session(ctx(), 'not_established', talking(hardship={'stated': True, 'reason': 'job_loss'}))
    assert {o['program_id'] for o in r['calculator']['options']} >= {'HP-CARD-MIN', 'HP-CARD-FPP'}
    assert 'offer_first' in keys(r, 'warn') and 'HARDSHIP_STATED' in r['wrap_up']['outcome_codes']
    chosen = cs.session(ctx(), 'not_established', talking(hardship={'stated': True, 'reason': 'job_loss'}, programme='HP-CARD-FPP'))
    assert 'programme' in keys(chosen, 'warn')  # hardship specialist approves
    assert any(f['type'] == 'approval' for f in chosen['wrap_up']['follow_ups'])
    assert 'Submit Fixed payment plan for hardship specialist approval' in chosen['plan']['next_action']
    assert 'programme' in keys(cs.session(ctx(), 'not_established', talking(programme='HP-NOPE')), 'block')


def test_calculator_prices_from_programme_terms():
    loan = {'product': 'personal_loan', 'balance': 10000.0, 'regular_payment': 400.0, 'apr': 0.1, 'remaining_term_months': 30}
    red3, ext = cs.calculate(LOAN_PROGRAMS, loan)
    assert (red3['payment_during'], red3['deferred_amount'], red3['monthly_saving']) == (200.0, 600.0, 200.0)
    assert ext['months'] == 42 and ext['payment_during'] < 400 and ext['payment_during'] == pytest.approx(10000 * (0.1 / 12) / (1 - (1 + 0.1 / 12) ** -42), abs=0.01)
    card = {'product': 'card', 'balance': 1200.0, 'regular_payment': None, 'apr': 0.2099}
    rows = cs.calculate([{**p, 'name': p['program_name'], 'payment_reduction_pct': 0.3 if p['program_id'] == 'HP-CARD-FPP' else 0.5,
                          'rate_override': 0 if p['program_id'] == 'HP-CARD-FPP' else None, 'duration_months': 12 if p['program_id'] == 'HP-CARD-FPP' else 3,
                          'term_extension_max_months': None} for p in PROGRAMS if p['version'] == '2026.1'], card)
    by = dict(zip([p['program_id'] for p in PROGRAMS if p['version'] == '2026.1'], rows))
    assert by['HP-CARD-MIN']['payment_now'] == 36.0  # 3% of balance when the source has no minimum
    assert by['HP-CARD-FPP']['payment_during'] == 100.0 and by['HP-CARD-FPP']['interest_saving'] > 0
    settle = cs.calculate([{'program_id': 'HP-SETTLE', 'name': 'Settlement offer', 'description': 'One-time settlement', 'payment_reduction_pct': 0.4,
                            'duration_months': 1}], {'product': 'card', 'balance': 1000.0, 'regular_payment': 30.0})[0]
    assert settle['one_time_amount'] == 400.0


def test_affordability_prefers_what_the_customer_says():
    r = cs.session(ctx(), 'not_established', talking(promise={'amount': 1500, 'date': '2026-10-02'}))
    assert r['affordability']['disposable'] == 4000 - 1500 - 300 and r['affordability']['verified']
    stated = cs.session(ctx(), 'not_established', talking(income={'monthly_income': 2000, 'monthly_expenses': 1800}, promise={'amount': 150, 'date': '2026-10-02'}))
    assert stated['affordability']['disposable'] == 200 and not stated['affordability']['verified']
    assert 'promise_share' in keys(stated, 'warn')


def test_callback_must_be_in_an_allowed_slot():
    def cb(day, at):
        return cs.session(ctx(), 'not_established', talking(callback={'date': day, 'time': at}))
    assert 'callback' in keys(cb('2026-09-30', '10:00'), 'block')  # statutory holiday
    assert 'callback' in keys(cb('2026-10-01', '22:30'), 'block')  # after 21:00
    assert 'callback' in keys(cb('2026-10-01', '10:00'), 'ok')
    assert 'CALLBACK' in cb('2026-10-01', '10:00')['wrap_up']['outcome_codes']


def test_cease_dispute_complaint_representative_shape_the_wrap_up():
    r = cs.session(ctx(), 'not_established', talking(cease_request=True, complaint=True, dispute={'raised': True, 'type': 'fraud'},
                                                    representative={'stated': True, 'kind': 'lawyer'}))
    codes = r['wrap_up']['outcome_codes']
    assert {'CEASE_REQUEST', 'COMPLAINT', 'FRAUD', 'REPRESENTATIVE'} <= set(codes)
    assert r['plan']['steps'][0]['key'] == 'restriction'  # cease request now stops contact
    assert any(f['type'] == 'escalation' for f in r['wrap_up']['follow_ups'])


def test_no_answer_schedules_the_next_allowed_attempt():
    r = cs.session(ctx(), 'not_established', {'reached': 'no_answer'})
    assert r['stage'] == 'wrap_up' and r['wrap_up']['ready_to_submit']
    assert r['wrap_up']['follow_ups'][0]['type'] == 'retry'


def test_vulnerable_script_and_uncertified_agent():
    r = cs.session(ctx(agent_certified=False), 'not_established', talking(vulnerable_disclosed=True))
    assert 'vulnerable' in keys(r, 'block') and any(s['key'] == 'vulnerable' for s in r['script'])
    assert 'details not recorded' in r['wrap_up']['note']


def test_rules_extraction_from_free_text():
    note = 'Customer said her hours were cut in September. She can pay $120 on Oct 16 when she gets paid. Please stop calling me at work.'
    found = {p['field']: p for p in cs.extract(note, date(2026, 10, 1))['proposals']}
    assert found['hardship.reason']['value'] == 'reduced_income'
    assert found['promise']['value'] == {'amount': 120.0, 'date': '2026-10-16'}
    assert found['cease_request']['quote'] == 'Please stop calling me at work.'
    assert cs.extract('Nothing relevant here.', date(2026, 10, 1))['proposals'] == []


def test_model_proposals_need_verbatim_quotes_and_matching_amounts():
    note = 'She lost her job last week. She will pay 200 dollars on 2026-10-09.'
    raw = [{'field': 'hardship', 'hardship_reason': 'job_loss', 'quote': 'She lost her job last week.'},
           {'field': 'hardship', 'hardship_reason': 'illness', 'quote': 'She is in hospital.'},  # not in the note
           {'field': 'promise', 'amount': 900, 'date': '2026-10-09', 'quote': 'She will pay 200 dollars on 2026-10-09.'},  # wrong amount
           {'field': 'promise', 'amount': 200, 'date': '2026-10-09', 'quote': 'She will pay 200 dollars on 2026-10-09.'},
           {'field': 'complaint', 'quote': 'x'}]
    found = cs.verify_model_proposals(raw, note, date(2026, 10, 1))
    assert [(p['field'], p['value']) for p in found] == [('hardship.stated', True), ('hardship.reason', 'job_loss'),
                                                         ('promise', {'amount': 200.0, 'date': '2026-10-09'})]


class FailingClient:
    configured = True

    def extract_outcomes(self, *args):
        raise RuntimeError('provider down')


def test_provider_failure_falls_back_to_rules():
    result = cs.extract('I lost my job.', date(2026, 10, 1), FailingClient())
    assert result['provider'] == 'rules' and result['proposals'][0]['field'] == 'hardship.stated'


def test_agreed_programme_is_not_read_as_hardship_and_each_field_is_proposed_once():
    note = 'Agreed to the 3-month reduced payment for October. He lost his job last month; money is tight since the layoff.'
    found = cs.extract(note, date(2026, 9, 28))['proposals']
    assert [(p['field'], p['value'], p['quote']) for p in found] == [
        ('hardship.stated', True, 'He lost his job last month;'), ('hardship.reason', 'job_loss', 'He lost his job last month;')]
