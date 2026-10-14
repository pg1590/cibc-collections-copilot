"""Ordered, policy-cited next steps for one customer. Rules only; no model output
changes a step. Every step names the source record and the policy it follows."""
import calendar
import csv
import json
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.settings import ROOT, SNAPSHOT

# Contact history ends 2026-09-28 06:56 UTC; plans start from the next business day.
AS_OF = datetime(2026, 9, 28, 7, 0, tzinfo=timezone.utc)
CAP_7D = 3
HORIZON_DAYS = 21
MIN_SLOT = timedelta(minutes=15)  # shorter windows are not usable by an agent
PTP_MAX_DAYS = 21
ATTEMPT_CHANNELS = ('call', 'sms', 'email', 'push')
POLICY = {
    'hold': 'POL-COLL-001 v3.0 §7.3', 'cease': 'POL-COLL-001 v3.0 §5.4', 'rep': 'POL-COLL-001 v3.0 §5.4',
    'hours': 'POL-COLL-001 v3.0 §5.1', 'cap': 'POL-COLL-001 v3.0 §5.2', 'consent': 'POL-COLL-001 v3.0 §5.3',
    'language': 'POL-COLL-001 v3.0 §5.5', 'hardship': 'POL-COLL-004 v4.2 §4.2', 'evidence': 'POL-COLL-004 v4.2 §4.3',
    'specialist': 'POL-COLL-004 v4.2 §4.4', 'vulnerable': 'POL-COLL-004 v4.2 §4.5', 'ptp': 'PRC-COLL-010 v2.1 §3.1',
    'ptp_confirm': 'PRC-COLL-010 v2.1 §3.2', 'ptp_grace': 'PRC-COLL-010 v2.1 §3.3', 'dispute': 'PRC-COLL-012 v1.4 §6.1',
    'complaint': 'POL-COLL-007 v2.0 §8.1', 'terms': 'HPT-2026 v2026.1',
}
LEVELS = {'none': 0, 'possible': 1, 'clear': 2}
# Latest start / earliest end that is 07:00-21:00 everywhere from St. John's to Vancouver.
FALLBACK_TZ = 'America/Vancouver'
FALLBACK_HOURS = ('07:00', '16:30')


def holidays():
    with (ROOT / 'config/statutory_holidays.csv').open(encoding='utf-8') as f:
        return {date.fromisoformat(r['date']): r['name'] for r in csv.DictReader(f)}


def _clock(value, default):
    try:
        return time.fromisoformat(value) if value else time.fromisoformat(default)
    except ValueError:
        return time.fromisoformat(default)


def _utc(ts):
    if ts is None:
        return None
    return ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts.astimezone(timezone.utc)


def _money(value):
    return f'CAD {float(value or 0):,.2f}'


def _day(d):
    return f"{d.strftime('%a')} {d.day} {d.strftime('%b')}"


