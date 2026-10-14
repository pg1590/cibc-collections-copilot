"""Agent work queue: open cases in a fixed, explainable urgency order. Vulnerability
and protected fields never change the order (POL-COLL-004 §4.5-4.6)."""
from datetime import timedelta

from app import action_plan as ap

TIERS = [
    ('stop_now', 'Stop contact now', 'Insolvency, cease-communication or deceased restriction recorded but the case is still in normal treatment.'),
    ('promise_due', 'Promise due soon', 'An open promise is due within 3 days: a reminder is the only contact needed.'),
    ('hardship_no_plan', 'Hardship, no plan yet', 'Hardship is recorded with no plan: offer an eligible programme before any payment request.'),
    ('near_write_off', 'Close to write-off', '150-180 days past due. Every charge-off recorded in collections_cases happened at 181 days past due.'),
    ('promise_overdue', 'Promise past grace', 'An open promise passed its 2-business-day grace period without a recorded outcome.'),
    ('standard', 'Standard', 'Remaining cases, highest days past due first.'),
    ('on_hold', 'On hold: no contact', 'Case is already on insolvency hold or a no-contact restriction is recorded; verify only.'),
]
RANK = {key: i for i, (key, _, _) in enumerate(TIERS)}

QUEUE_SQL = f'''SELECT g.case_id,g.customer_id,s.name,g.primary_product,g.current_dpd,g.total_overdue,g.case_status,g.hardship_flag,
 g.hardship_plan_type,g.cease_contact_flag,g.insolvency_hold_flag,g.deceased_hold_flag,g.third_party_rep_flag,g.dispute_flag,g.dispute_status,
 g.vulnerable_customer_flag,g.queue,p.ptp_id,p.ptp_amount,p.ptp_due_date,
 c.time_zone,c.permitted_call_start_local,c.permitted_call_end_local,c.sunday_contact_permitted,c.preferred_language,
 c.bankruptcy_flag,c.consumer_proposal_flag,c.cease_communication_flag,c.deceased_flag,c.consent_call,c.consent_sms,c.consent_email,
 c.internal_do_not_call_flag
FROM gold.cases g JOIN gold.customer_summary s USING(customer_id) JOIN gold.customers gc USING(customer_id)
LEFT JOIN curated.customers c ON c.crm_customer_id=gc.crm_customer_id
LEFT JOIN (SELECT case_id,arg_max(ptp_id,ptp_due_date) ptp_id,arg_max(ptp_amount,ptp_due_date) ptp_amount,max(ptp_due_date) ptp_due_date
  FROM curated.promises_to_pay WHERE ptp_status='open' GROUP BY 1) p ON p.case_id=g.case_id
WHERE g.outcome IS NULL AND g.assigned_agent_id=?'''


def _tier(r, as_of_date):
    restricted = r['bankruptcy_flag'] or r['consumer_proposal_flag'] or r['insolvency_hold_flag'] or \
        r['cease_communication_flag'] or r['cease_contact_flag'] or r['deceased_flag'] or r['deceased_hold_flag']
    if restricted:
        insolvent = r['bankruptcy_flag'] or r['consumer_proposal_flag'] or r['insolvency_hold_flag']
        if insolvent and r['case_status'] != 'insolvency_hold':
            return 'stop_now', 'Insolvency recorded but case not on hold: stop contact and move it to insolvency hold.'
        return 'on_hold', 'Insolvency hold.' if insolvent else 'No-contact restriction recorded.'
    due = r['ptp_due_date']
    if due and as_of_date <= due <= as_of_date + timedelta(days=3):
        return 'promise_due', f"Promise of CAD {r['ptp_amount'] or 0:,.2f} due {ap._day(due)}: send a reminder, don't ask for more."
    if r['hardship_flag'] and not r['hardship_plan_type']:
        return 'hardship_no_plan', 'Hardship recorded, no plan yet: offer a programme first.'
    if r['current_dpd'] is not None and 150 <= r['current_dpd'] <= 180:
        return 'near_write_off', f"{r['current_dpd']} days past due: charge-off happens at 181 ({181 - r['current_dpd']} days left)."
    if due and due < as_of_date - timedelta(days=4):
        return 'promise_overdue', f"Promise due {ap._day(due)} still open: confirm whether it was paid."
    return 'standard', f"{r['current_dpd'] or 0} days past due, CAD {r['total_overdue'] or 0:,.2f} overdue."


