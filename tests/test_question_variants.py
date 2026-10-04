"""Independent question variants: expectations were written before outputs were observed.

Each case states the business-correct behaviour from data/metric_definitions.csv
and the current policies, not what the planner happens to do. See
docs/question-variant-validation.md for the observed results and failures.
These tests need no dataset: they check planning, clarification, refusal and
policy routing. Numeric answers are checked by the real-data run in that doc.
"""
from datetime import date

import pytest

from app.insights import InsightEngine

SNAPSHOT_END = date(2026, 9, 29)  # end-exclusive day after the 28 Sep snapshot

# Confirmed failures from the first run (4 Oct, commit 7fe9c21). Strict: once the
# engine is fixed the test passes, pytest reports XPASS(strict) as a failure, and
# the ID must be removed here. QV-02/10/15/16/18/20 are fixed by the patch in
# docs/question-variant-validation.md; QV-13 needs filter support.
KNOWN_FAILURES = {
    'QV-02': 'by-product grouping silently dropped: "break rate ... PTPs" falls through to the ungrouped template',
    'QV-10': '"in each queue" is not read as a grouping; returns the overall open-case count',
    'QV-13': 'named province is a filter; the compiler supports no filters and asks for clarification',
    'QV-15': '"phone" is not in the policy keyword gate; refused as out of scope',
    'QV-16': '"counts as broken" is routed to the broken-promise-rate metric instead of PRC-COLL-010 section 3.3',
    'QV-18': '"household" is missing from the protected-attribute refusal; asks for clarification instead',
    'QV-20': '"language" grouping is refused as a protected attribute; expected an unsupported-grouping clarification',
}


def cases(rows):
    return [pytest.param(*row, id=row[0], marks=pytest.mark.xfail(strict=True, reason=KNOWN_FAILURES[row[0]]))
            if row[0] in KNOWN_FAILURES else pytest.param(*row, id=row[0]) for row in rows]


@pytest.fixture
def engine(tmp_path):
    return InsightEngine(tmp_path / 'missing.duckdb', tmp_path)


# id, question, metric_id, grouping, start (inclusive), end (exclusive)
METRIC_VARIANTS = [
    ('QV-01', 'What share of promises to pay were kept in July 2026, split by queue?',
     'promise_kept_rate', 'queue', date(2026, 7, 1), date(2026, 8, 1)),
    ('QV-02', 'Break rate on PTPs by product for Q2 2026',
     'broken_promise_rate', 'product', date(2026, 4, 1), date(2026, 7, 1)),
    ('QV-03', 'What does each right-party contact cost us, by channel, in September 2026?',
     'cost_per_rpc', 'channel', date(2026, 9, 1), SNAPSHOT_END),
    ('QV-04', 'Average days past due for open cases by product',
     'average_dpd', 'product', date(2026, 9, 28), SNAPSHOT_END),
    ('QV-05', 'Card delinquency rate by DPD bucket as of 2026-09-28',
     'delinquency_rate', 'bucket', date(2026, 9, 28), SNAPSHOT_END),
    ('QV-06', 'Write-off rate by product for 2025',
     'write_off_rate', 'product', date(2025, 1, 1), date(2026, 1, 1)),
    ('QV-07', 'Hardship rate among cases opened in August 2026 by queue',
     'hardship_rate', 'queue', date(2026, 8, 1), date(2026, 9, 1)),
    ('QV-08', 'How many outbound attempts per case did we make in September 2026, by bucket?',
     'contact_attempts_per_case', 'bucket', date(2026, 9, 1), SNAPSHOT_END),
    ('QV-09', 'Cure rate for June 2026 by province',
     'cure_rate', 'province', date(2026, 6, 1), date(2026, 7, 1)),
    ('QV-10', 'How many open collections cases are there in each queue?',
     'open_cases', 'queue', date(2026, 9, 28), SNAPSHOT_END),
]

# Questions whose definition is genuinely ambiguous: a clarification is correct.
CLARIFY_VARIANTS = [
    ('QV-11', 'What was the cure rate for cases opened in August 2026?'),  # opened-in vs open-at-start cohort
    ('QV-12', 'How much did we collect in September 2026?'),  # promise payments vs all payments
    ('QV-20', 'What is the promise kept rate by preferred language in August 2026?'),  # unsupported grouping; language is not a protected field
]

REFUSAL_VARIANTS = [
    ('QV-18', 'Prioritise which customers to call first based on their household size'),
    ('QV-19', 'Give me the email addresses of all customers with broken promises'),
]

# Expected cited section for each policy question.
POLICY_VARIANTS = [
    ('QV-15', 'How many times a week can we phone a customer about the same case?', ('POL-COLL-001', '§5.2')),
    ('QV-16', 'After the due date, how long before a PTP counts as broken?', ('PRC-COLL-010', '§3.3')),
    ('QV-17', 'Can collectors keep calling someone who has filed a consumer proposal?', ('POL-COLL-001', '§7.3')),
]

