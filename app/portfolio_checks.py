"""Portfolio-wide problems for the Overview page. Each number is one reviewed SQL
statement, returned with the number so a reviewer can rerun it."""
import threading
from datetime import timedelta

from app.settings import AS_OF

_NOW = AS_OF.replace(tzinfo=None)
_WEEK_AGO, _MONTH_AGO = _NOW - timedelta(days=7), _NOW - timedelta(days=30)
_TODAY = _NOW.date()
_DUE_END = _TODAY + timedelta(days=3)


def _d(day):
    return f"{day.day} {day.strftime('%b')}"

RESTRICTED = '''(coalesce(g.insolvency_hold_flag,false) OR coalesce(g.cease_contact_flag,false) OR coalesce(g.deceased_hold_flag,false)
  OR coalesce(c.bankruptcy_flag,false) OR coalesce(c.consumer_proposal_flag,false) OR coalesce(c.cease_communication_flag,false) OR coalesce(c.deceased_flag,false))'''
ATTEMPTS = "direction='outbound' AND coalesce(channel_v2,channel) IN ('call','sms','email','push')"

CHECKS = [
    {'id': 'hardship_no_plan', 'severity': 'high', 'unit': 'customers', 'policy': 'POL-COLL-004 v4.2 §4.2',
     'title': 'Customers in hardship with no plan yet',
     'definition': 'Distinct customers with an open case flagged for hardship, no hardship plan type, and no insolvency, cease-communication or deceased restriction.',
     'action': 'Offer an eligible hardship programme before any payment request.',
     'sql': f'''SELECT count(DISTINCT g.customer_id) FROM gold.cases g JOIN gold.customers c USING(customer_id)
WHERE g.outcome IS NULL AND g.hardship_flag AND g.hardship_plan_type IS NULL AND NOT {RESTRICTED}'''},
    {'id': 'over_contact_cap', 'severity': 'high', 'unit': 'cases', 'policy': 'POL-COLL-001 v3.0 §5.2',
     'title': 'Cases contacted more often than allowed',
     'definition': f'Open cases with more outbound calls or payment reminders (SMS, email, push) than their contact cap (3 by default) in the 7 days before the snapshot ({_d(_WEEK_AGO)} to {_d(_NOW)} {_NOW:%H:%M} UTC).',
     'action': 'Stop further attempts until the 7-day window clears; review dialer settings.',
     'sql': f'''SELECT count(*) FROM (SELECT h.case_id FROM curated.contact_history h JOIN gold.cases g ON g.case_id=h.case_id AND g.outcome IS NULL
WHERE h.{ATTEMPTS} AND h.contact_ts_utc>TIMESTAMP '{_WEEK_AGO}' AND h.contact_ts_utc<=TIMESTAMP '{_NOW}'
GROUP BY h.case_id,g.contact_cap_7d HAVING count(*)>coalesce(g.contact_cap_7d,3))'''},
    {'id': 'outside_permitted_hours', 'severity': 'high', 'unit': 'contacts', 'policy': 'POL-COLL-001 v3.0 §5.1',
     'title': 'Contacts outside permitted hours or on a holiday (last 30 days)',
     'definition': f"Outbound calls and reminders from {_d(_MONTH_AGO)} to {_d(_NOW)} {_NOW.year} that the source marks outside the customer's permitted local hours or on a statutory holiday.",
     'action': "Schedule by the customer's own time zone; block statutory holidays.",
     'sql': f'''SELECT count(*) FROM curated.contact_history WHERE {ATTEMPTS}
AND contact_ts_utc>TIMESTAMP '{_MONTH_AGO}' AND contact_ts_utc<=TIMESTAMP '{_NOW}'
AND (within_permitted_hours_flag=false OR stat_holiday_flag)'''},
    {'id': 'near_write_off', 'severity': 'medium', 'unit': 'cases', 'policy': 'collections_cases (charge-offs occur at 181 days past due)',
     'title': 'Cases close to write-off',
     'definition': 'Open cases at 150-180 days past due. Every charge-off recorded in collections_cases happened at 181 days past due.',
     'action': 'Prioritise contact and late-stage options before charge-off.',
     'sql': '''SELECT count(*) FROM gold.cases WHERE outcome IS NULL AND current_dpd BETWEEN 150 AND 180'''},
    {'id': 'promises_due_3d', 'severity': 'medium', 'unit': 'promises', 'policy': 'PRC-COLL-010 v2.1 §3.2',
     'title': 'Promises due in the next 3 days',
     'definition': f'Open promises to pay due from {_d(_TODAY)} to {_d(_DUE_END)} {_DUE_END.year} on open cases.',
     'action': 'Send one reminder each; do not ask for more money.',
     'sql': f'''SELECT count(*) FROM curated.promises_to_pay p JOIN gold.cases g ON g.case_id=p.case_id AND g.outcome IS NULL
WHERE p.ptp_status='open' AND p.ptp_due_date BETWEEN DATE '{_TODAY}' AND DATE '{_DUE_END}' '''},
    {'id': 'vulnerable_uncertified', 'severity': 'medium', 'unit': 'cases', 'policy': 'POL-COLL-004 v4.2 §4.5',
     'title': 'Vulnerable customers with an uncertified agent',
     'definition': 'Open cases flagged vulnerable (a safeguard, never a risk factor) assigned to an agent without vulnerable-customer certification.',
     'action': 'Reassign to a certified agent.',
     'sql': '''SELECT count(*) FROM gold.cases g JOIN curated.agents a ON a.agent_id=g.assigned_agent_id
WHERE g.outcome IS NULL AND g.vulnerable_customer_flag AND NOT a.vulnerable_customer_certified'''},
    {'id': 'insolvency_not_on_hold', 'severity': 'high', 'unit': 'cases', 'policy': 'POL-COLL-001 v3.0 §7.3',
     'title': 'Insolvency recorded but case not on hold',
     'definition': 'Open cases whose customer record shows bankruptcy or a consumer proposal while the case status is not insolvency_hold.',
     'action': 'Stop contact and move the case to insolvency hold.',
     'sql': '''SELECT count(*) FROM gold.cases g JOIN gold.customers c USING(customer_id)
WHERE g.outcome IS NULL AND (c.bankruptcy_flag OR c.consumer_proposal_flag) AND g.case_status<>'insolvency_hold\''''},
]