def build(c, agent_id, as_of=ap.AS_OF, limit=500):
    from app.main import records
    rows = records(c, QUEUE_SQL, [agent_id])
    if not rows:
        return {'agent_id': agent_id, 'items': [], 'tiers': [], 'as_of': as_of.isoformat()}
    ids = [r['case_id'] for r in rows]
    marks = ','.join('?' for _ in ids)
    attempts = {}
    for case_id, ts in c.execute(
            f"""SELECT case_id,contact_ts_utc FROM curated.contact_history WHERE case_id IN ({marks}) AND direction='outbound'
            AND coalesce(channel_v2,channel) IN {ap.ATTEMPT_CHANNELS} AND contact_ts_utc>? AND contact_ts_utc<=?""",
            [*ids, (as_of - timedelta(days=8)).replace(tzinfo=None), as_of.replace(tzinfo=None)]).fetchall():
        attempts.setdefault(case_id, []).append(ts)
    holiday_names = ap.holidays()
    items = []
    for r in rows:
        tier, reason = _tier(r, as_of.date())
        window = None
        if tier not in ('stop_now', 'on_hold'):
            w = ap.contact_window(attempts.get(r['case_id'], []), r['time_zone'], r['permitted_call_start_local'],
                                  r['permitted_call_end_local'], r['sunday_contact_permitted'], holiday_names, as_of)
            window = {k: w.get(k) for k in ('available', 'date', 'day', 'from_local', 'until_local', 'time_zone', 'attempts_last_7d', 'at_utc')}
            due = r['ptp_due_date']
            if tier == 'promise_due' and (not w['available'] or w['date'] > due.isoformat()):
                reason = (f"Promise of CAD {r['ptp_amount'] or 0:,.2f} due {ap._day(due)}, but no contact is allowed before then: "
                          'check for payment after the 2-business-day grace period.')
        items.append({'case_id': r['case_id'], 'customer_id': r['customer_id'], 'name': r['name'], 'product': r['primary_product'],
                      'dpd': r['current_dpd'], 'overdue_cad': r['total_overdue'], 'tier': tier, 'tier_label': TIERS[RANK[tier]][1],
                      'reason': reason, 'next_contact': window,
                      'flags': [f for f, on in [('representative', r['third_party_rep_flag']), ('dispute', r['dispute_flag'] and r['dispute_status'] == 'open'),
                                                ('vulnerable_safeguard', r['vulnerable_customer_flag']), ('french', (r['preferred_language'] or '').lower().startswith('fr'))] if on]})
    # Tier first; then whoever can be contacted soonest; then days past due and balance.
    due = {r['case_id']: r['ptp_due_date'] for r in rows}
    items.sort(key=lambda i: (RANK[i['tier']], due[i['case_id']].toordinal() if i['tier'] == 'promise_due' else -(i['dpd'] or 0) if i['tier'] == 'near_write_off' else 0,
                              (i['next_contact'] or {}).get('at_utc') or '9999', -(i['dpd'] or 0), -(i['overdue_cad'] or 0), i['case_id']))
    for n, item in enumerate(items, 1):
        item['position'] = n
    counts = {}
    for i in items:
        counts[i['tier']] = counts.get(i['tier'], 0) + 1
    return {'agent_id': agent_id, 'as_of': as_of.isoformat(), 'total': len(items), 'items': items[:limit],
            'tiers': [{'key': k, 'label': label, 'rule': rule, 'count': counts.get(k, 0)} for k, label, rule in TIERS],
            'ordering': 'Tier; within a tier, earliest promise due date or highest days past due where relevant, then earliest allowed contact time, then days past due and overdue balance. '
                        'Vulnerability, language and protected attributes do not change the order.'}
