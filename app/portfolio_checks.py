"""Portfolio-wide problems for the Overview page. Each number is one reviewed SQL
statement, returned with the number so a reviewer can rerun it."""
import threading

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
     'definition': 'Open cases with 4 or more outbound calls or payment reminders (SMS, email, push) in the 7 days before the snapshot (21 Sep 07:00 to 28 Sep 07:00 UTC). The cap is 3 per rolling 7 days.',
     'action': 'Stop further attempts until the 7-day window clears; review dialer settings.',
     'sql': f'''SELECT count(*) FROM (SELECT h.case_id FROM curated.contact_history h JOIN gold.cases g ON g.case_id=h.case_id AND g.outcome IS NULL
WHERE h.{ATTEMPTS} AND h.contact_ts_utc>TIMESTAMP '2026-09-21 07:00' AND h.contact_ts_utc<=TIMESTAMP '2026-09-28 07:00'
GROUP BY 1 HAVING count(*)>3)'''},
    {'id': 'outside_permitted_hours', 'severity': 'high', 'unit': 'contacts', 'policy': 'POL-COLL-001 v3.0 §5.1',
     'title': 'Contacts outside permitted hours or on a holiday (last 30 days)',
     'definition': "Outbound calls and reminders from 29 Aug to 28 Sep 2026 that the source marks outside the customer's permitted local hours or on a statutory holiday.",
     'action': "Schedule by the customer's own time zone; block statutory holidays.",
     'sql': f'''SELECT count(*) FROM curated.contact_history WHERE {ATTEMPTS}
AND contact_ts_utc>TIMESTAMP '2026-08-29 07:00' AND contact_ts_utc<=TIMESTAMP '2026-09-28 07:00'
AND (within_permitted_hours_flag=false OR stat_holiday_flag)'''},
    {'id': 'near_write_off', 'severity': 'medium', 'unit': 'cases', 'policy': 'collections_cases (charge-offs occur at 181 days past due)',
     'title': 'Cases close to write-off',
     'definition': 'Open cases at 150-180 days past due. Every charge-off recorded in collections_cases happened at 181 days past due.',
     'action': 'Prioritise contact and late-stage options before charge-off.',
     'sql': '''SELECT count(*) FROM gold.cases WHERE outcome IS NULL AND current_dpd BETWEEN 150 AND 180'''},
    {'id': 'promises_due_3d', 'severity': 'medium', 'unit': 'promises', 'policy': 'PRC-COLL-010 v2.1 §3.2',
     'title': 'Promises due in the next 3 days',
     'definition': 'Open promises to pay due from 28 Sep to 1 Oct 2026 on open cases.',
     'action': 'Send one reminder each; do not ask for more money.',
     'sql': '''SELECT count(*) FROM curated.promises_to_pay p JOIN gold.cases g ON g.case_id=p.case_id AND g.outcome IS NULL
WHERE p.ptp_status='open' AND p.ptp_due_date BETWEEN DATE '2026-09-28' AND DATE '2026-10-01\''''},
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
            _cache.clear()
            _cache[key] = items
        return _cache[key]
