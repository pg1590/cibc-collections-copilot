"""Live Call Mode: recompute the compliant plan from what the agent records during a call.

Everything here is rules over source records plus what the agent confirmed. Optional Gemini
only proposes outcomes from free-text notes, each with a verbatim quote that is verified
against the note before it is shown; the agent accepts or dismisses every proposal.
"""
import copy
import re
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app import action_plan as ap
from app.features import normalize_text, text_features

REASONS = ('job_loss', 'reduced_income', 'illness', 'separation', 'disaster', 'expense_increase', 'other')
DISPUTES = ('fee', 'transaction', 'payment_not_applied', 'fraud', 'other')
REPRESENTATIVES = {'lawyer': 'lawyer', 'credit_counsellor': 'credit_counsellor', 'trustee': 'trustee', 'other': None}
EMPTY = {'reached': None, 'identity_verified': False, 'recording_notice': False,
         'hardship': {'stated': False, 'reason': None}, 'cannot_afford': False,
         'dispute': {'raised': False, 'type': None}, 'complaint': False, 'cease_request': False,
         'representative': {'stated': False, 'kind': None}, 'vulnerable_disclosed': False,
         'programme': None, 'promise': None, 'callback': None,
         'income': {'monthly_income': None, 'monthly_expenses': None}}


def normalise(outcomes):
    """Defaults for missing fields; unknown enum values are dropped, never trusted."""
    out = copy.deepcopy(EMPTY)
    for key, value in (outcomes or {}).items():
        if key in out and isinstance(out[key], dict) and isinstance(value, dict):
            out[key].update({k: v for k, v in value.items() if k in out[key]})
        elif key in out:
            out[key] = value
    if out['reached'] not in (None, 'customer', 'third_party', 'no_answer', 'voicemail'):
        out['reached'] = None
    if out['hardship']['reason'] not in (None, *REASONS):
        out['hardship']['reason'] = 'other'
    if out['dispute']['type'] not in (None, *DISPUTES):
        out['dispute']['type'] = 'other'
    if out['representative']['kind'] not in (None, *REPRESENTATIVES):
        out['representative']['kind'] = 'other'
    for flag in ('identity_verified', 'recording_notice', 'cannot_afford', 'complaint', 'cease_request', 'vulnerable_disclosed'):
        out[flag] = bool(out[flag])
    return out


def _money(value):
    return f'CAD {float(value or 0):,.2f}'


def _num(value):
    try:
        return None if value is None or value == '' else float(value)
    except (TypeError, ValueError):
        return None


def _parse_date(value):
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- source facts

def load_extras(c, ctx):
    """Account payment terms and declared income for the calculator and affordability."""
    case, cust = ctx['case'], ctx['customer']
    account_id, product = case.get('primary_account_id'), case.get('primary_product')
    account = {'product': product, 'balance': None, 'regular_payment': None, 'apr': None, 'remaining_term_months': None, 'source': None}
    row = c.execute('SELECT current_balance, minimum_payment_due, purchase_apr FROM curated.card_accounts WHERE card_account_id=?', [account_id]).fetchone()
    if row:
        account.update(balance=row[0], regular_payment=row[1], apr=row[2], source=f'card_accounts:{account_id}')
    else:
        row = c.execute('''SELECT principal_balance, scheduled_payment_amount, interest_rate, remaining_term_months
            FROM curated.loan_accounts WHERE loan_id=? ORDER BY snapshot_date DESC NULLS LAST LIMIT 1''', [account_id]).fetchone()
        if row:
            account.update(balance=row[0], regular_payment=row[1], apr=row[2], remaining_term_months=row[3], source=f'loan_accounts:{account_id}')
        else:
            row = c.execute('SELECT overdraft_used FROM curated.deposit_accounts WHERE deposit_account_id=?', [account_id]).fetchone()
            if row:
                account.update(balance=row[0], source=f'deposit_accounts:{account_id}')
    if account['balance'] is None:
        account['balance'] = case.get('total_overdue')
    income = c.execute('''SELECT declared_annual_income, monthly_housing_cost, income_verified_flag FROM curated.customers
        WHERE crm_customer_id=? ORDER BY extract_ts DESC NULLS LAST LIMIT 1''', [cust['crm_customer_id']]).fetchone() or (None, None, False)
    obligations = c.execute('''SELECT coalesce(sum(p),0) FROM (
        SELECT a.minimum_payment_due p FROM gold.accounts g JOIN curated.card_accounts a ON a.card_account_id=g.account_id WHERE g.customer_id=?
        UNION ALL SELECT l.scheduled_payment_amount FROM gold.accounts g JOIN curated.loan_accounts l ON l.loan_id=g.account_id WHERE g.customer_id=?)''',
                            [case['customer_id'], case['customer_id']]).fetchone()[0]
    return {'account': account, 'declared_annual_income': income[0], 'housing': income[1],
            'income_verified': bool(income[2]), 'obligations': obligations}


