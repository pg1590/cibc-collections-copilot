"""Ordered next-step rules: restrictions first, then representative, hardship,
promise, the legal contact window and only then a payment request."""
from datetime import date, datetime, timedelta, timezone

from app import action_plan as ap

HOLIDAYS = {date(2026, 9, 30): 'National Day for Truth and Reconciliation'}
PROGRAMS = [
    {'program_id': 'HP-CARD-MIN', 'version': '2026.1', 'program_name': 'Reduced minimum payment', 'product_types': '["card"]',
     'description': 'Minimum payment reduced by 50% for 3 months', 'min_hardship_level': 'possible', 'max_dpd': 90,
     'min_months_on_book': 6, 'max_uses_12m': 1, 'excludes_insolvency': True, 'excludes_broken_plan_90d': True,
     'requires_income_evidence': False, 'approver_level': 'agent', 'effective_from': date(2026, 3, 1), 'effective_to': date(9999, 12, 31)},
    {'program_id': 'HP-CARD-MIN', 'version': '2025.1', 'program_name': 'Reduced minimum payment', 'product_types': '["card"]',
     'description': 'old version', 'min_hardship_level': 'possible', 'max_dpd': 90, 'min_months_on_book': 6, 'max_uses_12m': 1,
     'excludes_insolvency': True, 'excludes_broken_plan_90d': True, 'requires_income_evidence': False, 'approver_level': 'agent',
     'effective_from': date(2025, 3, 1), 'effective_to': date(2026, 2, 28)},
    {'program_id': 'HP-CARD-FPP', 'version': '2026.1', 'program_name': 'Fixed payment plan', 'product_types': '["card"]',
     'description': 'Fixed monthly payment', 'min_hardship_level': 'clear', 'max_dpd': 150, 'min_months_on_book': 12,
     'max_uses_12m': 1, 'excludes_insolvency': True, 'excludes_broken_plan_90d': True, 'requires_income_evidence': True,
     'approver_level': 'hardship_specialist', 'effective_from': date(2026, 3, 1), 'effective_to': date(9999, 12, 31)},
    {'program_id': 'HP-DMP', 'version': '2026.1', 'program_name': 'Debt management plan', 'product_types': '["card"]',
     'description': 'Credit counsellor plan', 'min_hardship_level': 'clear', 'max_dpd': 180, 'min_months_on_book': 0,
     'max_uses_12m': 1, 'excludes_insolvency': False, 'excludes_broken_plan_90d': False, 'requires_income_evidence': True,
     'approver_level': 'hardship_specialist', 'effective_from': date(2026, 3, 1), 'effective_to': date(9999, 12, 31)},
]


def ctx(customer=None, case=None, **extra):
    base_customer = {'crm_customer_id': 'CRM-1', 'time_zone': 'America/Toronto', 'preferred_language': 'EN', 'consent_call': True,
                     'consent_sms': True, 'consent_email': False, 'permitted_call_start_local': '07:00', 'permitted_call_end_local': '21:00',
                     'sunday_contact_permitted': True, 'pay_frequency': 'semi_monthly'}
    base_case = {'case_id': 'CS-1', 'primary_product': 'card', 'current_dpd': 40, 'total_overdue': 250.0, 'case_status': 'open'}
    value = {'customer': base_customer | (customer or {}), 'case': base_case | (case or {}), 'other_open_cases': [], 'attempts': [],
             'promise': None, 'uses_12m': {}, 'broken_plan_90d': False, 'months_on_book': 24, 'last_salary_credit': date(2026, 8, 31),
             'agent_certified': True, 'programs': PROGRAMS}
    value.update(extra)
    return value


def plan(context, status='not_established'):
    return ap.build(context, status, holiday_names=HOLIDAYS)


def keys(result):
    return [step['key'] for step in result['steps']]


def test_insolvency_stops_every_contact_step():
    result = plan(ctx({'consumer_proposal_flag': True, 'licensed_insolvency_trustee_name': 'Trustee Inc.'}), 'recorded')
    assert keys(result) == ['restriction', 'representative']
    assert result['next_action'] == "Don't contact this customer"
    assert result['steps'][0]['status'] == 'stop' and 'POL-COLL-001 v3.0 §7.3' in result['steps'][0]['policy']
    assert result['programmes'] == [] and result['contact_window'] is None


def test_cease_communication_is_a_stop():
    result = plan(ctx(case={'cease_contact_flag': True}))
    assert keys(result) == ['restriction'] and 'letters and statements continue' in result['steps'][0]['detail']


def test_representative_routes_all_contact():
    result = plan(ctx({'credit_counselling_agency_flag': True, 'third_party_relationship': 'credit_counsellor'}))
    step = result['steps'][0]
    assert step['key'] == 'representative' and step['status'] == 'action'
    assert step['title'] == 'Only talk to their representative' and 'credit counsellor' in step['detail']
    assert 'representative' in next(s for s in result['steps'] if s['key'] == 'contact_window')['detail']