def _add_months(d, n):
    m = d.month - 1 + n
    y, m = d.year + m // 12, m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def contact_window(attempts, tz_name, start, end, sunday_ok, holiday_names, as_of=AS_OF, cap=CAP_7D, horizon=HORIZON_DAYS):
    """Earliest instant contact is allowed: customer-local hours, Sundays, holidays,
    and the rolling 7-day attempt cap (POL-COLL-001 §5.1-5.2)."""
    known_tz = bool(tz_name)
    tz = ZoneInfo(tz_name or FALLBACK_TZ)
    if not known_tz:
        start, end = FALLBACK_HOURS
    start, end = _clock(start, '07:00'), _clock(end, '21:00')
    times = sorted(t for t in (_utc(a) for a in attempts) if t and t <= as_of)
    recent = [t for t in times if t > as_of - timedelta(days=7)]
    skipped = []
    first_day = as_of.astimezone(tz).date()
    for offset in range(horizon + 1):
        d = first_day + timedelta(days=offset)
        if d in holiday_names:
            skipped.append({'date': d.isoformat(), 'reason': f'statutory holiday ({holiday_names[d]})'})
            continue
        lo, hi = start, end
        if d.weekday() == 6:
            if not sunday_ok:
                skipped.append({'date': d.isoformat(), 'reason': 'Sunday contact not permitted for this customer'})
                continue
            lo, hi = max(lo, time(13)), min(hi, time(17))
        opens = datetime.combine(d, lo, tz).astimezone(timezone.utc)
        closes = datetime.combine(d, hi, tz).astimezone(timezone.utc)
        t = max(opens, as_of)
        window = [a for a in times if t - timedelta(days=7) < a <= t]
        if len(window) >= cap:
            t = max(t, window[len(window) - cap] + timedelta(days=7))
        if t + MIN_SLOT > closes:
            reason = 'already 3 attempts in the last 7 days' if len(window) >= cap else 'outside permitted hours'
            if not (skipped and skipped[-1]['date'] == d.isoformat()):
                skipped.append({'date': d.isoformat(), 'reason': reason})
            continue
        local = t.astimezone(tz)
        # Round up to the next 5 minutes so the agent sees a usable time.
        local = local + timedelta(minutes=(-local.minute) % 5, seconds=-local.second, microseconds=-local.microsecond)
        return {'available': True, 'date': d.isoformat(), 'day': _day(d), 'from_local': local.strftime('%H:%M'),
                'until_local': datetime.combine(d, hi).strftime('%H:%M'), 'time_zone': tz_name or 'unknown',
                'time_zone_known': known_tz, 'attempts_last_7d': len(recent), 'cap_7d': cap,
                'skipped': skipped, 'at_utc': t.isoformat()}
    return {'available': False, 'time_zone': tz_name or 'unknown', 'time_zone_known': known_tz,
            'attempts_last_7d': len(recent), 'cap_7d': cap, 'skipped': skipped[-5:]}


def next_payday(frequency, last_credit, as_of_date):
    """Estimate only: recorded pay frequency rolled forward from the last salary credit."""
    if not last_credit or frequency not in ('weekly', 'biweekly', 'semi_monthly', 'monthly'):
        return None
    if frequency == 'semi_monthly':  # 15th and last day of the month
        for month in (as_of_date.replace(day=1), _add_months(as_of_date.replace(day=1), 1)):
            for day in (15, calendar.monthrange(month.year, month.month)[1]):
                if month.replace(day=day) >= as_of_date:
                    return month.replace(day=day)
    d = last_credit
    for n in range(1, 60):
        if d >= as_of_date:
            return d
        d = _add_months(last_credit, n) if frequency == 'monthly' else last_credit + timedelta(days=(7 if frequency == 'weekly' else 14) * n)
    return None


def programmes(programs, ctx, hardship_level, as_of_date):
    """Check each effective programme version against the recorded rules. Results are
    suggestions for the agent and approver, never an eligibility decision."""
    case, cust = ctx['case'], ctx['customer']
    product, dpd = case.get('primary_product'), case.get('current_dpd')
    insolvent = bool(cust.get('bankruptcy_flag') or cust.get('consumer_proposal_flag') or case.get('insolvency_hold_flag'))
    counsellor = bool(cust.get('credit_counselling_agency_flag') or cust.get('third_party_relationship') == 'credit_counsellor')
    out = []
    for p in programs:
        if not (p['effective_from'] <= as_of_date <= p['effective_to']):
            continue
        products = json.loads(p['product_types']) if isinstance(p['product_types'], str) else p['product_types']
        if product not in products:
            continue
        fails, unknown, needs = [], [], []
        need = LEVELS.get(p['min_hardship_level'], 2)
        if need > hardship_level:
            fails.append('needs recorded hardship' if need == 2 else 'needs a hardship indication')
        if dpd is None:
            unknown.append('days past due missing')
        elif dpd > p['max_dpd']:
            fails.append(f"{dpd} days past due is over the {p['max_dpd']}-day limit")
        mob = ctx.get('months_on_book')
        if mob is None and p['min_months_on_book']:
            unknown.append('account open date missing')
        elif mob is not None and mob < p['min_months_on_book']:
            fails.append(f"{mob} months on book, needs {p['min_months_on_book']}")
        used = ctx['uses_12m'].get(p['program_id'], 0)
        if used >= p['max_uses_12m']:
            fails.append(f"already used {used} time(s) in 12 months")
        if p['excludes_insolvency'] and insolvent:
            fails.append('not available during bankruptcy or consumer proposal')
        if p['excludes_broken_plan_90d'] and ctx['broken_plan_90d']:
            fails.append('a hardship plan was broken in the last 90 days')
        if p['program_id'] == 'HP-DMP' and not counsellor:
            fails.append('needs a non-profit credit counsellor representing the customer')
        if p['program_id'] == 'HP-SETTLE' and (dpd or 0) < 121:
            fails.append('settlement is a late-stage option (121+ days past due)')
        if p['requires_income_evidence']:
            needs.append(f"income and expense evidence ({POLICY['evidence']})")
        status = 'not_eligible' if fails else 'check' if unknown else 'likely_eligible'
        out.append({'program_id': p['program_id'], 'version': p['version'], 'name': p['program_name'],
                    'description': p['description'], 'approver': p['approver_level'], 'status': status,
                    'reasons': fails + unknown, 'missing_inputs': needs,
                    'source': f"hardship_programs:{p['program_id']} v{p['version']}; {POLICY['terms']}"})
    order = {'likely_eligible': 0, 'check': 1, 'not_eligible': 2}
    return sorted(out, key=lambda r: (order[r['status']], r['approver'] != 'agent', r['program_id']))