def load(c, customer_id):
    ctx = ap.load(c, customer_id)
    if ctx is None:
        return None
    ctx['extras'] = load_extras(c, ctx)
    ctx['customer']['name'] = (c.execute('SELECT name FROM gold.customer_summary WHERE customer_id=?', [customer_id]).fetchone() or [customer_id])[0]
    return ctx


# ---------------------------------------------------------------- calculator

def _amortised(principal, annual_rate, months):
    if not principal or not months:
        return None
    r = (annual_rate or 0) / 12
    return principal / months if r == 0 else principal * r / (1 - (1 + r) ** -months)


def calculate(programme_rows, account):
    """Payment now / during / after for each programme, from the programme's own terms, so a
    new or changed programme in hardship_programs is priced without code changes."""
    balance, regular, apr = _num(account.get('balance')), _num(account.get('regular_payment')), _num(account.get('apr'))
    if regular is None and balance and account.get('product') == 'card':
        regular = max(10.0, round(balance * 0.03, 2))  # common card minimum when the source has none
    out = []
    for p in programme_rows:
        months = int(p['duration_months']) if p.get('duration_months') else None
        pct, rate = _num(p.get('payment_reduction_pct')), _num(p.get('rate_override'))
        text = f"{p.get('name', '')} {p.get('description', '')}".lower()
        row = {'payment_now': round(regular, 2) if regular else None, 'payment_during': None, 'payment_after': round(regular, 2) if regular else None,
               'monthly_saving': None, 'deferred_amount': None, 'interest_saving': None, 'one_time_amount': None, 'months': months, 'note': ''}
        if 'settle' in text:
            low = round(balance * (pct or 0.4), 2) if balance else None
            row.update(one_time_amount=low, payment_after=0, note=f'One payment of {int((pct or .4) * 100)}-70% of the balance; the rest is written off. Team lead decides the amount.')
        elif p.get('term_extension_max_months') and account.get('remaining_term_months') and balance:
            extra = int(p['term_extension_max_months'])
            new = _amortised(balance, apr, int(account['remaining_term_months']) + extra)
            row.update(payment_during=round(new, 2), payment_after=round(new, 2), months=int(account['remaining_term_months']) + extra,
                       note=f'Term extended by up to {extra} months; payment recalculated on the remaining balance.')
        elif rate is not None and pct and months and balance and 'counsel' not in text and 'debt management' not in text:
            fixed = balance / months if rate == 0 else _amortised(balance, rate, months)
            saving = balance * (apr or 0) * (months + 1) / 24 if rate == 0 else None
            row.update(payment_during=round(fixed, 2), payment_after=0, interest_saving=round(saving, 2) if saving else None,
                       note=f'Fixed payment for {months} months at {rate:.2%} interest' + ('; card is blocked.' if 'block' in text else '.'))
        elif 'counsel' in text or 'debt management' in text:
            fixed = balance / months if balance and months else None
            row.update(payment_during=round(fixed, 2) if fixed else None, note='Arranged through the non-profit credit counsellor; interest set by the plan.')
        elif pct and pct >= 1:
            row.update(payment_during=0, deferred_amount=round(regular * (months or 1), 2) if regular else None,
                       note='One payment skipped; it is added to the end of the term or balance.')
        elif rate is not None and balance and apr:
            saving = balance * max(apr - rate, 0) / 12 * (months or 1)
            row.update(payment_during=row['payment_now'], interest_saving=round(saving, 2),
                       note=f'Interest reduced to {rate:.2%} for {months} months; payment unchanged, more of it reduces the balance.')
        elif pct and regular:
            reduced = regular * (1 - pct)
            row.update(payment_during=round(reduced, 2), deferred_amount=round(regular * pct * (months or 1), 2),
                       note=f'Pay {1 - pct:.0%} of the regular payment for {months} months; interest keeps accruing.')
        elif months and balance:
            row.update(payment_during=round(balance / months, 2), payment_after=0, note=f'Balance repaid over {months} months.')
        if row['payment_now'] is not None and row['payment_during'] is not None:
            row['monthly_saving'] = round(row['payment_now'] - row['payment_during'], 2)
        out.append(row)
    return out


# ---------------------------------------------------------------- the session

def _apply(ctx, o):
    """What the customer said, applied to a copy of the source context."""
    ctx = copy.deepcopy(ctx)
    case, cust = ctx['case'], ctx['customer']
    if o['cease_request']:
        cust['cease_communication_flag'] = True
    if o['representative']['stated']:
        kind = REPRESENTATIVES.get(o['representative']['kind'])
        if kind:
            cust['third_party_relationship'] = kind
        else:
            case['third_party_rep_flag'] = True
    if o['dispute']['raised']:
        case.update(dispute_flag=True, dispute_status='open', dispute_type=o['dispute']['type'] or 'other')
    if o['complaint']:
        case.update(complaint_flag=True, complaint_stage=case.get('complaint_stage') or 'frontline')
    if o['vulnerable_disclosed']:
        case['vulnerable_customer_flag'] = True
    promise = o['promise'] or {}
    due, amount = _parse_date(promise.get('date')), _num(promise.get('amount'))
    if due and amount:
        ctx['promise'] = {'ptp_id': 'NEW (this call)', 'ptp_amount': amount, 'ptp_due_date': due}
    return ctx