def test_order_matches_the_agent_checklist():
    result = plan(ctx(case={'dispute_flag': True, 'dispute_status': 'open', 'vulnerable_customer_flag': True}), 'recorded')
    assert keys(result) == ['representative', 'dispute', 'vulnerability', 'hardship', 'contact_window', 'payment_ask']


def test_recorded_hardship_offers_effective_eligible_programmes_before_payment():
    result = plan(ctx(), 'recorded')
    hardship = next(s for s in result['steps'] if s['key'] == 'hardship')
    assert hardship['title'] == 'Offer one of these hardship programmes first'
    statuses = {(p['program_id'], p['version']): p['status'] for p in result['programmes']}
    assert ('HP-CARD-MIN', '2025.1') not in statuses  # superseded version is not offered
    assert statuses[('HP-CARD-MIN', '2026.1')] == 'likely_eligible'
    fpp = next(p for p in result['programmes'] if p['program_id'] == 'HP-CARD-FPP')
    assert fpp['status'] == 'likely_eligible' and fpp['approver'] == 'hardship_specialist' and fpp['missing_inputs']
    dmp = next(p for p in result['programmes'] if p['program_id'] == 'HP-DMP')
    assert dmp['status'] == 'not_eligible' and 'credit counsellor' in dmp['reasons'][0]
    ask = result['steps'][-1]
    assert ask['key'] == 'payment_ask' and ask['status'] == 'wait'


def test_possible_hardship_cannot_unlock_programmes_needing_recorded_hardship():
    result = plan(ctx(), 'possible')
    fpp = next(p for p in result['programmes'] if p['program_id'] == 'HP-CARD-FPP')
    assert fpp['status'] == 'not_eligible' and 'needs recorded hardship' in fpp['reasons']
    assert 'AI cue' in next(s for s in result['steps'] if s['key'] == 'hardship')['detail']


def test_programme_rule_failures_are_explained():
    result = plan(ctx(case={'current_dpd': 120}, uses_12m={'HP-CARD-MIN': 1}, broken_plan_90d=True, months_on_book=3), 'recorded')
    card_min = next(p for p in result['programmes'] if p['program_id'] == 'HP-CARD-MIN')
    assert card_min['status'] == 'not_eligible'
    text = ' '.join(card_min['reasons'])
    assert 'over the 90-day limit' in text and 'already used' in text and 'broken' in text and 'months on book' in text


def test_active_plan_means_follow_the_plan():
    result = plan(ctx(case={'hardship_flag': True, 'hardship_plan_type': 'reduced_payment', 'hardship_plan_end': date(2026, 12, 1)}), 'recorded')
    hardship = next(s for s in result['steps'] if s['key'] == 'hardship')
    assert hardship['status'] == 'clear' and 'do not ask for more than the plan payment' in hardship['detail']
    assert result['programmes'] == []


def test_open_promise_means_reminder_not_new_payment_ask():
    promise = {'ptp_id': 'PTP-1', 'ptp_amount': 120.0, 'ptp_due_date': date(2026, 10, 2)}
    result = plan(ctx(promise=promise))
    step = next(s for s in result['steps'] if s['key'] == 'promise')
    assert step['title'].startswith('Their promised payment is due Fri 2 Oct, so send a reminder')
    assert 'counts as 1 of the 3 attempts' in step['detail'] and 'POL-COLL-001 v3.0 §5.2' in step['policy']
    assert result['steps'][-1]['title'] == "Don't ask for a new payment yet"


def test_promise_in_grace_period_waits_for_payment():
    result = plan(ctx(promise={'ptp_id': 'PTP-2', 'ptp_amount': 50.0, 'ptp_due_date': date(2026, 9, 26)}))
    assert next(s for s in result['steps'] if s['key'] == 'promise')['status'] == 'wait'


def test_contact_cap_holiday_and_sunday_push_the_window():
    # Three attempts inside the last 7 days: the oldest drops out on Fri 2 Oct 14:00 UTC.
    attempts = [datetime(2026, 9, 25, 14, 0), datetime(2026, 9, 26, 14, 0), datetime(2026, 9, 27, 14, 0)]
    window = ap.contact_window(attempts, 'America/Toronto', '07:00', '21:00', False, HOLIDAYS)
    assert window['available'] and window['attempts_last_7d'] == 3
    assert window['date'] == '2026-10-02' and window['from_local'] == '10:00'
    reasons = {s['date']: s['reason'] for s in window['skipped']}
    assert 'statutory holiday' in reasons['2026-09-30']
    assert reasons['2026-09-28'] == 'already 3 attempts in the last 7 days'


def test_sunday_permitted_uses_afternoon_window():
    as_of = datetime(2026, 10, 4, 7, 0, tzinfo=timezone.utc)
    window = ap.contact_window([], 'America/Toronto', '07:00', '21:00', True, {}, as_of=as_of)
    assert window['date'] == '2026-10-04' and (window['from_local'], window['until_local']) == ('13:00', '17:00')
    blocked = ap.contact_window([], 'America/Toronto', '07:00', '21:00', False, {}, as_of=as_of)
    assert blocked['date'] == '2026-10-05'