def _step(steps, key, status, title, detail, policy=(), evidence=()):
    steps.append({'order': len(steps) + 1, 'key': key, 'status': status, 'title': title, 'detail': detail,
                  'policy': [POLICY[p] if p in POLICY else p for p in policy], 'evidence': list(evidence)})


def build(ctx, hardship_status, as_of=AS_OF, holiday_names=None):
    """Pure rule evaluation over a loaded context; see load() for the source fields."""
    holiday_names = holidays() if holiday_names is None else holiday_names
    cust, case, steps = ctx['customer'], ctx['case'], []
    as_of_date = as_of.date()
    case_ref = f"collections_cases:{case['case_id']}"
    cust_ref = f"customers:{cust.get('crm_customer_id')}"
    french = (cust.get('preferred_language') or '').lower().startswith('fr')
    level = 2 if hardship_status == 'recorded' else 1 if hardship_status == 'possible' else 0

    # 1. Restrictions stop every other contact step.
    holds = []
    if cust.get('bankruptcy_flag') or cust.get('consumer_proposal_flag') or case.get('insolvency_hold_flag'):
        filed = cust.get('insolvency_filed_date')
        holds.append(('insolvency', 'Bankruptcy or consumer proposal recorded' + (f' (filed {filed})' if filed else '') +
                      '. A stay of proceedings applies: all collection contact stops.', ['hold']))
    if cust.get('deceased_flag') or case.get('deceased_hold_flag'):
        holds.append(('deceased', 'Deceased-customer restriction recorded. A supervisor must verify it before any action.', ['hold']))
    if cust.get('cease_communication_flag') or case.get('cease_contact_flag'):
        holds.append(('cease', 'Written cease-communication request recorded. Calls, texts and emails stop; required letters and statements continue.', ['cease']))
    if holds:
        _step(steps, 'restriction', 'stop', "Don't contact this customer", ' '.join(h[1] for h in holds),
              sorted({p for h in holds for p in h[2]}), [case_ref, cust_ref])
        if any(h[0] == 'insolvency' for h in holds) and cust.get('licensed_insolvency_trustee_name'):
            _step(steps, 'representative', 'action', 'Route any communication through the Licensed Insolvency Trustee',
                  f"Trustee on record: {cust['licensed_insolvency_trustee_name'].rstrip('.')}. Debt details are never disclosed to other third parties.",
                  ['rep', 'hold'], [cust_ref])
        return _finish(steps, ctx, None, [], None)

    # 2. Representative: every later step is carried out with the representative.
    rep = None
    if cust.get('legal_representative_flag') or cust.get('third_party_relationship') == 'lawyer':
        rep = 'lawyer'
    elif cust.get('credit_counselling_agency_flag') or cust.get('third_party_relationship') == 'credit_counsellor':
        rep = 'non-profit credit counsellor'
    elif cust.get('licensed_insolvency_trustee_name') or cust.get('third_party_relationship') == 'trustee':
        rep = 'Licensed Insolvency Trustee'
    elif case.get('third_party_rep_flag'):
        rep = 'recorded third-party representative'
    if rep:
        _step(steps, 'representative', 'action', 'Only talk to their representative',
              f'A {rep} represents this customer. All contact goes through the representative; do not contact the customer directly.',
              ['rep'], [cust_ref if not case.get('third_party_rep_flag') else case_ref])
    else:
        _step(steps, 'representative', 'clear', 'No representative recorded', 'Contact the customer directly after identity verification.', ['rep'], [cust_ref])

    if case.get('case_status') in ('placed_agency', 'legal'):
        _step(steps, 'placement', 'caution',
              'Case is with an external collection agency: coordinate before any contact' if case['case_status'] == 'placed_agency'
              else 'Legal action is in progress: coordinate with the legal team before any contact',
              f"Source case status is '{case['case_status']}'. No policy section in the release covers this; the step follows the recorded status.",
              [], [case_ref])

    # 3. Disputes and complaints pause or shape the payment conversation.
    disputed = case.get('dispute_flag') and case.get('dispute_status') == 'open'
    if disputed:
        kind = (case.get('dispute_type') or 'amount').replace('_', ' ')
        _step(steps, 'dispute', 'caution', 'Pause payment requests for the disputed amount',
              f'An open {kind} dispute is recorded. Do not ask for the disputed amount until it is resolved; fraud claims go to the fraud team.',
              ['dispute'], [case_ref])
    if case.get('complaint_flag') and case.get('complaint_stage'):
        _step(steps, 'complaint', 'caution', 'Acknowledge the open complaint',
              f"Complaint at stage '{case['complaint_stage'].replace('_', ' ')}'. Escalate to a team lead and tell the customer the current stage.",
              ['complaint'], [case_ref])

    # 4. Vulnerability is a safeguard, never a risk factor or a priority input.
    if case.get('vulnerable_customer_flag') or cust.get('vulnerability_flag'):
        certified = ctx.get('agent_certified')
        detail = ('Use script SCR-VUL-EN/FR, allow extra time, never pressure for payment, offer hardship options first; contact may be paused up to 30 days.' +
                  ('' if certified else ' The assigned agent is not vulnerable-customer certified: reassign before contact.'))
        _step(steps, 'vulnerability', 'caution' if certified else 'action', 'Use the vulnerable-customer approach', detail, ['vulnerable'], [case_ref])

    # 5. Hardship: offer an eligible programme before any payment request.
    offers = []
    plan_active = case.get('hardship_plan_type') and (case.get('hardship_plan_end') is None or case['hardship_plan_end'] >= as_of_date)
    if plan_active:
        end = case.get('hardship_plan_end')
        _step(steps, 'hardship', 'clear', f"Hardship plan already in place ({case['hardship_plan_type'].replace('_', ' ')})",
              'Follow the agreed plan; do not ask for more than the plan payment.' + (f' Plan ends {end}; the hardship specialist contacts the customer 10 days before.' if end else ''),
              ['specialist'], [case_ref])
    elif level:
        offers = programmes(ctx['programs'], ctx, level, as_of_date)
        eligible = [o for o in offers if o['status'] != 'not_eligible']
        label = 'Hardship is recorded on this case' if level == 2 else 'Possible hardship (AI cue, needs the agent to confirm)'
        if eligible:
            names = '; '.join(f"{o['name']} ({o['program_id']}, approver: {o['approver'].replace('_', ' ')})" for o in eligible[:4])
            _step(steps, 'hardship', 'action', 'Offer one of these hardship programmes first',
                  f'{label}. Likely eligible: {names}. Final eligibility is confirmed by the approver.',
                  ['hardship'], [case_ref] + [o['source'] for o in eligible[:4]])
        else:
            _step(steps, 'hardship', 'action', 'Refer to a hardship specialist',
                  f'{label}, but no programme passes the recorded rules for this product. Confirm affordability; do not request a payment the customer cannot afford.',
                  ['hardship', 'specialist'], [case_ref])
    else:
        _step(steps, 'hardship', 'clear', 'No hardship recorded',
              'If the customer states a hardship, acknowledge it, record it and offer an eligible programme before asking for payment.', ['hardship'], [case_ref])

    # 6. Existing promise: remind, don't ask for more.
    ptp = ctx.get('promise')
    promise_pending = False
    window = contact_window(ctx['attempts'], cust.get('time_zone'), cust.get('permitted_call_start_local'),
                            cust.get('permitted_call_end_local'), cust.get('sunday_contact_permitted'), holiday_names, as_of)
    if ptp and ptp.get('ptp_due_date'):
        due = ptp['ptp_due_date']
        grace_end = due + timedelta(days=2 + (2 if due.weekday() >= 3 else 0))
        if due >= as_of_date:
            promise_pending = True
            slot = window.get('date')
            in_time = window['available'] and date.fromisoformat(slot) <= due
            _step(steps, 'promise', 'action' if in_time else 'wait',
                  f"Their promised payment is due {_day(due)}, so send a reminder; don't ask for more money yet",
                  f"Promise {ptp['ptp_id']}: {_money(ptp.get('ptp_amount'))} due {due}. " +
                  ((f'Send it today, {window["day"]}, before the payment is due.' if slot == due.isoformat() else f'Send it between {window["day"]} and {_day(due - timedelta(days=1))}.') + ' A payment reminder counts as 1 of the 3 attempts in 7 days.' if in_time
                   else 'No allowed contact slot before the due date; do not chase. Check for payment after the 2-business-day grace period.'),
                  ['ptp_confirm', 'cap'], [f"promises_to_pay:{ptp['ptp_id']}"])
        elif as_of_date <= grace_end:
            promise_pending = True
            _step(steps, 'promise', 'wait', 'Promise is in its grace period: check for payment first',
                  f"Promise {ptp['ptp_id']} for {_money(ptp.get('ptp_amount'))} was due {due}; it is kept if paid within 2 business days.",
                  ['ptp_grace'], [f"promises_to_pay:{ptp['ptp_id']}"])
        else:
            _step(steps, 'promise', 'caution', 'Promise past due and still open: confirm whether it was paid',
                  f"Promise {ptp['ptp_id']} for {_money(ptp.get('ptp_amount'))} was due {due} and has no recorded outcome. Check payment posting before treating it as broken.",
                  ['ptp_grace'], [f"promises_to_pay:{ptp['ptp_id']}"])

    # 7. When and how contact is allowed.
    channels = []
    if cust.get('consent_call') and not cust.get('internal_do_not_call_flag'):
        channels.append('call')
    if cust.get('consent_sms'):
        channels.append('text')
    if cust.get('consent_email'):
        channels.append('email')
    blocked = [] if channels else ['no call, text or email consent recorded: letters only']
    if cust.get('internal_do_not_call_flag'):
        blocked.append('internal do-not-call flag: no calls')
    if window['available']:
        tz_note = '' if window['time_zone_known'] else ' Time zone missing: hours narrowed to a window that is legal across Canada.'
        skip = ''.join(f" Not {_day(date.fromisoformat(s['date']))}: {s['reason']}." for s in window['skipped'][:3])
        title = f"You can contact them {window['day']} between {window['from_local']} and {window['until_local']} their time"
        detail = (f"{window['attempts_last_7d']} of {CAP_7D} attempts used in the last 7 days.{skip} Channels with consent: "
                  f"{', '.join(channels) or 'none'}." + (' ' + '; '.join(blocked) + '.' if blocked else '') +
                  (' Contact in French (Montréal site).' if french else '') + tz_note +
                  (' All contact goes to the representative.' if rep else ''))
        _step(steps, 'contact_window', 'action' if channels else 'caution', title, detail,
              ['hours', 'cap', 'consent'] + (['language'] if french else []), [cust_ref, 'contact_history: outbound attempts, last 7 days'])
    else:
        _step(steps, 'contact_window', 'wait', f'No allowed contact slot in the next {HORIZON_DAYS} days',
              f"{window['attempts_last_7d']} attempts in the last 7 days; check the restrictions above.", ['hours', 'cap'], [cust_ref])

    # 8. Only then: ask for payment, timed to payday.
    payday = next_payday(cust.get('pay_frequency'), ctx.get('last_salary_credit'), as_of_date)
    if promise_pending:
        _step(steps, 'payment_ask', 'wait', "Don't ask for a new payment yet", 'An open promise is pending; wait for its outcome.', ['ptp'], [case_ref])
    elif level and not plan_active:
        _step(steps, 'payment_ask', 'wait', 'Ask for payment only after offering a programme',
              'Agree an affordable amount once the hardship options are discussed. Never request a payment the customer says they cannot afford.', ['hardship'], [case_ref])
    else:
        latest = as_of_date + timedelta(days=PTP_MAX_DAYS)
        target = payday if payday and payday <= latest else None
        frequency = (cust.get('pay_frequency') or 'unknown').replace('_', '-')
        when = (f'Propose a promise date on or after their next payday, {_day(target)} (estimated from {frequency} pay and salary credits).'
                if target else f'Their next estimated payday, {_day(payday)}, is more than {PTP_MAX_DAYS} days away: propose a date by {_day(latest)}.'
                if payday else f'Pay frequency is {frequency} but no recent salary credit is recorded: ask for their next payday and set a date within {PTP_MAX_DAYS} days (by {_day(latest)}).')
        amount = _money(case.get('total_overdue'))
        detail = (f'Overdue on the case: {amount}.' + (' Exclude the disputed amount.' if disputed else '') +
                  f' {when} Read back the amount and date and offer a payment link.')
        _step(steps, 'payment_ask', 'action', 'Ask for the payment, timed to their payday', detail, ['ptp', 'ptp_confirm'],
              [case_ref] + ([f"salary_credit_history:{cust.get('crm_customer_id')}"] if target else []))
    return _finish(steps, ctx, window, offers, payday)