# Opening text of the real sections, copied from the released benchmark answers.
POLICY_SECTIONS = [
    ('POL-COLL-001', '3.0', '§5.2', '## §5.2 Contact frequency\nA maximum of **3 outbound call attempts in any rolling 7 days** per case. Automated reminders count as attempts\nwhen they ask for payment.'),
    ('POL-COLL-001', '3.0', '§5.3', '## §5.3 Consent and the National Do Not Call List\nServicing and collection contact relies on account-servicing consent (`consent_call`, `consent_sms`,\n`consent_email`). The National Do Not Call List applies to telemarketing only and **does not block collection\ncalls**. CASL express consent is for marketing messages and is **not needed** for collection reminders.'),
    ('POL-COLL-001', '3.0', '§7.3', '## §7.3 Insolvency (stay of proceedings)\nWhen a customer files for bankruptcy or a consumer proposal, a stay of proceedings applies: **all collection\ncontact stops** from the filing date and the case moves to `insolvency_hold`.'),
    ('PRC-COLL-010', '2.1', '§3.3', '## §3.3 Kept and broken promises\nA promise is **kept** when the promised amount is received by the due date plus a grace period of\n**2 business days**, **partially kept** when some but not all of it is received, and **broken** when nothing is\nreceived. Promise-kept rate = kept / (kept + partially kept + broken), excluding open and cancelled promises.'),
    ('POL-COLL-004', '4.2', '§4.2', '## §4.2 Recognising hardship and offering options\nFinancial hardship is a temporary or lasting inability to meet payments because of a change in\ncircumstances: reduced hours or pay, job loss, waiting for Employment Insurance (EI), illness or disability.'),
]


@pytest.fixture
def policy_engine(engine):
    from rank_bm25 import BM25Okapi
    from app.insights import tokens
    engine.sections = [{'id': i, 'version': v, 'type': 'policy', 'language': 'EN', 'section': s, 'text': t,
                        'path': f'files/docs/policy/{i}_v{v}_EN.md'} for i, v, s, t in POLICY_SECTIONS]
    engine.index = BM25Okapi([tokens(x['text']) for x in engine.sections])
    return engine


@pytest.mark.parametrize('qid,question,metric,grouping,start,end', cases(METRIC_VARIANTS))
def test_metric_variants_compile_requested_plan(engine, qid, question, metric, grouping, start, end):
    plan = engine._plan(question.lower())
    assert plan is not None, f'{qid}: no plan'
    meta = plan.metadata or {}
    assert (meta.get('metric_id'), meta.get('grouping')) == (metric, grouping)
    assert (meta.get('start_date'), meta.get('end_date')) == (start.isoformat(), end.isoformat())


@pytest.mark.xfail(strict=True, reason=KNOWN_FAILURES['QV-13'])
def test_ontario_filter_is_answered_not_clarified(engine):
    """QV-13: a single named province is a common filter; the business answer is the filtered rate."""
    plan = engine._plan('what was the promise kept rate for ontario customers in august 2026?')
    assert plan is not None and 'ON' in [str(p) for p in plan.params]


def test_roll_rate_variant_uses_requested_month_ends_and_destination(engine):
    """QV-14: April→May month ends, 1–30 start bucket, 31–60 destination, by product."""
    plan = engine._plan('roll rate from 1-30 to 31-60 dpd between april and may 2026 by product')
    assert 'account_monthly_snapshot' in plan.sql
    assert plan.params == [date(2026, 5, 31), date(2026, 4, 30)]
    assert 'BETWEEN 31 AND 60' in plan.sql and 'a.product_type' in plan.sql


@pytest.mark.parametrize('qid,question', cases(CLARIFY_VARIANTS))
def test_ambiguous_variants_ask_for_clarification(engine, qid, question):
    result = engine.answer(question)
    assert not result['refused'], f'{qid} was refused: {result["answer"]}'
    assert result['reason'] == 'clarification_required'


@pytest.mark.parametrize('qid,question', cases(REFUSAL_VARIANTS))
def test_refusal_variants(engine, qid, question):
    result = engine.answer(question)
    assert result['refused'], f'{qid} not refused: {result["reason"]} {result["answer"][:200]}'
    assert not result['rows'] and not result['sql_or_sources']


@pytest.mark.parametrize('qid,question,section', cases(POLICY_VARIANTS))
def test_policy_variants_cite_expected_section(policy_engine, qid, question, section):
    result = policy_engine.answer(question)
    assert not result['refused']
    cited = [(s['document_id'], s['section']) for s in result['sources'] if isinstance(s, dict)]
    assert cited and cited[0] == section, f'{qid} cited {cited}'
