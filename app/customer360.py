"""Customer 360 views: one dated history across systems, and a contact calendar that
applies the same contact rules as the action plan, day by day."""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app import action_plan as ap

EVENT_SQL = '''
WITH ids AS (SELECT crm_customer_id FROM gold.crm_identity WHERE customer_id=?),
cases AS (SELECT case_id FROM gold.cases WHERE customer_id=?)
SELECT * FROM (
  SELECT h.contact_ts_utc AS ts, 'contact' AS kind, h.case_id AS case_id,
         coalesce(h.channel_v2,h.channel) AS channel, h.direction AS direction, h.outcome_code AS code, h.outcome_desc AS title,
         CASE WHEN h.payment_taken_flag THEN h.payment_amount END AS amount, h.rpc_flag AS rpc,
         coalesce(h.within_permitted_hours_flag,true)=false OR coalesce(h.stat_holiday_flag,false) AS outside_rules,
         h.contact_id AS ref, NULL AS detail
  FROM curated.contact_history h WHERE h.crm_customer_id IN (SELECT * FROM ids)
    AND coalesce(h.channel_v2,h.channel)<>'system' AND h.contact_ts_utc>? AND h.contact_ts_utc<=?
  UNION ALL
  SELECT p.ptp_created_ts, 'promise', p.case_id, p.ptp_channel, NULL, p.ptp_status, 'Promise to pay',
         p.ptp_amount, NULL, false, p.ptp_id, 'due ' || CAST(p.ptp_due_date AS VARCHAR)
  FROM curated.promises_to_pay p WHERE p.crm_customer_id IN (SELECT * FROM ids) AND p.ptp_created_ts>? AND p.ptp_created_ts<=?
  UNION ALL
  SELECT n.note_ts, 'note', n.case_id, NULL, NULL, n.note_type, 'Agent note', NULL, NULL, false, n.note_id, n.note_text
  FROM curated.agent_notes n WHERE n.crm_customer_id IN (SELECT * FROM ids) AND n.note_ts>? AND n.note_ts<=?
  UNION ALL
  SELECT o.offer_ts, 'offer', o.case_id, NULL, NULL, o.customer_response, 'Hardship offer ' || o.program_id,
         o.proposed_payment_amount, NULL, false, o.offer_id, coalesce(o.plan_status, o.decline_reason)
  FROM curated.offers o WHERE o.case_id IN (SELECT * FROM cases) AND o.offer_ts>? AND o.offer_ts<=?
  UNION ALL
  SELECT CAST(g.case_open_date AS TIMESTAMP), 'case', g.case_id, NULL, NULL, g.case_status, 'Case opened: ' || coalesce(g.case_open_reason,'collections'),
         g.entry_overdue, NULL, false, g.case_id, g.primary_product
  FROM gold.cases g WHERE g.customer_id=? AND g.case_open_date>CAST(? AS DATE)
) ORDER BY ts DESC LIMIT ?'''


def timeline(c, customer_id, days=365, limit=200):
    end = ap.AS_OF.replace(tzinfo=None)
    start = end - timedelta(days=days)
    rows = c.execute(EVENT_SQL, [customer_id, customer_id, start, end, start, end, start, end, start, end, customer_id, start, limit])
    keys = [d[0] for d in rows.description]
    events = [dict(zip(keys, r)) for r in rows.fetchall()]
    counts = {}
    for e in events:
        counts[e['kind']] = counts.get(e['kind'], 0) + 1
    return {'customer_id': customer_id, 'from': start.isoformat(), 'to': end.isoformat(), 'events': events, 'counts': counts,
            'outside_rules': sum(1 for e in events if e['outside_rules']),
            'note': 'Contacts, promises, notes, hardship offers and case openings from the source systems, newest first.'}


def calendar(c, customer_id, days=14):
    """Each day: when contact is allowed (customer-local) or why not, from the same rules as the plan."""
    ctx = ap.load(c, customer_id)
    if ctx is None:
        return None
    cust, case = ctx['customer'], ctx['case']
    cap = int(case.get('contact_cap_7d') or ap.DEFAULT_CAP_7D)
    tz = ZoneInfo(cust.get('time_zone') or ap.FALLBACK_TZ)
    holiday_names = ap.holidays(ap.AS_OF.date(), days=days + 7)
    first = ap.AS_OF.astimezone(tz).date()
    restricted = ap.build(ctx, 'not_established')['steps'][0]
    out = []
    for offset in range(days):
        day = first + timedelta(days=offset)
        start = max(ap.AS_OF, datetime.combine(day, time(0), tz).astimezone(timezone.utc))
        w = ap.contact_window(ctx['attempts'], cust.get('time_zone'), cust.get('permitted_call_start_local'), cust.get('permitted_call_end_local'),
                              cust.get('sunday_contact_permitted'), holiday_names, start, cap, horizon=0)
        if restricted['status'] == 'stop':
            entry = {'status': 'blocked', 'reason': restricted['title']}
        elif w.get('available'):
            entry = {'status': 'open', 'from_local': w['from_local'], 'until_local': w['until_local'],
                     'reason': 'Sunday hours' if day.weekday() == 6 else None}
            if w['from_local'] != ('13:00' if day.weekday() == 6 else (cust.get('permitted_call_start_local') or '07:00')[:5]) and offset:
                entry['reason'] = 'opens later: contact cap'
        else:
            reason = w['skipped'][0]['reason'] if w.get('skipped') else 'not allowed'
            entry = {'status': 'holiday' if 'holiday' in reason else 'cap' if 'attempts' in reason else 'closed', 'reason': reason}
        out.append({'date': day.isoformat(), 'day': ap._day(day), 'weekday': day.strftime('%a'), **entry})
    return {'customer_id': customer_id, 'time_zone': cust.get('time_zone') or 'unknown', 'cap_7d': cap,
            'attempts_last_7d': sum(1 for a in ctx['attempts'] if ap._utc(a) and ap._utc(a) > ap.AS_OF - timedelta(days=7)),
            'days': out, 'note': 'Planned contact must also respect consent and any new attempts; each new attempt counts toward the cap.'}