def _finish(steps, ctx, window, offers, payday):
    # The headline is the task; the contact window only says when it may happen.
    first = next((s for s in steps if s['status'] in ('stop', 'action', 'wait') and s['key'] != 'contact_window'), None) or \
        next((s for s in steps if s['status'] in ('stop', 'action', 'wait')), steps[0])
    headline = first['title']
    if window and window.get('available') and first['key'] in ('hardship', 'promise', 'payment_ask', 'vulnerability'):
        headline += f" ({window['day']}, {window['from_local']}-{window['until_local']} their time)"
    return {'as_of': AS_OF.isoformat(), 'snapshot_date': SNAPSHOT, 'case_id': ctx['case']['case_id'],
            'next_action': headline, 'steps': steps, 'contact_window': window, 'programmes': offers,
            'payday_estimate': payday.isoformat() if payday else None,
            'note': 'Rules from POL-COLL-001, POL-COLL-004, PRC-COLL-010/012 and POL-COLL-007 applied to source records. '
                    'Suggestions for the agent; a supervisor reviews the brief. Holidays: config/statutory_holidays.csv.'}


CUSTOMER_FIELDS = '''crm_customer_id,time_zone,fsa,province_code,preferred_language,consent_call,consent_sms,consent_email,
 internal_do_not_call_flag,cease_communication_flag,permitted_call_start_local,permitted_call_end_local,sunday_contact_permitted,
 pay_frequency,credit_counselling_agency_flag,legal_representative_flag,licensed_insolvency_trustee_name,third_party_relationship,
 bankruptcy_flag,consumer_proposal_flag,insolvency_filed_date,deceased_flag,vulnerability_flag'''