def _hardship_status(base_status, o):
    return 'recorded' if o['hardship']['stated'] else base_status


def _slot_check(ctx, when, call_at, cap, holiday_names):
    """Is a callback at this customer-local time allowed? This call counts as an attempt."""
    cust = ctx['customer']
    tz = ZoneInfo(cust.get('time_zone') or ap.FALLBACK_TZ)
    local = when.astimezone(tz)
    lo, hi = ap._clock(cust.get('permitted_call_start_local'), '07:00'), ap._clock(cust.get('permitted_call_end_local'), '21:00')
    if local.date() in holiday_names:
        return f"{ap._day(local.date())} is a statutory holiday ({holiday_names[local.date()]})."
    if local.weekday() == 6:
        if not cust.get('sunday_contact_permitted'):
            return 'This customer does not permit Sunday contact.'
        lo, hi = max(lo, time(13)), min(hi, time(17))
    if not lo <= local.time() <= hi:
        return f"Outside permitted hours ({lo:%H:%M}-{hi:%H:%M} their time)."
    attempts = [a for a in (ap._utc(x) for x in ctx['attempts']) if a] + ([call_at] if call_at else [])
    used = sum(1 for a in attempts if when - timedelta(days=7) < a <= when)
    if used >= cap:
        return f'{used} attempts would already be in the 7 days before it (cap {cap}).'
    if when <= (call_at or when):
        return 'The callback must be after this call.'
    return None


