"""Generate a nine-slide PDF from measured local reports and source facts.

Conventional PDF text, charts and a technical diagram only. No image generation.
Regenerate after the final benchmark run and inspect every rendered page.
"""
import argparse
import csv
import json
import sys
import xml.etree.ElementTree as ET
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.settings import ROOT, DATASET, QUALITY, MODEL_REPORT, DB, SNAPSHOT
import duckdb
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pypdf import PdfReader

NAVY = '#18343C'
TEAL = '#087F80'
MUTED = '#52676B'
PAPER = '#F8F9F6'
RED = '#A34335'
W, H = 960, 540


def generate(output):
    quality = json.loads(QUALITY.read_text(encoding='utf-8'))
    model = json.loads(MODEL_REPORT.read_text(encoding='utf-8'))
    parity = json.loads((ROOT / 'data/feature-parity.json').read_text(encoding='utf-8'))
    contract = json.loads((ROOT / 'data/c360-contract-validation.json').read_text(encoding='utf-8'))
    if parity.get('status') != 'pass' or parity.get('mismatch_count') != 0 or any(parity.get('key_coverage', {}).values()):
        raise ValueError('Feature parity/key checks have failures. Run scripts/check_feature_parity.py.')
    if not parity.get('sample_size') or len(parity.get('key_coverage', {})) != 4:
        raise ValueError('Feature parity report is missing sample or key coverage.')
    if contract.get('failed') or contract.get('skipped') or not contract.get('database_unchanged'):
        raise ValueError('C360 contract checks are incomplete or failed.')
    with duckdb.connect(str(DB), read_only=True) as db:
        demo = db.execute('SELECT s.open_cases,s.total_overdue,s.max_dpd,c.case_id,c.case_status,c.hardship_flag,c.insolvency_hold_flag,g.consumer_proposal_flag '
            'FROM gold.customer_summary s JOIN gold.cases c USING(customer_id) JOIN gold.customers g USING(customer_id) '
            'WHERE s.customer_id=? AND c.outcome IS NULL ORDER BY c.case_id', ['HAC-4447']).fetchall()
        portfolio_open, first_bucket = db.execute("SELECT count(*) FILTER(WHERE outcome IS NULL), count(*) FILTER(WHERE outcome IS NULL AND current_bucket='1-30') FROM curated.collections_cases").fetchone()
    if len(demo) != 1 or not all(demo[0][5:]):
        raise ValueError('HAC-4447 demo restrictions differ; recheck the customer and script.')
    open_cases, overdue, dpd, case_id, case_status, *_ = demo[0]
    with (ROOT / 'submission/benchmark_answers.csv').open(newline='',encoding='utf-8-sig') as stream:
        benchmark = list(csv.DictReader(stream))
    with (DATASET / 'data/benchmark_questions.csv').open(newline='',encoding='utf-8-sig') as stream:
        released = list(csv.DictReader(stream))
    validation_path = ROOT / 'data/dev-validation.json'
    if not validation_path.exists():
        raise ValueError('Run scripts/validate_dev.py before generating the pitch.')
    validation = json.loads(validation_path.read_text(encoding='utf-8'))
    numeric = [row for row in validation if 'numeric_reference_match' in row]
    matched = sum(row['numeric_reference_match'] for row in numeric)
    if matched != len(numeric) or any(row.get('execution_error') for row in validation):
        raise ValueError('Development validation has failures. Do not export passing claims.')
    status = json.loads((ROOT / 'data/benchmark-status.json').read_text(encoding='utf-8'))
    test_report=ROOT/'data/test-results.xml'
    if not test_report.exists():raise ValueError('Run pytest with --junitxml=data/test-results.xml before generating the pitch.')
    suites=ET.parse(test_report).getroot().findall('testsuite')
    totals={key:sum(int(s.get(key,0)) for s in suites) for key in ['tests','failures','errors','skipped']}
    if not suites or totals['failures'] or totals['errors']:raise ValueError('Tests have failures or missing results; do not export passing claims.')
    passed=totals['tests']-totals['skipped']
    if status.get('unresolved') or status.get('questions') != len(benchmark):
        raise ValueError('Benchmark output/status is unresolved or stale.')
    checks = {(row['table'], row['check']): row['failed_rows'] for row in quality['checks']}
    pdfmetrics.registerFont(TTFont('PitchSans', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'))
    pdfmetrics.registerFont(TTFont('PitchBold', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'))
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(output), pagesize=(W, H), pageCompression=1)
    c.setTitle('Collections Copilot - Adda Wale')
    c.setAuthor('Adda Wale')

    def text(x, top, width, value, size=19, color=NAVY, bold=False, maximum=None):
        style = ParagraphStyle('pitch', fontName='PitchBold' if bold else 'PitchSans',
                               fontSize=size, leading=size * 1.32, textColor=HexColor(color),
                               spaceAfter=0, spaceBefore=0)
        paragraph = Paragraph(value, style)
        _, height = paragraph.wrap(width, 1000)
        if maximum is not None and height > maximum:
            raise ValueError(f'Text exceeds allocated height: {value[:80]} ({height}>{maximum})')
        if top - height < 30 or x < 0 or x + width > W:
            raise ValueError(f'Text outside slide: {value[:80]}')
        paragraph.drawOn(c, x, top - height)
        return top - height

    def page(number, title, subtitle=None, source=None):
        c.setFillColor(HexColor(PAPER)); c.rect(0, 0, W, H, fill=1, stroke=0)
        text(52, 490, 856, escape(title), 32, bold=True, maximum=48)
        if subtitle:
            text(52, 436, 856, escape(subtitle), 17, MUTED, maximum=47)
        c.setFont('PitchSans', 11); c.setFillColor(HexColor(MUTED))
        c.drawRightString(908, 20, f'{number} / 9')
        if source:
            c.drawString(52, 20, source)

    def item(x, top, width, label, body, size=19):
        bottom = text(x, top, width, '<b>' + escape(label) + '</b>', size, bold=False)
        return text(x, bottom - 8, width, escape(body), size, MUTED)

    def connector(x1, y1, x2, y2):
        c.setStrokeColor(HexColor(TEAL)); c.setFillColor(HexColor(TEAL)); c.setLineWidth(2)
        c.line(x1, y1, x2, y2)
        path = c.beginPath(); path.moveTo(x2, y2)
        if x1 == x2:
            path.lineTo(x2 - 5, y2 + 9); path.lineTo(x2 + 5, y2 + 9)
        else:
            path.lineTo(x2 - 9, y2 + 5); path.lineTo(x2 - 9, y2 - 5)
        path.close(); c.drawPath(path, fill=1, stroke=0)

    # 1. Minimal cover.
    c.setFillColor(HexColor(NAVY)); c.rect(0, 0, W, H, fill=1, stroke=0)
    text(70, 466, 820, 'Collections<br/>Copilot', 50, '#FFFFFF', True, maximum=140)
    text(72, 298, 800, 'Customer context and evidence<br/>for collections review', 27, '#FFFFFF', maximum=78)
    text(72, 182, 810, 'Adda Wale', 22, '#6DDBD3', True)
    text(72, 135, 816, 'Prakhar Gupta, Aryan Shrivastava<br/>Krish Agarwal, Ved Maurya', 17, '#FFFFFF', maximum=50)
    text(72, 65, 810, 'CIBC Hackathon    4 October 2026', 14, '#BCD0D1')
    c.showPage()

    # 2. Business problem and operational use.
    page(2, 'The collections review workflow',
         'An agent needs customer facts and applicable policy before agreeing on the next step.')
    item(52, 362, 390, 'Information across systems',
         'Profiles, cards, loans, deposits and collections use different IDs and formats.')
    item(52, 238, 390, 'Relevant assistance',
         'A combined view shows accounts, cases, notes and optional call audio. Recommendations include supporting facts.')
    text(525, 364, 380, '1   Open the customer view<br/><br/>2   Inspect facts and sources<br/><br/>3   Generate a review brief<br/><br/>4   Record a supervisor decision', 21, maximum=280)
    text(52, 106, 856, 'Pilot measures: time per case, factual errors, missed hardship and supervisor corrections. Business improvement remains to be measured.', 17, MUTED, maximum=52)
    c.showPage()

    # 3. Native technical diagram, not a generated illustration.
    page(3, 'Four connected layers', 'Batch preparation supplies the local API and review workflow.')
    nodes = [
        (52, 282, '1  Data Product Factory', 'Normalize sources and match IDs<br/>DuckDB raw, curated and C360'),
        (528, 282, '2  Insight and NLP', 'Local SQL and cited policies<br/>Optional local Whisper audio evidence'),
        (52, 111, '3  Feature Store', 'Financial note cues and case context<br/>Shared offline and live definitions'),
        (528, 111, '4  Models and Decisioning', 'Classifier + explicit hardship rules<br/>Supervisor decision and SQLite audit'),
    ]
    for x, y, label, body in nodes:
        c.setStrokeColor(HexColor(TEAL)); c.setLineWidth(1.6)
        c.rect(x, y, 380, 120, fill=0, stroke=1)
        text(x + 18, y + 100, 344, escape(label), 20, bold=True, maximum=30)
        text(x + 18, y + 60, 344, body, 17, maximum=52)
    connector(432, 342, 528, 342)
    connector(242, 282, 242, 231)
    connector(432, 171, 528, 171)
    text(52, 83, 856, 'Next.js interface and FastAPI backend. DuckDB serves customer data. SQLite stores sessions and reviews.', 17, MUTED, maximum=47)
    c.showPage()

    # 4. Measured pipeline volume and issue handling.
    page(4, 'Data product and measured quality',
         'The pipeline preserves source records and reports issues before linking customer accounts.',
         'Sources: measured data/quality.json and docs/data-quality-report.md')
    for x, value, label in [(52, str(len(quality['raw_counts'])), 'source tables'),
                            (354, f"{sum(quality['raw_counts'].values()) / 1_000_000:.1f}m", 'raw source rows'),
                            (660, f"{quality['identity']['golden_customers']:,}", 'golden customer records')]:
        text(x, 365, 280, value, 34, TEAL, True, maximum=50)
        text(x, 313, 280, label, 17, MUTED)
    text(52, 264, 300, '<b>Measured issue</b>', 17)
    text(395, 264, 125, '<b>Rows</b>', 17)
    text(570, 264, 335, '<b>Handling</b>', 17)
    for top, label, count, handling in [
        (222, 'Missing card DPD', checks[('card_accounts', 'dpd_missing')], 'Keep null and report denominator'),
        (169, 'Orphan contact case refs', checks[('contact_history', 'case_id_referential_integrity')], 'Retain source and flag missing link'),
        (116, 'Case bucket / DPD conflict', checks[('collections_cases', 'current_bucket_disagrees_with_dpd')], 'Retain both and report discrepancy'),
    ]:
        text(52, top, 310, label, 17)
        text(395, top, 125, f'{count:,}', 17, TEAL, True)
        text(570, top, 335, handling, 16, MUTED, maximum=43)
    text(52, 62, 856, 'Uncertain source links stay out of linked balances. Identity precision remains unmeasured.', 14, MUTED, maximum=25)
    c.showPage()

    # 5. Concrete outputs, grounded in verified development examples.
    page(5, 'Answers with inspectable evidence',
         'Local SQL calculates results. Optional Gemini selects validated plans and exact source evidence.',
         'Sources: curated collections cases and POL-COLL-001 v3.0 section 7.3')
    text(52, 355, 410, 'Open collections cases<br/>28 September 2026', 24, bold=True, maximum=75)
    text(52, 258, 410, f'{portfolio_open:,}', 54, TEAL, True)
    text(52, 181, 410, f'{first_bucket:,} in the 1-30 DPD bucket<br/>SQL and result rows remain inspectable', 18, MUTED, maximum=64)
    text(528, 355, 380, 'Consumer proposal policy', 24, bold=True, maximum=75)
    text(528, 270, 380, 'All collection<br/>contact stops', 30, TEAL, True, maximum=85)
    text(528, 170, 380, 'From the filing date<br/>POL-COLL-001 v3.0 section 7.3', 18, MUTED, maximum=66)
    text(52, 96, 856, 'Protected-attribute ranking, bulk personal-data exports and unrelated requests receive an explicit refusal.', 18, maximum=52)
    c.showPage()

    # 6. Actual model metrics, using native chart primitives.
    page(6, 'Financial hardship review model',
         'Class-balanced logistic regression on six financial text cues from English and French notes.',
         'Source: docs/model-evaluation.md. Metrics use 126 customer-grouped heldout notes.')
    for top, label, value in [(358, 'Precision', model['heldout']['precision']),
                              (279, 'Recall', model['heldout']['recall']),
                              (200, 'F1', model['heldout']['f1'])]:
        text(52, top, 145, label, 20)
        c.setFillColor(HexColor('#DEEAE6')); c.rect(210, top - 31, 280, 24, fill=1, stroke=0)
        c.setFillColor(HexColor(TEAL)); c.rect(210, top - 31, 280 * value, 24, fill=1, stroke=0)
        text(510, top, 95, f'{value * 100:.1f}%', 20, TEAL, True)
    item(643, 358, 265, 'Training boundary',
         f"{model['train_rows']} training notes, {model['test_rows']} test notes. Split by resolved customer ID.", 18)
    item(643, 224, 265, 'Model inputs',
         'Six financial cues. Protected fields and raw text are excluded.', 18)
    matrix = model['heldout']['confusion_matrix']
    text(52, 105, 856,
         f"The model missed {matrix[1][0]} of {matrix[1][0] + matrix[1][1]} positive test labels. A low score cannot establish that hardship is absent. Supervisor review remains essential.",
         18, RED, maximum=66)
    c.showPage()

    # 7. Human decision point and backend controls.
    page(7, 'HAC-4447: contact hold takes priority',
         'A concrete example of source restrictions overriding hardship and model cues.',
         f'Sources: C360 snapshot {SNAPSHOT}, {case_id}, POL-COLL-001 v3.0 section 7.3')
    item(52, 358, 410, 'Customer and case facts',
         f'{open_cases} open card case. CAD {overdue:,.2f} overdue, {dpd} days past due. Case {case_id} is in {case_status}.', 18)
    item(52, 216, 410, 'Historical audio evidence',
         '53-second supplied call. Local Whisper detects a payment difficulty candidate. Words and speakers need human review.', 18)
    item(538, 358, 370, 'Recorded restriction',
         'Consumer proposal and insolvency hold override recorded hardship. The brief remains pending.', 18)
    item(538, 234, 370, 'Internal note for supervisor review',
         'Do not contact this customer. All collection contact stops from the filing date under section 7.3.', 18)
    text(52, 85, 856, 'Editing the internal note preserves the hold and records an audit event. Approval does not contact the customer.', 17, maximum=48)
    c.showPage()

    # 8. Scope of evidence and known limitations.
    page(8, 'Verification evidence and current limits',
         'Local checks support the prototype. Hidden answers and production performance remain unverified.',
         'Sources: build status, development validation, feature report and accuracy/readiness audit')
    rows = [
        ('Numeric development references', f'{matched}/{len(numeric)} match within tolerance'),
        ('Generated benchmark rows', f'{len(benchmark)} rows, {sum(r["refused"] == "true" for r in benchmark)} refusals'),
        ('Automated application tests', f"{passed} passed"),
        ('C360 contract and availability', f'{contract["passed"]} checks, {contract["rows"]:,} rows'),
        ('Stored / live feature values', f'{parity["sample_size"]:,} customers, {parity["mismatch_count"]} mismatches'),
        ('Full-table customer key coverage', f'{parity["stored_rows"]:,} rows checked'),
        ('Voice integrity and C360 linkage', '2,000 verified / 1,944 linked'),
    ]
    for i, (label, value) in enumerate(rows):
        top = 369 - i * 38
        text(52, top, 430, escape(label), 17, maximum=26)
        text(530, top, 378, escape(value), 17, TEAL, maximum=26)
    extra = len(benchmark) - len(released)
    extra_text = f'{extra} extra question rows included.' if extra else 'The 15 extra questions are pending the 19:00 release.'
    text(52, 83, 856, escape(extra_text) + ' Feature values are sampled, while key coverage uses the full store.<br/>Limits: ASR, live provider, eligibility and production capacity need broader validation.',
         14, RED, maximum=46)
    c.showPage()

    # 9. Implementation path and accurate AI disclosure.
    page(9, 'Company pilot and next implementation steps',
         'A real deployment requires approved accuracy targets and representative customer-data validation.')
    item(52, 357, 410, 'Accuracy and relevant support',
         'Validate unseen questions, improve hardship recall and check programme eligibility against policy.', 19)
    item(52, 205, 410, 'Operational measures',
         'Track factual errors, missed hardship, supervisor corrections and time per case.', 19)
    item(538, 357, 370, 'Shared serving and fresh data',
         'Add incremental ingestion, shared persistent review storage, backups and measured concurrent-user capacity.', 19)
    item(538, 205, 370, 'Controlled rollout',
         'Integrate company login and monitor data quality, feature versions and model drift.', 19)
    text(52, 84, 856,
         '<b>Development:</b> Codex implementation/verification; Claude Opus 5.5 reviews, frontend and extractive summaries. <b>Runtime:</b> local classifier/SQL/Whisper; optional Gemini, live verification pending.',
         14, MUTED, maximum=42)
    c.showPage(); c.save()
    reader = PdfReader(output)
    if len(reader.pages) != 9 or any(not p.extract_text().strip() for p in reader.pages):
        raise ValueError('Pitch export has missing pages or text.')
    print(json.dumps({'pdf': str(output), 'slides': len(reader.pages),
                      'benchmark_rows': len(benchmark), 'extra_rows': len(benchmark) - len(released)}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT.parent / 'deliverables/AddaWale-Presentation.pdf')
    args = parser.parse_args()
    generate(args.output)