CASE_FIELDS = '''case_id,customer_id,primary_product,primary_account_id,current_dpd,total_overdue,case_status,hardship_flag,
 hardship_plan_type,hardship_plan_end,dispute_flag,dispute_status,dispute_type,complaint_flag,complaint_stage,cease_contact_flag,
 third_party_rep_flag,insolvency_hold_flag,deceased_hold_flag,vulnerable_customer_flag,assigned_agent_id,current_ptp_id,
 current_ptp_amount,current_ptp_due_date,case_open_date'''


def _rows(c, sql, params):
    r = c.execute(sql, params)
    keys = [d[0] for d in r.description]
    return [dict(zip(keys, row)) for row in r.fetchall()]


def load(c, customer_id, as_of=AS_OF):
    """Read the source records one plan needs; returns None without an open case."""
    cust = _rows(c, f'SELECT {CUSTOMER_FIELDS} FROM curated.customers WHERE crm_customer_id=(SELECT crm_customer_id FROM gold.customers WHERE customer_id=?) ORDER BY extract_ts DESC NULLS LAST LIMIT 1', [customer_id])
    cases = _rows(c, f'SELECT {CASE_FIELDS} FROM gold.cases WHERE customer_id=? AND outcome IS NULL ORDER BY current_dpd DESC NULLS LAST,total_overdue DESC NULLS LAST,case_id', [customer_id])
    if not cust or not cases:
        return None
    cust, case = cust[0], cases[0]
    if not cust.get('time_zone'):
        tz = c.execute('SELECT any_value(time_zone) FROM curated.geo_reference WHERE fsa=? OR (? IS NULL AND province_code=?)',
                       [cust.get('fsa'), cust.get('fsa'), cust.get('province_code')]).fetchone()
        cust['time_zone'] = tz[0] if tz else None
    attempts = [r[0] for r in c.execute(
        f"""SELECT contact_ts_utc FROM curated.contact_history WHERE case_id=? AND direction='outbound'
        AND coalesce(channel_v2,channel) IN {ATTEMPT_CHANNELS} AND contact_ts_utc>? AND contact_ts_utc<=?""",
        [case['case_id'], (as_of - timedelta(days=8)).replace(tzinfo=None), as_of.replace(tzinfo=None)]).fetchall()]
    promise = _rows(c, "SELECT ptp_id,ptp_amount,ptp_due_date,ptp_status FROM curated.promises_to_pay WHERE case_id=? AND ptp_status='open' ORDER BY ptp_due_date DESC LIMIT 1", [case['case_id']])
    if not promise and case.get('current_ptp_id') and case.get('current_ptp_due_date'):
        promise = [{'ptp_id': case['current_ptp_id'], 'ptp_amount': case['current_ptp_amount'], 'ptp_due_date': case['current_ptp_due_date']}]
    case_ids = [r[0] for r in c.execute('SELECT case_id FROM gold.cases WHERE customer_id=?', [customer_id]).fetchall()]
    marks = ','.join('?' for _ in case_ids)
    since = (as_of - timedelta(days=365)).replace(tzinfo=None)
    uses = dict(c.execute(f"SELECT program_id,count(*) FROM curated.offers WHERE case_id IN ({marks}) AND customer_response='accepted' AND offer_ts>? GROUP BY 1",
                          [*case_ids, since]).fetchall())
    broken = c.execute(f"SELECT count(*) FROM curated.offers WHERE case_id IN ({marks}) AND plan_status='broken' AND coalesce(response_ts,offer_ts)>?",
                       [*case_ids, (as_of - timedelta(days=90)).replace(tzinfo=None)]).fetchone()[0]
    opened = c.execute('''SELECT coalesce((SELECT open_date FROM curated.card_accounts WHERE card_account_id=?),
        (SELECT origination_date FROM curated.loan_accounts WHERE loan_id=? LIMIT 1),
        (SELECT open_date FROM curated.deposit_accounts WHERE deposit_account_id=?))''', [case['primary_account_id']] * 3).fetchone()[0]
    months = None
    if opened:
        months = (as_of.date().year - opened.year) * 12 + as_of.date().month - opened.month - (as_of.date().day < opened.day)
    salary = c.execute('SELECT max(last_credit_date) FROM curated.salary_credit_history WHERE crm_customer_id=? AND employer_flag=\'Y\'',
                       [cust['crm_customer_id']]).fetchone()[0]
    certified = c.execute('SELECT vulnerable_customer_certified FROM curated.agents WHERE agent_id=?', [case.get('assigned_agent_id')]).fetchone()
    programs = _rows(c, 'SELECT * FROM curated.hardship_programs', [])
    return {'customer': cust, 'case': case, 'other_open_cases': [x['case_id'] for x in cases[1:]], 'attempts': attempts,
            'promise': promise[0] if promise else None, 'uses_12m': uses, 'broken_plan_90d': bool(broken),
            'months_on_book': months, 'last_salary_credit': salary, 'agent_certified': bool(certified and certified[0]),
            'programs': programs}


def for_customer(c, customer_id, hardship_status):
    ctx = load(c, customer_id)
    if ctx is None:
        return None
    plan = build(ctx, hardship_status)
    plan['other_open_cases'] = ctx['other_open_cases']
    return plan