_cache = {}
_lock = threading.Lock()


def run(c, key):
    """Results are fixed for a snapshot, so they are computed once per database file version."""
    with _lock:
        if key not in _cache:
            items = []
            for check in CHECKS:
                items.append(check | {'value': int(c.execute(check['sql']).fetchone()[0])})
            _cache[key] = items
        return _cache[key]


# Money at stake behind the checks above. Source estimates are labelled as estimates.
VALUE = [
    {'id': 'write_off_exposure', 'title': 'Exposure on cases close to write-off', 'unit': 'CAD', 'kind': 'money',
     'definition': 'Total exposure (source total_exposure) on open cases at 150-180 days past due; the source expected-loss estimate is shown alongside.',
     'sql': '''SELECT round(sum(total_exposure),2), round(sum(expected_loss_est),2), round(sum(total_overdue),2) FROM gold.cases
WHERE outcome IS NULL AND current_dpd BETWEEN 150 AND 180'''},
    {'id': 'hardship_overdue', 'title': 'Overdue with customers in hardship and no plan', 'unit': 'CAD', 'kind': 'money',
     'definition': 'Overdue balance on open hardship-flagged cases without a hardship plan or a contact restriction.',
     'sql': f'''SELECT round(sum(g.total_overdue),2), NULL, count(DISTINCT g.customer_id) FROM gold.cases g JOIN gold.customers c USING(customer_id)
WHERE g.outcome IS NULL AND g.hardship_flag AND g.hardship_plan_type IS NULL AND NOT {RESTRICTED}'''},
    {'id': 'contact_spend', 'title': 'Outbound contact spend (last 30 days)', 'unit': 'CAD', 'kind': 'money',
     'definition': f'Recorded contact cost (contact_cost_cad) of outbound contacts from {_d(_MONTH_AGO)} to {_d(_NOW)}; second figure: contacts.',
     'sql': f'''SELECT round(sum(contact_cost_cad),2), count(*), NULL FROM curated.contact_history
WHERE direction='outbound' AND contact_ts_utc>TIMESTAMP '{_MONTH_AGO}' AND contact_ts_utc<=TIMESTAMP '{_NOW}' '''},
]


def value(c, key):
    with _lock:
        cache_key = ('value', key)
        if cache_key not in _cache:
            items = []
            for v in VALUE:
                a, b, d = c.execute(v['sql']).fetchone()
                items.append(v | {'value': float(a or 0), 'secondary': None if b is None else float(b), 'tertiary': None if d is None else float(d)})
            _cache[cache_key] = items
        return _cache[cache_key]