def session(ctx, base_status, outcomes):
    o = normalise(outcomes)
    base = ap.build(ctx, base_status)
    held = base['steps'][0]['status'] == 'stop'
    window = base['contact_window'] or {}
    call_at = datetime.fromisoformat(window['at_utc']) if window.get('at_utc') else None
    changed = _apply(ctx, o)
    status = _hardship_status(base_status, o)
    plan = ap.build(changed, status)
    cust, case, extras = ctx['customer'], ctx['case'], ctx['extras']
    tz = ZoneInfo(cust.get('time_zone') or ap.FALLBACK_TZ)
    cap = int(case.get('contact_cap_7d') or ap.DEFAULT_CAP_7D)
    holiday_names = ap.holidays((call_at or ap.AS_OF).date(), days=60)
    french = (cust.get('preferred_language') or '').lower().startswith('fr')
    vulnerable = bool(case.get('vulnerable_customer_flag') or cust.get('vulnerability_flag') or o['vulnerable_disclosed'])

    blocked = held or call_at is None
    can_discuss = not blocked and o['reached'] == 'customer' and o['identity_verified'] and o['recording_notice']
    stage = ('blocked' if blocked else 'pre_call' if o['reached'] is None else 'wrap_up' if o['reached'] in ('no_answer', 'voicemail', 'third_party')
             else 'verification' if not can_discuss else 'conversation')
    checks = []

    def check(key, level, message, *policy):
        checks.append({'key': key, 'status': level, 'message': message, 'policy': [ap.POLICY.get(p, p) for p in policy]})

    if blocked:
        check('blocked', 'block', base['steps'][0]['detail'] if held else f'No allowed contact slot in the next {ap.HORIZON_DAYS} days.', 'hold' if held else 'cap')
    if o['reached'] == 'third_party':
        check('third_party', 'block', 'Do not disclose any debt details to a third party; leave only a name and number.', 'rep')
    if o['reached'] == 'voicemail':
        check('voicemail', 'warn', 'Voicemail: leave a name and callback number only, no debt details. It counts as an attempt.', 'cap')
    if o['reached'] == 'customer' and not can_discuss:
        check('verification', 'block', 'Read the recording notice and verify identity (date of birth) before discussing the debt.', 'SCR-MID-STD-EN v2.0')
    if o['cease_request']:
        check('cease', 'warn', 'Cease request: stop calls, texts and emails; ask the customer to confirm in writing. Required letters continue.', 'cease')
    if o['representative']['stated']:
        check('representative', 'warn', 'A representative acts for the customer: end the debt discussion and continue only through them.', 'rep')
    if o['dispute']['raised']:
        if o['dispute']['type'] == 'fraud':
            check('fraud', 'warn', 'Fraud claim: transfer to the fraud team; do not ask for payment on the disputed amount.', 'dispute')
        else:
            check('dispute', 'warn', 'Open a dispute and pause payment requests for the disputed amount until it is resolved.', 'dispute')
    if o['complaint']:
        check('complaint', 'warn', 'Record the complaint today and escalate it to a team lead; tell the customer the stages.', 'complaint')
    if vulnerable:
        check('vulnerable', 'warn' if ctx.get('agent_certified') else 'block',
              'Vulnerable customer: use SCR-VUL, offer hardship options first, never pressure.' +
              ('' if ctx.get('agent_certified') else ' The assigned agent is not certified: hand over to a certified agent.'), 'vulnerable')

    # Hardship options, priced from the programme terms and the account.
    rows = ap.programmes(ctx['programs'], changed, ap.LEVELS['clear' if status == 'recorded' else 'possible' if status == 'possible' else 'none'],
                         (call_at or ap.AS_OF).date()) if (status in ('recorded', 'possible') or o['cannot_afford']) else []
    terms = {(p['program_id'], p['version']): p for p in ctx['programs']}
    priced = calculate([{**terms[(r['program_id'], r['version'])], 'name': r['name'], 'description': r['description']} for r in rows], extras['account'])
    options = [{**{k: r[k] for k in ('program_id', 'version', 'name', 'status', 'approver', 'reasons')}, **price} for r, price in zip(rows, priced)]
    chosen = next((x for x in options if x['program_id'] == o['programme']), None)
    if o['programme'] and not chosen:
        check('programme', 'block', f"{o['programme']} is not available for this product or hardship level.", 'hardship')
    elif chosen:
        if chosen['status'] == 'not_eligible':
            check('programme', 'block', f"{chosen['name']} fails the recorded rules: {'; '.join(chosen['reasons'])}.", 'hardship')
        elif chosen['approver'] != 'agent':
            check('programme', 'warn', f"{chosen['name']} needs approval by a {chosen['approver'].replace('_', ' ')}; submit it as a request.", 'specialist')
        else:
            check('programme', 'ok', f"{chosen['name']} can be agreed by the agent; confirm the terms back to the customer.", 'hardship')
    if (status == 'recorded' or o['cannot_afford']) and not o['programme'] and can_discuss:
        check('offer_first', 'warn', 'Offer at least one eligible hardship option before asking for payment.', 'hardship')

    # Affordability: declared income (or what the customer says now) minus housing and other obligations.
    stated_income, stated_expenses = _num(o['income']['monthly_income']), _num(o['income']['monthly_expenses'])
    declared = _num(extras['declared_annual_income'])
    income = stated_income if stated_income is not None else (declared / 12 if declared else None)
    housing, obligations = _num(extras['housing']), _num(extras['obligations'])
    spend = stated_expenses if stated_expenses is not None else ((housing or 0) + (obligations or 0) if housing is not None or obligations else None)
    disposable = round(income - spend, 2) if income is not None and spend is not None else None
    promise = o['promise'] or {}
    amount, due = _num(promise.get('amount')), _parse_date(promise.get('date'))
    share = round(amount / disposable, 3) if amount and disposable and disposable > 0 else None
    affordability = {'monthly_income': round(income, 2) if income is not None else None, 'monthly_obligations': round(obligations, 2) if obligations is not None else None,
                     'housing': round(housing, 2) if housing is not None else None, 'disposable': disposable,
                     'source': 'stated on this call' if stated_income is not None or stated_expenses is not None else 'declared income and housing cost on the customer record; loan and card payments from accounts',
                     'verified': bool(extras['income_verified']) and stated_income is None, 'promise_share_of_disposable': share}

    # Promise rules (PRC-COLL-010) and payment-request rules (POL-COLL-004 §4.2).
    payday = _parse_date(plan.get('payday_estimate'))
    if o['promise']:
        call_day = (call_at.astimezone(tz).date() if call_at else ap.AS_OF.date())
        if not can_discuss:
            check('promise', 'block', 'A promise can only be taken after identity is verified.', 'ptp')
        elif not amount or amount <= 0:
            check('promise', 'block', 'Enter the promised amount.', 'ptp')
        elif not due:
            check('promise', 'block', 'Enter the promised date.', 'ptp')
        elif due < call_day:
            check('promise', 'block', 'The promised date is in the past.', 'ptp')
        elif due > call_day + timedelta(days=ap.PTP_MAX_DAYS):
            check('promise', 'block', f'Promised date must be within {ap.PTP_MAX_DAYS} days (by {ap._day(call_day + timedelta(days=ap.PTP_MAX_DAYS))}).', 'ptp')
        else:
            if payday and due < payday and payday <= call_day + timedelta(days=ap.PTP_MAX_DAYS):
                check('promise_payday', 'warn', f'The date is before their estimated payday ({ap._day(payday)}); a date on or after payday is more likely to be kept.', 'ptp')
            if o['cannot_afford']:
                check('promise_afford', 'warn', 'The customer said they cannot afford payment: do not press for this amount; agree an affordable one.', 'hardship')
            if share and share > 0.5:
                check('promise_share', 'warn', f'The promise is {share:.0%} of estimated monthly disposable income; check it is affordable.', 'hardship')
            if case.get('total_overdue') and amount > float(case['total_overdue']) * 1.05:
                check('promise_amount', 'warn', f"More than the overdue amount ({_money(case['total_overdue'])}); confirm the figure.", 'ptp')
            if o['dispute']['raised']:
                check('promise_dispute', 'warn', 'Exclude the disputed amount from the promise.', 'dispute')
            if not [c for c in checks if c['key'].startswith('promise') and c['status'] != 'ok']:
                check('promise', 'ok', f"Promise of {_money(amount)} on {ap._day(due)} meets the promise rules; read it back and offer a payment link.", 'ptp_confirm')
    if o['callback']:
        cb_date, cb_time = _parse_date(o['callback'].get('date')), o['callback'].get('time')
        try:
            when = datetime.combine(cb_date, time.fromisoformat(cb_time), tz).astimezone(timezone.utc) if cb_date and cb_time else None
        except ValueError:
            when = None
        problem = 'Enter a valid callback date and time.' if when is None else _slot_check(ctx, when, call_at, cap, holiday_names)
        check('callback', 'block' if problem else 'ok', problem or f'Callback {ap._day(cb_date)} at {cb_time} their time is allowed.', 'hours', 'cap')

    # Script for this call.
    script = [
        {'key': 'recording_notice', 'text': 'Greet, give your name and the bank, and read the recording notice: "This call may be recorded for quality and training purposes."', 'required': True, 'done': o['recording_notice'], 'policy': ['SCR-MID-STD-EN v2.0']},
        {'key': 'identity_verified', 'text': 'Verify identity (date of birth) before disclosing any debt.', 'required': True, 'done': o['identity_verified'], 'policy': ['SCR-MID-STD-EN v2.0']},
        {'key': 'purpose', 'text': f"State the purpose and the past-due amount accurately: {_money(case.get('total_overdue'))} on the {str(case.get('primary_product') or 'account').replace('_', ' ')}.", 'required': False, 'done': can_discuss, 'policy': ['SCR-MID-STD-EN v2.0']},
        {'key': 'listen', 'text': 'Listen. If hardship is mentioned, acknowledge it, record it and offer an eligible option before asking for payment.', 'required': False, 'done': can_discuss and (o['hardship']['stated'] or bool(o['promise'])), 'policy': [ap.POLICY['hardship']]},
        {'key': 'agree', 'text': 'Agree a promise or arrangement; read back the amount and date.', 'required': False, 'done': bool(o['promise'] or o['programme']), 'policy': [ap.POLICY['ptp_confirm']]},
        {'key': 'close', 'text': 'Close respectfully and confirm the next steps.', 'required': False, 'done': False, 'policy': ['SCR-MID-STD-EN v2.0']},
    ]
    if vulnerable:
        script.insert(2, {'key': 'vulnerable', 'text': 'Speak slowly, check understanding, offer a call back at a better time or a trusted person; never pressure.', 'required': True, 'done': False, 'policy': ['SCR-VUL-EN', ap.POLICY['vulnerable']]})
    if french:
        script.insert(0, {'key': 'french', 'text': 'Conduct the call in French (Montréal site).', 'required': True, 'done': False, 'policy': [ap.POLICY['language']]})

    _reflect_agreements(plan, o, chosen, checks)
    if blocked:  # nothing to say to the customer: no script, no call record beyond the restriction
        script = []
        o = normalise({})
    wrap = wrap_up(ctx, o, plan, checks, chosen, call_at, tz, stage, cap, holiday_names)
    return {'customer': {'customer_id': case['customer_id'], 'name': cust.get('name'), 'preferred_language': cust.get('preferred_language'),
                         'time_zone': cust.get('time_zone') or 'unknown', 'local_time_now': call_at.astimezone(tz).strftime('%a %d %b %H:%M') if call_at else None,
                         'product': case.get('primary_product'), 'dpd': case.get('current_dpd'), 'overdue_cad': case.get('total_overdue'), 'case_id': case['case_id'],
                         'call_time_note': 'Simulated at the first allowed contact time after the data snapshot.' if call_at else 'No allowed contact time.'},
            'stage': stage, 'can_discuss_debt': can_discuss, 'script': script, 'plan': plan, 'checks': checks,
            'calculator': {'account': extras['account'], 'options': options}, 'affordability': affordability, 'wrap_up': wrap, 'outcomes': o}