def test_customer_local_time_zone_is_used():
    late = datetime(2026, 9, 29, 2, 30, tzinfo=timezone.utc)  # 23:00 in St. John's, 19:30 in Vancouver
    st_johns = ap.contact_window([], 'America/St_Johns', '07:00', '21:00', True, {}, as_of=late)
    vancouver = ap.contact_window([], 'America/Vancouver', '07:00', '21:00', True, {}, as_of=late)
    assert st_johns['date'] == '2026-09-29' and st_johns['from_local'] == '07:00'
    assert vancouver['date'] == '2026-09-28' and vancouver['from_local'] == '19:30'


def test_missing_time_zone_uses_a_window_legal_everywhere():
    window = ap.contact_window([], None, '07:00', '21:00', True, {})
    assert window['time_zone_known'] is False and window['until_local'] == '16:30'


def test_consent_and_do_not_call_shape_channels():
    result = plan(ctx({'consent_call': True, 'internal_do_not_call_flag': True, 'consent_sms': False, 'consent_email': True}))
    detail = next(s for s in result['steps'] if s['key'] == 'contact_window')['detail']
    assert 'Channels with consent: email' in detail and 'internal do-not-call' in detail
    none = plan(ctx({'consent_call': False, 'consent_sms': False, 'consent_email': False}))
    assert next(s for s in none['steps'] if s['key'] == 'contact_window')['status'] == 'caution'


def test_uncertified_agent_must_reassign_vulnerable_customer():
    result = plan(ctx(case={'vulnerable_customer_flag': True}, agent_certified=False))
    step = next(s for s in result['steps'] if s['key'] == 'vulnerability')
    assert step['status'] == 'action' and 'reassign' in step['detail'] and 'POL-COLL-004 v4.2 §4.5' in step['policy']


def test_payment_ask_is_timed_to_payday_and_excludes_disputes():
    result = plan(ctx(case={'dispute_flag': True, 'dispute_status': 'open'}))
    ask = result['steps'][-1]
    assert ask['status'] == 'action' and ask['title'] == 'Ask for the payment, timed to their payday'
    assert 'Wed 30 Sep' in ask['detail'] and 'Exclude the disputed amount' in ask['detail']
    assert result['payday_estimate'] == '2026-09-30'


def test_next_payday_estimates():
    as_of = date(2026, 9, 28)
    assert ap.next_payday('semi_monthly', date(2026, 8, 31), as_of) == date(2026, 9, 30)
    assert ap.next_payday('semi_monthly', date(2026, 8, 31), date(2026, 10, 1)) == date(2026, 10, 15)
    assert ap.next_payday('biweekly', date(2026, 8, 21), as_of) == date(2026, 10, 2)
    assert ap.next_payday('weekly', date(2026, 8, 28), as_of) == date(2026, 10, 2)
    assert ap.next_payday('monthly', date(2026, 8, 31), as_of) == date(2026, 9, 30)
    assert ap.next_payday('irregular', date(2026, 8, 31), as_of) is None
    assert ap.next_payday('biweekly', None, as_of) is None


def test_payday_beyond_promise_limit_is_not_used():
    result = plan(ctx({'pay_frequency': 'monthly'}, last_salary_credit=date(2026, 8, 25)))
    assert 'Sun 25 Oct, is more than 21 days away: propose a date by Mon 19 Oct' in result['steps'][-1]['detail']
    missing = plan(ctx({'pay_frequency': 'biweekly'}, last_salary_credit=None))
    assert 'no recent salary credit is recorded' in missing['steps'][-1]['detail']


def test_holiday_calendar_contains_policy_example():
    assert ap.holidays()[date(2026, 9, 30)].startswith('National Day for Truth')


def test_promise_due_today_says_send_today():
    result = plan(ctx(promise={'ptp_id': 'PTP-3', 'ptp_amount': 60.0, 'ptp_due_date': date(2026, 9, 28)}))
    assert 'Send it today, Mon 28 Sep' in next(s for s in result['steps'] if s['key'] == 'promise')['detail']


def test_headline_is_the_task_with_its_time_window():
    result = plan(ctx())
    assert result['next_action'] == 'Ask for the payment, timed to their payday (Mon 28 Sep, 07:00-21:00 their time)'
    held = plan(ctx(case={'insolvency_hold_flag': True}))
    assert held['next_action'] == "Don't contact this customer"


def test_window_shorter_than_fifteen_minutes_moves_to_next_day():
    # Third attempt frees up at 20:55 Toronto time on Mon 28 Sep: too late to use.
    attempts = [datetime(2026, 9, 22, 0, 55), datetime(2026, 9, 25, 12, 0), datetime(2026, 9, 26, 12, 0)]
    window = ap.contact_window(attempts, 'America/Toronto', '07:00', '21:00', True, {})
    assert window['date'] == '2026-09-29' and window['from_local'] == '07:00'