def _reflect_agreements(plan, o, chosen, checks):
    """Steps the customer has now agreed become done (or 'submit for approval') in the live plan."""
    promise_ok = any(c['key'] == 'promise' and c['status'] == 'ok' for c in checks)
    for step in plan['steps']:
        if step['key'] == 'hardship' and chosen and chosen['status'] != 'not_eligible':
            needs = chosen['approver'] != 'agent'
            step.update(status='action' if needs else 'clear',
                        title=f"Submit {chosen['name']} for {chosen['approver'].replace('_', ' ')} approval" if needs else f"Agreed: {chosen['name']}",
                        detail=f"{chosen['program_id']} v{chosen['version']}. " + (chosen.get('note') or ''))
        if step['key'] == 'payment_ask' and promise_ok:
            amount, due = _num(o['promise']['amount']), _parse_date(o['promise']['date'])
            step.update(status='clear', title=f'Promise taken: {_money(amount)} on {ap._day(due)}', detail='Read back the amount and date and offer a payment link.')
    first = next((s for s in plan['steps'] if s['status'] in ('stop', 'action', 'wait') and s['key'] != 'contact_window'), None)
    plan['next_action'] = first['title'] if first else 'Close the call and submit the wrap-up for review'


def wrap_up(ctx, o, plan, checks, chosen, call_at, tz, stage, cap, holiday_names):
    case, cust = ctx['case'], ctx['customer']
    lines, codes, follow = [], [], []
    if stage == 'blocked':
        return {'note': f"No call made on case {case['case_id']}: {plan['steps'][0]['title']}. {plan['steps'][0]['detail']}",
                'outcome_codes': ['NO_CONTACT_RESTRICTION'], 'follow_ups': [], 'ready_to_submit': False,
                'blocking': ['Contact is not allowed for this customer.']}
    when = call_at.astimezone(tz).strftime('%a %d %b %Y %H:%M') if call_at else 'not allowed'
    reached = {'customer': 'Reached the customer', 'third_party': 'Reached a third party (no debt details disclosed)',
               'no_answer': 'No answer', 'voicemail': 'Voicemail (name and number only)'}.get(o['reached'], 'Not yet recorded')
    lines.append(f"Call {when} ({cust.get('time_zone') or 'time zone unknown'}), case {case['case_id']}: {reached}.")
    codes.append({'customer': 'RPC', 'third_party': 'THIRD_PARTY', 'no_answer': 'NO_ANSWER', 'voicemail': 'VOICEMAIL'}.get(o['reached'], 'NOT_STARTED'))
    if o['reached'] == 'customer':
        lines.append(f"Recording notice {'read' if o['recording_notice'] else 'NOT read'}; identity {'verified' if o['identity_verified'] else 'NOT verified'}.")
    if o['hardship']['stated']:
        lines.append(f"Customer stated financial hardship ({(o['hardship']['reason'] or 'other').replace('_', ' ')}); hardship recorded per {ap.POLICY['hardship']}.")
        codes.append('HARDSHIP_STATED')
    if o['cannot_afford']:
        lines.append('Customer said they cannot afford a payment now; no payment was pressed.')
        codes.append('CANNOT_AFFORD')
    if chosen:
        lines.append(f"Hardship option selected: {chosen['name']} ({chosen['program_id']} v{chosen['version']}); approver: {chosen['approver'].replace('_', ' ')}.")
        codes.append('PROGRAMME_REQUESTED' if chosen['approver'] != 'agent' else 'PROGRAMME_AGREED')
        if chosen['approver'] != 'agent':
            follow.append({'type': 'approval', 'when': 'today', 'reason': f"{chosen['approver'].replace('_', ' ').capitalize()} approves {chosen['program_id']}."})
    promise = o['promise'] or {}
    due, amount = _parse_date(promise.get('date')), _num(promise.get('amount'))
    if due and amount and not any(c['key'] == 'promise' and c['status'] == 'block' for c in checks):
        lines.append(f"Promise to pay {_money(amount)} on {ap._day(due)} {due.year}; amount and date read back.")
        codes.append('PTP')
        # One reminder before the due date, in an allowed slot, counting this call as an attempt.
        attempts = list(ctx['attempts']) + ([call_at] if call_at else [])
        slot = ap.contact_window(attempts, cust.get('time_zone'), cust.get('permitted_call_start_local'), cust.get('permitted_call_end_local'),
                                 cust.get('sunday_contact_permitted'), holiday_names, (call_at or ap.AS_OF) + timedelta(days=1), cap)
        if slot.get('available') and date.fromisoformat(slot['date']) < due:
            follow.append({'type': 'reminder', 'when': f"{slot['day']} from {slot['from_local']} their time",
                           'reason': f'One payment reminder before {ap._day(due)}; it counts toward the {cap}-in-7-days cap.'})
        else:
            follow.append({'type': 'check_payment', 'when': f'{ap._day(due + timedelta(days=3))}', 'reason': 'No allowed reminder slot before the due date; check payment after the grace period.'})
    for key, text, code in [('dispute', 'Dispute opened; payment requests paused for the disputed amount.', 'DISPUTE'),
                            ('fraud', 'Fraud claim: transferred to the fraud team.', 'FRAUD'),
                            ('complaint', 'Complaint recorded and escalated to a team lead.', 'COMPLAINT'),
                            ('cease', 'Customer asked us to stop contact; written confirmation requested; calls, texts and emails stop.', 'CEASE_REQUEST'),
                            ('representative', 'Customer is represented; further contact only through the representative.', 'REPRESENTATIVE')]:
        if any(c['key'] == key for c in checks):
            lines.append(text)
            codes.append(code)
            if key == 'complaint':
                follow.append({'type': 'escalation', 'when': 'today', 'reason': 'Team lead reviews the complaint (POL-COLL-007 §8.1).'})
    if o['vulnerable_disclosed']:
        lines.append('Customer disclosed circumstances that make them vulnerable; vulnerable-customer approach applied (details not recorded in the note).')
        codes.append('VULNERABLE_SAFEGUARD')
    if o['callback'] and any(c['key'] == 'callback' and c['status'] == 'ok' for c in checks):
        follow.append({'type': 'callback', 'when': f"{o['callback']['date']} {o['callback']['time']} their time", 'reason': 'Customer asked for a call back.'})
        codes.append('CALLBACK')
    if o['reached'] in ('no_answer', 'voicemail') and not o['callback']:
        nxt = ap.contact_window(list(ctx['attempts']) + ([call_at] if call_at else []), cust.get('time_zone'), cust.get('permitted_call_start_local'),
                                cust.get('permitted_call_end_local'), cust.get('sunday_contact_permitted'), holiday_names,
                                (call_at or ap.AS_OF) + timedelta(hours=1), cap)
        if nxt.get('available'):
            follow.append({'type': 'retry', 'when': f"{nxt['day']} from {nxt['from_local']} their time", 'reason': 'Next allowed attempt.'})
    blocking = [c['message'] for c in checks if c['status'] == 'block' and c['key'] not in ('blocked',)]
    ready = o['reached'] is not None and not blocking and stage != 'blocked'
    return {'note': '\n'.join(lines), 'outcome_codes': codes, 'follow_ups': follow, 'ready_to_submit': ready, 'blocking': blocking}


# ---------------------------------------------------------------- notes → proposals

_REASON_BY_CUE = {'income_loss': 'job_loss', 'income_reduction': 'reduced_income', 'income_delay': 'reduced_income',
                  'illness_or_injury': 'illness', 'separation': 'separation', 'disaster_or_evacuation': 'disaster',
                  'expense_pressure': 'expense_increase', 'payment_difficulty': 'other', 'hardship_request': 'other'}
# An agreed or offered arrangement repeats the programme's own words ("reduced payment",
# "deferral"); it is an outcome of the call, not a statement of hardship by the customer.
_AGREEMENT = re.compile(r'\b(agreed|accepted|chose|selected|offered|set up|signed up|enrolled)\b.{0,60}\b(plan|payment|programme|program|deferral|extension|arrangement)\b')
_MONTHS = {m: i for i, m in enumerate(['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'], 1)}


def _sentences(note):
    return [s.strip() for s in re.split(r'(?<=[.!?;])\s+|\n+', note or '') if s.strip()]


def _date_in(sentence, today):
    s = sentence.lower()
    m = re.search(r'\b(\d{4}-\d{2}-\d{2})\b', s)
    if m:
        return _parse_date(m.group(1))
    m = re.search(r'\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})\b|\b(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)', s)
    if m:
        month, day = (_MONTHS[m.group(1)], int(m.group(2))) if m.group(1) else (_MONTHS[m.group(4)], int(m.group(3)))
        try:
            d = date(today.year, month, day)
            return d if d >= today else date(today.year + 1, month, day)
        except ValueError:
            return None
    m = re.search(r'\b(?:on|this|next|by)\s+(mon|tue|wed|thu|fri|sat|sun)[a-z]*', s)
    if m:
        target = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'].index(m.group(1))
        return today + timedelta(days=(target - today.weekday()) % 7 or 7)
    return None


def extract_rules(note, today):
    """Local fallback: the same versioned cues as the classifier, plus explicit amounts and dates."""
    proposals = []
    for sentence in _sentences(note):
        cues = [k for k, v in text_features(sentence).items() if v]
        if cues and not _AGREEMENT.search(normalize_text(sentence)):
            proposals += [{'field': 'hardship.stated', 'value': True, 'quote': sentence, 'source': 'rules'},
                          {'field': 'hardship.reason', 'value': _REASON_BY_CUE.get(cues[0], 'other'), 'quote': sentence, 'source': 'rules'}]
        n = normalize_text(sentence)
        amount = re.search(r'(?:\$|cad\s?)\s?(\d[\d,]*(?:\.\d{1,2})?)|(\d[\d,]*(?:\.\d{1,2})?)\s?(?:\$|dollars|cad)', n)
        if amount and re.search(r'promis|will pay|can pay|pay\b|paiement|payer', n):
            value = float((amount.group(1) or amount.group(2)).replace(',', ''))
            due = _date_in(sentence, today)
            proposals.append({'field': 'promise', 'value': {'amount': value, 'date': due.isoformat() if due else None}, 'quote': sentence, 'source': 'rules'})
        if re.search(r'stop (calling|contacting)|do not (call|contact)|don.t (call|contact)|cease|cessez', n):
            proposals.append({'field': 'cease_request', 'value': True, 'quote': sentence, 'source': 'rules'})
        if re.search(r'fraud|not my (charge|transaction)|didn.t make (this|that|the)', n):
            proposals.append({'field': 'dispute', 'value': {'raised': True, 'type': 'fraud'}, 'quote': sentence, 'source': 'rules'})
        elif re.search(r'disput|contest|wrong (fee|charge)|fee.{0,20}(error|wrong|unfair)|payment (was )?not (applied|posted)', n):
            kind = 'payment_not_applied' if re.search(r'not (applied|posted)', n) else 'fee' if 'fee' in n else 'other'
            proposals.append({'field': 'dispute', 'value': {'raised': True, 'type': kind}, 'quote': sentence, 'source': 'rules'})
        if re.search(r'complain|ombudsman|unhappy with|plainte', n):
            proposals.append({'field': 'complaint', 'value': True, 'quote': sentence, 'source': 'rules'})
        rep = re.search(r'\b(lawyer|attorney|avocat|credit counsel|counsell?or|trustee|syndic)', n)
        if rep:
            kind = 'lawyer' if rep.group(1) in ('lawyer', 'attorney', 'avocat') else 'trustee' if rep.group(1) in ('trustee', 'syndic') else 'credit_counsellor'
            proposals.append({'field': 'representative', 'value': {'stated': True, 'kind': kind}, 'quote': sentence, 'source': 'rules'})
        if re.search(r'call (me )?back|rappel', n):
            proposals.append({'field': 'callback', 'value': None, 'quote': sentence, 'source': 'rules'})
    return _first_per_field(proposals)


def _first_per_field(proposals):
    """One proposal per outcome: the agent confirms each field once, from its first supporting quote."""
    seen, out = set(), []
    for p in proposals:
        if p['field'] not in seen:
            seen.add(p['field'])
            out.append(p)
    return out


EXTRACT_SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'properties': {'proposals': {'type': 'array', 'maxItems': 12, 'items': {
        'type': 'object', 'additionalProperties': False,
        'properties': {
            'field': {'type': 'string', 'enum': ['hardship', 'cannot_afford', 'promise', 'dispute', 'complaint', 'cease_request', 'representative', 'vulnerable_disclosed', 'callback']},
            'hardship_reason': {'type': ['string', 'null'], 'enum': [*REASONS, None]},
            'dispute_type': {'type': ['string', 'null'], 'enum': [*DISPUTES, None]},
            'representative_kind': {'type': ['string', 'null'], 'enum': ['lawyer', 'credit_counsellor', 'trustee', 'other', None]},
            'amount': {'type': ['number', 'null']}, 'date': {'type': ['string', 'null']},
            'quote': {'type': 'string'}},
        'required': ['field', 'hardship_reason', 'dispute_type', 'representative_kind', 'amount', 'date', 'quote']}}},
    'required': ['proposals'],
}


def verify_model_proposals(raw, note, today):
    """Keep only proposals whose quote is verbatim in the note and whose values pass the rules."""
    out, flat = [], ' '.join((note or '').split())
    for item in raw if isinstance(raw, list) else []:
        quote = ' '.join(str(item.get('quote') or '').split())
        if len(quote) < 4 or quote not in flat:
            continue
        field = item.get('field')
        if field == 'hardship':
            out += [{'field': 'hardship.stated', 'value': True, 'quote': quote, 'source': 'gemini'},
                    {'field': 'hardship.reason', 'value': item.get('hardship_reason') if item.get('hardship_reason') in REASONS else 'other', 'quote': quote, 'source': 'gemini'}]
        elif field == 'promise':
            amount, due = _num(item.get('amount')), _parse_date(item.get('date'))
            if amount and amount > 0 and str(int(amount)) in quote.replace(',', ''):
                out.append({'field': 'promise', 'value': {'amount': amount, 'date': due.isoformat() if due and due >= today else None}, 'quote': quote, 'source': 'gemini'})
        elif field == 'dispute':
            out.append({'field': 'dispute', 'value': {'raised': True, 'type': item.get('dispute_type') if item.get('dispute_type') in DISPUTES else 'other'}, 'quote': quote, 'source': 'gemini'})
        elif field == 'representative':
            kind = item.get('representative_kind')
            out.append({'field': 'representative', 'value': {'stated': True, 'kind': kind if kind in REPRESENTATIVES else 'other'}, 'quote': quote, 'source': 'gemini'})
        elif field in ('cannot_afford', 'complaint', 'cease_request', 'vulnerable_disclosed'):
            out.append({'field': field, 'value': True, 'quote': quote, 'source': 'gemini'})
        elif field == 'callback':
            out.append({'field': 'callback', 'value': None, 'quote': quote, 'source': 'gemini'})
    return out


def extract(note, today, client=None):
    note = (note or '')[:4000]
    if client is not None and client.configured:
        try:
            raw = client.extract_outcomes(note, today.isoformat(), EXTRACT_SCHEMA)
            found = _first_per_field(verify_model_proposals(raw.get('proposals'), note, today))
            return {'proposals': found, 'provider': 'gemini',
                    'message': None if found else 'No outcome with a verifiable quote was found in the note.'}
        except Exception:  # provider unavailable or invalid: fall back, never fail the call
            pass
    found = extract_rules(note, today)
    return {'proposals': found, 'provider': 'rules', 'message': None if found else 'No supported outcome was recognised; record outcomes with the controls.'}
