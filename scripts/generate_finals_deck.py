"""Generate the 16-slide finals deck from measured local results.

Numbers come from the database, the reports in data/ and the pinned demo customers.
Screenshots are real application renders from scripts/e2e_finals.mjs (OUT=data/finals-shots).
Conventional PDF text, shapes and screenshots only; no image generation.
Run after: pytest --junitxml=data/test-results.xml, scripts/validate_dev.py,
scripts/evaluate_hardship_cv.py, scripts/compare_llm_classifier.py and the browser check.
The LLM comparison is read from data/llm-comparison.json (override with LLM_COMPARISON=path).
"""
import argparse
import csv
import json
import os
import statistics
import sys
import time
import xml.etree.ElementTree as ET
from datetime import timedelta
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import duckdb
from PIL import Image
from pypdf import PdfReader
from reportlab.lib.colors import HexColor
from reportlab.lib.fonts import addMapping
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

from app import action_plan, call_session, portfolio_checks, work_queue
from app.settings import AS_OF, DB, QUALITY, ROOT, SNAPSHOT

NAVY, TEAL, MUTED, PAPER, RED, CORAL, LINE = '#18343C', '#087F80', '#52676B', '#F8F9F6', '#A34335', '#D9614A', '#CCDCD8'
W, H = 960, 540
SLIDES = 16
SHOTS = ROOT / 'data/finals-shots'
DOCS = ROOT / 'docs'
LLM_COMPARISON = Path(os.environ.get('LLM_COMPARISON', ROOT / 'data/llm-comparison.json'))


def load_facts():
    facts = {}
    with duckdb.connect(str(DB), read_only=True) as c:
        facts['checks'] = {i['id']: i for i in portfolio_checks.run(c, 'deck')}
        facts['open_cases'] = c.execute('SELECT count(*) FROM curated.collections_cases WHERE outcome IS NULL').fetchone()[0]
        facts['agents'] = c.execute('SELECT count(DISTINCT assigned_agent_id) FROM gold.cases WHERE outcome IS NULL AND assigned_agent_id IS NOT NULL').fetchone()[0]
        facts['documents'] = c.execute('SELECT count(*) FROM curated.reference_documents').fetchone()[0]
        facts['sav'] = action_plan.for_customer(c, 'SAV-6847', 'not_established')
        facts['jev'] = action_plan.for_customer(c, 'JEV-1240', 'recorded')
        facts['queue'] = work_queue.build(c, 'AG-7514')
        facts['value'] = {i['id']: i for i in portfolio_checks.value(c, 'deck')}
        facts['call'] = call_session.session(call_session.load(c, 'JEV-1240'), 'recorded', {
            'reached': 'customer', 'recording_notice': True, 'identity_verified': True,
            'hardship': {'stated': True, 'reason': 'job_loss'}, 'programme': 'HP-LOAN-RED3',
            'promise': {'amount': 315.86, 'date': '2026-10-15'}, 'income': {'monthly_income': 2400, 'monthly_expenses': 1900}})
        facts['blocked'] = call_session.session(call_session.load(c, 'HAC-4447'), 'not_established', {})
        # Data volumes and speeds for the architecture slide, measured at export.
        facts['volumes'] = {name: c.execute(f'SELECT count(*) FROM curated.{name}').fetchone()[0]
                            for name in ['customers', 'contact_history', 'agent_notes', 'collections_cases']}
        scan = []
        for _ in range(5):
            started = time.perf_counter()
            c.execute(f"SELECT count(*) FROM curated.contact_history WHERE direction='outbound' AND contact_ts_utc > TIMESTAMP '{(AS_OF.replace(tzinfo=None) - timedelta(days=30)):%Y-%m-%d %H:%M:%S}'").fetchone()
            scan.append((time.perf_counter() - started) * 1000)
        facts['scan_ms'] = statistics.median(scan)
        call_times = []
        for _ in range(5):
            started = time.perf_counter()
            call_session.session(call_session.load(c, 'JEV-1240'), 'recorded', {'reached': 'customer', 'recording_notice': True, 'identity_verified': True,
                                                                               'hardship': {'stated': True, 'reason': 'job_loss'}})
            call_times.append(time.perf_counter() - started)
        facts['call_seconds'] = statistics.median(call_times)
    red3 = next(o for o in facts['call']['calculator']['options'] if o['program_id'] == 'HP-LOAN-RED3')
    if (red3['payment_now'], red3['payment_during']) != (631.72, 315.86) or facts['blocked']['stage'] != 'blocked':
        raise ValueError('Call Mode demo example changed; recheck JEV-1240 and HAC-4447.')
    plans = json.loads((ROOT / 'data/plans-report.json').read_text(encoding='utf-8'))
    if plans['snapshot_date'] != SNAPSHOT or plans['errors']:
        raise ValueError('Batch report is stale or has errors; rerun scripts/batch_plans.py.')
    facts['plans'] = plans
    sav = facts['sav']['contact_window']
    if not sav['date'] == '2026-10-01' or not any('holiday' in s['reason'] for s in sav['skipped']):
        raise ValueError('SAV-6847 no longer shows the cap + holiday example; recheck the demo customers.')
    if not {'HP-LOAN-RED3', 'HP-LOAN-EXT'} <= {p['program_id'] for p in facts['jev']['programmes'] if p['status'] == 'likely_eligible'}:
        raise ValueError('JEV-1240 programme example changed; recheck the demo customers.')
    facts['quality'] = json.loads(QUALITY.read_text(encoding='utf-8'))
    cv = json.loads((ROOT / 'data/hardship-cv-report.json').read_text(encoding='utf-8'))['cue_sets']
    facts['hardship'] = {k: cv[k] for k in ['v1_current', 'c360-financial-v2']}
    dev = json.loads((ROOT / 'data/dev-validation.json').read_text(encoding='utf-8'))
    numeric = [r for r in dev if 'numeric_reference_match' in r]
    if sum(r['numeric_reference_match'] for r in numeric) != len(numeric) or any(r.get('execution_error') for r in dev):
        raise ValueError('Development validation has failures. Do not export passing claims.')
    facts['dev'] = (sum(r['numeric_reference_match'] for r in numeric), len(numeric))
    with (ROOT / 'submission/benchmark_answers.csv').open(newline='', encoding='utf-8-sig') as f:
        facts['benchmark'] = list(csv.DictReader(f))
    suites = ET.parse(ROOT / 'data/test-results.xml').getroot().findall('testsuite')
    totals = {k: sum(int(s.get(k, 0)) for s in suites) for k in ['tests', 'failures', 'errors', 'skipped']}
    if not suites or totals['failures'] or totals['errors']:
        raise ValueError('Tests have failures or missing results; do not export passing claims.')
    facts['tests'] = totals['tests'] - totals['skipped']
    e2e = json.loads((SHOTS / 'results.json').read_text(encoding='utf-8'))
    if not all(r['ok'] for r in e2e['results']) or e2e['errors']:
        raise ValueError('Browser check has failures; rerun scripts/e2e_finals.mjs.')
    facts['e2e'] = len(e2e['results'])
    # Hardship detector vs an LLM on the same held-out notes (scripts/compare_llm_classifier.py).
    llm = json.loads(LLM_COMPARISON.read_text(encoding='utf-8'))
    if llm['gemini'].get('unreadable_answers') is None or not llm.get('notes'):
        raise ValueError(f'{LLM_COMPARISON} is incomplete; rerun scripts/compare_llm_classifier.py.')
    facts['llm'] = llm
    # Why Gemini's false alarms happened, counted from the notes themselves: the release tags
    # vulnerable customers "cust vulnerable - financial hardship" (POL-COLL-004 s4.5), not hardship.
    fp_ids = llm.get('errors_by_detector', {}).get('gemini', {}).get('false_positives', [])
    with duckdb.connect(str(DB), read_only=True) as con:
        fp_text = [r[0] for r in con.execute('SELECT note_text FROM curated.agent_notes WHERE note_id IN (' + ','.join('?' for _ in fp_ids) + ')', fp_ids).fetchall()] if fp_ids else []
    facts['llm_fp_vulnerability_tag'] = sum('vulnerable - financial hardship' in t.lower() for t in fp_text)
    # Local end-to-end cost on the same notes: cue extraction plus model scoring.
    sys.path.insert(0, str(ROOT / 'scripts'))
    import joblib
    from compare_llm_classifier import heldout
    from app.features import TEXT_FEATURES, text_features
    notes = heldout()[0]
    bundle = joblib.load(ROOT / 'data/hardship-model.joblib')
    model = bundle['model'] if isinstance(bundle, dict) else bundle
    runs = []
    for _ in range(5):
        started = time.perf_counter()
        model.predict_proba([[text_features(n)[k] for k in TEXT_FEATURES] for n in notes])
        runs.append((time.perf_counter() - started) * 1000 / len(notes))
    facts['local_ms_per_note'] = statistics.median(runs)
    return facts


def generate(output):
    f = load_facts()
    pdfmetrics.registerFont(TTFont('DeckSans', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'))
    pdfmetrics.registerFont(TTFont('DeckBold', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'))
    pdfmetrics.registerFont(TTFont('DeckMono', '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf'))
    for italic in (0, 1):
        addMapping('DeckSans', 0, italic, 'DeckSans'); addMapping('DeckSans', 1, italic, 'DeckBold')
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(output), pagesize=(W, H), pageCompression=1)
    c.setTitle('Collections Copilot - Adda Wale - Finals')
    c.setAuthor('Adda Wale')

    def text(x, top, width, value, size=18, color=NAVY, bold=False, maximum=None, font=None):
        style = ParagraphStyle('deck', fontName=font or ('DeckBold' if bold else 'DeckSans'), fontSize=size,
                               leading=size * 1.32, textColor=HexColor(color))
        p = Paragraph(value, style)
        _, height = p.wrap(width, 1000)
        if maximum is not None and height > maximum:
            raise ValueError(f'Text exceeds allocated height: {value[:80]} ({height:.0f}>{maximum})')
        if top - height < 28 or x < 0 or x + width > W:
            raise ValueError(f'Text outside slide: {value[:80]}')
        p.drawOn(c, x, top - height)
        return top - height

    counter = [1]  # the cover is slide 1

    def page(title, subtitle=None, source=None):
        counter[0] += 1
        number = counter[0]
        c.setFillColor(HexColor(PAPER)); c.rect(0, 0, W, H, fill=1, stroke=0)
        text(48, 500, 864, escape(title), 29, bold=True, maximum=44)
        if subtitle:
            text(48, 452, 864, escape(subtitle), 16, MUTED, maximum=44)
        c.setFont('DeckSans', 10); c.setFillColor(HexColor(MUTED))
        c.drawRightString(912, 16, f'{number} / {SLIDES}')
        if source:
            c.drawString(48, 16, source)

    def shot(name, x, y, width, height, top_fraction=0.0, left_fraction=0.0):
        """Draw a real app screenshot, cropped to the box aspect from the top (and optionally the left)."""
        img = Image.open(SHOTS / name).convert('RGB')
        img = img.crop((int(img.width * left_fraction), 0, img.width, img.height))
        iw, ih = img.size
        want = iw * height / width
        top = int(ih * top_fraction)
        img = img.crop((0, top, iw, min(ih, top + int(want))))
        scale = min(width / img.width, height / img.height)
        dw, dh = img.width * scale, img.height * scale
        c.setStrokeColor(HexColor(LINE)); c.setLineWidth(1)
        c.drawImage(ImageReader(img), x, y + height - dh, dw, dh)
        c.rect(x, y + height - dh, dw, dh, fill=0, stroke=1)

    def picture(path, x, y, width, height):
        """Draw a whole image (no crop), scaled to fit the box and centred in it."""
        img = Image.open(path).convert('RGB')
        scale = min(width / img.width, height / img.height)
        dw, dh = img.width * scale, img.height * scale
        c.drawImage(ImageReader(img), x + (width - dw) / 2, y + (height - dh) / 2, dw, dh)

    def box(x, y, w, h, title, body, dashed=False, accent=False, size=12.5, body_size=10.5):
        c.setFillColor(HexColor('#E6F2F0' if accent else '#FFFFFF')); c.setStrokeColor(HexColor(TEAL if accent else MUTED if dashed else LINE))
        c.setLineWidth(1.6 if accent else 1.1); c.setDash(4, 3) if dashed else c.setDash()
        c.roundRect(x, y, w, h, 7, fill=1, stroke=1); c.setDash()
        top = text(x + 10, y + h - 9, w - 20, f'<b>{escape(title)}</b>', size, maximum=size * 2.8)
        text(x + 10, top - 3, w - 20, escape(body), body_size, MUTED, maximum=h - 9 - (y + h - 9 - top) - 6)

    def arrow(x1, y1, x2, y2, dashed=False):
        c.setStrokeColor(HexColor(MUTED)); c.setFillColor(HexColor(MUTED)); c.setLineWidth(1.2)
        c.setDash(4, 3) if dashed else c.setDash()
        c.line(x1, y1, x2, y2); c.setDash()
        import math
        a = math.atan2(y2 - y1, x2 - x1)
        p = c.beginPath(); p.moveTo(x2, y2)
        p.lineTo(x2 - 7 * math.cos(a - 0.45), y2 - 7 * math.sin(a - 0.45)); p.lineTo(x2 - 7 * math.cos(a + 0.45), y2 - 7 * math.sin(a + 0.45)); p.close()
        c.drawPath(p, fill=1, stroke=0)

    def chip(x, y, label, color):
        c.setFont('DeckBold', 9)
        w = c.stringWidth(label, 'DeckBold', 9) + 12
        c.setFillColor(HexColor(color)); c.roundRect(x, y, w, 15, 4, fill=1, stroke=0)
        c.setFillColor(HexColor('#FFFFFF')); c.drawString(x + 6, y + 4, label)
        return w

    checks = f['checks']

    # 1. Cover
    c.setFillColor(HexColor(NAVY)); c.rect(0, 0, W, H, fill=1, stroke=0)
    text(70, 452, 820, 'Collections<br/>Copilot', 50, '#FFFFFF', True, maximum=140)
    text(72, 288, 820, 'Every customer call in the right order,<br/>within policy, with the reason shown', 26, '#FFFFFF', maximum=80)
    text(72, 172, 810, 'Adda Wale', 22, '#6DDBD3', True)
    text(72, 128, 816, 'Prakhar Gupta, Aryan Shrivastava, Krish Agarwal, Ved Maurya', 16, '#FFFFFF', maximum=30)
    text(72, 70, 810, f'CIBC Hackathon finals · synthetic Maple Bank data · snapshot {SNAPSHOT}', 13, '#BCD0D1')
    c.showPage()

    # 2. The problem
    page('Before every call, an agent has to check eight things',
         'The facts sit in different systems and the rules in different policies. Missing one can mean a breach or a harmed customer.')
    items = [('Restrictions', 'insolvency, cease, deceased', 'POL-COLL-001 §7.3'), ('Representative', 'counsellor, lawyer, trustee', '§5.4'),
             ('Disputes, complaints', 'pause disputed amounts', 'PRC-COLL-012'), ('Vulnerability', 'safeguard, certified agent', 'POL-COLL-004 §4.5'),
             ('Hardship', 'programme before payment', '§4.2'), ('Open promise', 'remind, do not ask for more', 'PRC-COLL-010'),
             ('When contact is legal', 'local hours, holidays, 3 in 7 days', 'POL-COLL-001 §5.1-5.2'), ('Payment ask', 'timed to payday, within 21 days', 'PRC-COLL-010 §3.1')]
    for i, (label, body, ref) in enumerate(items):
        col, row = i % 2, i // 2
        x, top = 48 + col * 300, 396 - row * 82
        c.setFillColor(HexColor(TEAL)); c.circle(x + 13, top - 12, 13, fill=1, stroke=0)
        c.setFillColor(HexColor('#FFFFFF')); c.setFont('DeckBold', 12); c.drawCentredString(x + 13, top - 16.5, str(i + 1))
        text(x + 34, top, 250, f'<b>{escape(label)}</b>', 15, maximum=22)
        text(x + 34, top - 22, 250, escape(body), 12.5, MUTED, maximum=20)
        text(x + 34, top - 40, 250, escape(ref), 10, TEAL, font='DeckMono', maximum=16)
    for i, (value, label) in enumerate([(f"{f['open_cases']:,}", 'open collections cases'),
                                        (f"{f['agents']:,}", 'agents with assigned cases'),
                                        (f"{f['documents']}", 'policy and procedure documents')]):
        text(668, 392 - i * 100, 250, value, 34, TEAL, True, maximum=46)
        text(668, 346 - i * 100, 250, label, 14, MUTED, maximum=20)
    c.showPage()

    # 3. What we found
    page(f"What we found across {f['open_cases']:,} open cases",
         'Each number is one SQL query, shown on the Overview page next to its definition.',
         'Source: app/portfolio_checks.py on the 28 Sep 2026 snapshot')
    order = ['hardship_no_plan', 'over_contact_cap', 'outside_permitted_hours', 'near_write_off', 'vulnerable_uncertified', 'insolvency_not_on_hold']
    for i, key in enumerate(order):
        ch = checks[key]
        col, row = i % 3, i // 3
        x, y = 48 + col * 292, 232 - row * 182
        c.setFillColor(HexColor('#FFFFFF')); c.setStrokeColor(HexColor(LINE)); c.roundRect(x, y, 276, 168, 8, fill=1, stroke=1)
        if ch['severity'] == 'high':
            c.setFillColor(HexColor(CORAL)); c.rect(x, y, 5, 168, fill=1, stroke=0)
        text(x + 18, y + 156, 246, escape(ch['title']), 13, MUTED, maximum=36)
        text(x + 18, y + 116, 246, f"{ch['value']:,} <font size=13 color='{MUTED}'>{escape(ch['unit'])}</font>", 30, NAVY, True, maximum=42)
        text(x + 18, y + 70, 246, escape(ch['action']), 11.5, maximum=32)
        text(x + 18, y + 32, 246, escape(ch['policy']), 9, TEAL, font='DeckMono', maximum=24)
    c.showPage()

    # 4. How we decided
    page('How we decided which tool does each job',
         'Five constraints from the policies and the data came before any code. One rule then picked the technology for each job.',
         'Source: docs/design-decisions.md')
    top = 404
    for i, (label, body) in enumerate([
            ('Compliance first', 'A wrong step is a legal or policy breach, not a lower score.'),
            ('Explainable', 'Every recommendation names its source record and policy section.'),
            ('Data stays in the bank by default', 'Notes and transcripts are the most sensitive text we hold.'),
            ('Works on the next data release', 'Nothing in the decisions is tied to this extract.'),
            ('Measured, not claimed', 'Every number can be reproduced by a script or a query.')]):
        c.setFillColor(HexColor(TEAL)); c.circle(61, top - 9, 11, fill=1, stroke=0)
        c.setFillColor(HexColor('#FFFFFF')); c.setFont('DeckBold', 11); c.drawCentredString(61, top - 13, str(i + 1))
        top = text(80, top, 300, f'<b>{escape(label)}</b>', 13.5, maximum=22)
        top = text(80, top - 2, 300, escape(body), 11, MUTED, maximum=34) - 12
    text(48, top - 4, 332, 'The LLM goes only where language helps <i>and</i> its output can be checked; it never touches numbers or compliance steps.', 12, TEAL, maximum=54)
    picture(DOCS / 'how-it-works/decision-rule.png', 396, 36, 516, 384)
    c.showPage()

    # 5. Backend architecture
    vol, pl = f['volumes'], f['plans']
    page('Backend architecture, and why each part',
         'Customer data is only read; reviews and audit are the only writes; the LLM is optional.',
         'Source: app/main.py, app/action_plan.py, app/insights.py, app/storage.py, app/gemini.py; timings measured on the demo laptop at export')
    box(48, 316, 160, 104, 'Next.js web app', 'Nine pages and Ctrl+K. No business logic or data access in the browser.')
    box(240, 316, 190, 104, 'FastAPI backend', 'Typed JSON endpoints. Role and case access checked on every request, not by hiding buttons.')
    box(240, 176, 190, 112, 'Gemini 3.5 Flash-Lite', 'Optional. Fills a fixed JSON schema; every reply is validated; any failure falls back to local.', dashed=True)
    box(462, 352, 220, 68, 'Rules engine', 'action_plan, call_session, work_queue: each policy step is code.', accent=True, body_size=10)
    box(462, 276, 220, 68, 'Ask engine', 'Question to reviewed SQL with bound parameters; BM25 policy search.', body_size=10)
    box(462, 200, 220, 68, 'Customer 360', 'One customer across systems: timeline and contact calendar.', body_size=10)
    box(714, 300, 198, 120, 'DuckDB, read-only', f"Columnar SQL in one local file: {vol['customers'] / 1e6:.2f}M customers, {vol['contact_history'] / 1e6:.2f}M contacts, {vol['agent_notes'] / 1e3:,.0f}K notes. Reads Parquet directly.", body_size=10)
    box(714, 176, 198, 108, 'SQLite, the only writes', 'Sessions, briefs, decisions. Hash-chained audit; triggers refuse edits and deletes.', body_size=10)
    arrow(208, 368, 240, 368)
    c.setStrokeColor(HexColor(MUTED)); c.setLineWidth(1.2); c.line(430, 368, 446, 368); c.line(446, 234, 446, 386)
    for yy in (386, 310, 234):
        arrow(446, yy, 462, yy)
    arrow(335, 316, 335, 288, dashed=True)
    c.setStrokeColor(HexColor(MUTED)); c.setLineWidth(1.2); c.line(698, 234, 698, 386)
    for yy in (386, 310, 234):
        c.line(682, yy, 698, yy)
    arrow(698, 360, 714, 360); arrow(698, 230, 714, 230)
    text(48, 288, 170, 'Why these parts: DuckDB scans millions of rows in milliseconds without a server; BM25 cites an exact policy section; SQLite keeps writes away from customer data.', 10.5, NAVY, maximum=120)
    for i, (value, label) in enumerate([(f"{f['scan_ms']:.0f} ms", '30-day scan of all outbound contacts'),
                                        (f"{f['call_seconds']:.2f} s", 'Call Mode recompute, in-process (about 0.17 s via the web API)'),
                                        ('0.23 s', 'full brief (measured 15 Oct)'),
                                        (f"{pl['seconds']:.1f} s", f"plan all {pl['customers']:,} customers, nightly batch"),
                                        ('0', 'model-written SQL queries ever executed')]):
        x = 48 + i * 174
        c.setFillColor(HexColor('#FFFFFF')); c.setStrokeColor(HexColor(LINE)); c.setLineWidth(1); c.roundRect(x, 40, 164, 104, 7, fill=1, stroke=1)
        text(x + 12, 132, 140, value, 24, TEAL, True, maximum=34)
        text(x + 12, 96, 140, escape(label), 10.5, MUTED, maximum=44)
    c.showPage()

    # 6. Why this model, and why this LLM
    llm = f['llm']
    g, lr, rules, serve = llm['gemini'], llm['logistic_regression'], llm['rules_only'], llm['serving_brief']
    positives = llm['positives']
    page('Why this model, and why this LLM',
         f"Same {llm['notes']} held-out notes, {positives} with hardship. Gemini was given the policy's hardship definition.",
         'Source: scripts/compare_llm_classifier.py, data/llm-comparison.json; held-out split from scripts/train_model.py (customer-grouped, seed 1590)')
    local = f"≤ {f['local_ms_per_note']:.2f} ms"
    stable = g.get('same_answer_on_rerun')
    rows = [('Served detector: model OR any cue (what the app ships)', serve, local, '100%', 'No', 'Cue and sentence shown'),
            ('Logistic regression on 9 policy cues', lr, local, '100%', 'No', '9 named weights'),
            ('Rules only: any cue fires', rules, local, '100%', 'No', 'Cue and sentence shown'),
            (f"Gemini 3.5 Flash-Lite, zero-shot", g, f"{g['median_seconds_per_note']:.2f} s median",
             f"{stable:.0%}" + (f" of {g['rerun_notes']}" if g.get('rerun_notes') else '') if stable is not None else 'n/a', 'Yes: note text sent', 'A yes or no, no reason')]
    heads = ['Detector', 'Hardship found', 'False alarms', 'Time per note', 'Same answer twice', 'Note leaves the bank', 'Explains itself']
    xs, ws = [48, 316, 422, 504, 610, 698, 806], [260, 100, 76, 100, 82, 102, 106]
    for j, head in enumerate(heads):
        text(xs[j], 410, ws[j], f'<b>{escape(head)}</b>', 10.5, MUTED, maximum=30)
    c.setStrokeColor(HexColor(LINE)); c.setLineWidth(1)
    for i, (name, m, speed, same, leaves, why) in enumerate(rows):
        y = 366 - i * 46
        c.line(48, y + 12, 912, y + 12)
        if i == 0:
            c.setFillColor(HexColor('#E6F2F0')); c.rect(48, y - 32, 864, 44, fill=1, stroke=0)
        found = f"{m['tp']} of {m['tp'] + m['fn']}"
        color = TEAL if i == 0 else NAVY
        cells = [name, found, str(m['fp']), speed, same, leaves, why]
        for j, cell in enumerate(cells):
            text(xs[j], y + 4, ws[j], f'<b>{escape(cell)}</b>' if j in (0, 1) else escape(cell), 11 if j else 11.5, color if j != 5 or leaves == 'No' else RED, maximum=40)
    notes_total = f['volumes']['agent_notes']
    local_s = notes_total * f['local_ms_per_note'] / 1000
    llm_days = notes_total * g['median_seconds_per_note'] / 86400
    text(48, 178, 864, f"<b>All {notes_total:,} notes, one at a time at the measured rate:</b> local detector about {local_s:,.0f} s; Gemini about {llm_days:,.1f} days"
         + (f"; {g['unreadable_answers']} unreadable Gemini answers in {g['calls']} calls." if g.get('unreadable_answers') else '.')
         + (f" {f['llm_fp_vulnerability_tag']} of Gemini's {g['fp']} false alarms were notes tagged \u201ccust vulnerable - financial hardship\u201d: a vulnerability tag under POL-COLL-004 \u00a74.5, not hardship." if f.get('llm_fp_vulnerability_tag') else ''),
         12.5, NAVY, maximum=40)
    text(48, 128, 420, '<b>Why this model</b><br/>500 labelled notes is too few for a deep model. Nine policy cues give readable weights, use no protected or vulnerability inputs, and are identical offline and live. It runs inside the bank.', 11, MUTED, maximum=96)
    text(492, 128, 420, '<b>Why this LLM, and only to propose</b><br/>Gemini 3.5 Flash-Lite: free tier, JSON-schema output we validate, under 2 s a call; 3.8 Flash was overloaded (503 and timeouts) on 15 Oct. '
         'It sits behind one module. It proposes plans, verbatim evidence and call outcomes; the app verifies each one.', 11, MUTED, maximum=96)
    c.showPage()

    # 7. The brief
    page('The brief: what to do, in order',
         'Rules over source records decide every step. The model can only flag possible hardship for a human to confirm.')
    flow = [('1', "Don't contact", 'restriction recorded', 'stop'), ('2', 'Representative only', 'all contact through them', 'do'),
            ('3', 'Dispute / complaint', 'pause, escalate', 'careful'), ('4', 'Vulnerable', 'script, certified agent', 'careful'),
            ('5', 'Hardship first', 'eligible programmes', 'do'), ('6', 'Promise due', 'reminder only', 'do'),
            ('7', 'Legal window', 'hours, holiday, 3 in 7 days', 'do'), ('8', 'Ask for payment', 'timed to payday', 'do')]
    colors = {'stop': RED, 'do': TEAL, 'careful': CORAL}
    for i, (n, label, body, kind) in enumerate(flow):
        col, row = i % 4, i // 4
        x, y = 48 + col * 222, 268 - row * 140
        c.setFillColor(HexColor('#FFFFFF')); c.setStrokeColor(HexColor(colors[kind])); c.setLineWidth(1.6)
        c.roundRect(x, y, 200, 110, 8, fill=1, stroke=1)
        chip(x + 12, y + 84, {'stop': 'STOP', 'do': 'DO', 'careful': 'CAREFUL'}[kind], colors[kind])
        text(x + 12, y + 76, 176, f'<b>{n}. {escape(label)}</b>', 13, maximum=36)
        text(x + 12, y + 38, 176, escape(body), 12, MUTED, maximum=32)
        if col < 3:
            c.setStrokeColor(HexColor(LINE)); c.setLineWidth(2); c.line(x + 202, y + 55, x + 220, y + 55)
    text(48, 102, 864, 'Each step shows the policy section and the source record it relies on. Steps 1-4 can end or change the call before any money is discussed. '
         'A supervisor reviews every brief; the app never contacts a customer.', 14, maximum=60)
    c.showPage()

    # 8. Example: legal window
    sav = f['sav']['contact_window']
    page('Example: when is contact actually allowed?', 'Customer SAV-6847, a real record in the synthetic release.',
         'Source: contact_history, customer consent and hours, holidays computed by rule (app/holidays.py)')
    reasons = ''.join(f"<br/>{escape(action_plan._day(__import__('datetime').date.fromisoformat(s['date'])))}: {escape(s['reason'])}" for s in sav['skipped'])
    text(48, 400, 330, '<b>Not Monday or Tuesday</b><br/>3 attempts already used in the last 7 days. Payment reminders count (POL-COLL-001 §5.2).', 15, maximum=110)
    text(48, 282, 330, '<b>Not Wednesday</b><br/>30 Sep is a statutory holiday (§5.1).', 15, maximum=70)
    text(48, 200, 330, f"<b>Thursday {sav['from_local']}-{sav['until_local']} their time</b><br/>in {escape(sav['time_zone'])}, with consent checked per channel.", 15, TEAL, maximum=80)
    text(48, 100, 330, 'Vulnerable customer: the script and "never pressure" rule are repeated at the payment step.', 12.5, MUTED, maximum=48)
    shot('plan-SAV-6847.png', 400, 40, 512, 380)
    c.showPage()

    # 9. Example: hardship first
    eligible = [p for p in f['jev']['programmes'] if p['status'] == 'likely_eligible']
    page('Example: hardship options before payment', 'Customer JEV-1240: hardship recorded on a loan case, no plan yet.',
         'Source: hardship_programs.csv (v2026.1), HPT-2026, POL-COLL-004 §4.2-4.3')
    text(48, 400, 330, '<b>Programme rules checked</b><br/>effective version, product, days past due, months on book, uses in 12 months, insolvency, broken plans in 90 days.', 14, maximum=120)
    text(48, 274, 330, '<b>Likely eligible</b><br/>' + '<br/>'.join(f"{escape(p['name'])} (approver: {escape(p['approver'].replace('_', ' '))})" for p in eligible), 14, TEAL, maximum=100)
    text(48, 160, 330, 'Missing inputs are named (income evidence for a term extension). The approver decides; the agent asks for payment only after the options are discussed.', 12.5, MUTED, maximum=80)
    shot('plan-JEV-1240.png', 400, 40, 512, 380)
    c.showPage()

    # 10. Live Call Mode
    call = f['call']
    red3 = next(o for o in call['calculator']['options'] if o['program_id'] == 'HP-LOAN-RED3')
    ext = next(o for o in call['calculator']['options'] if o['program_id'] == 'HP-LOAN-EXT')
    aff = call['affordability']
    page('Live Call Mode: the plan follows the conversation', 'JEV-1240 on the phone. Every click recomputes the plan, the checks and the script with the same rules as the brief.',
         'Source: app/call_session.py; programme terms from hardship_programs v2026.1; PRC-COLL-010 §3.1')
    top = 400
    for label, body in [
            ('Debt details only after the basics', 'Who answered, recording notice, identity. Third parties and voicemail get no debt details.'),
            ('Hardship options, priced', f"Reduced payment: ${red3['payment_now']:,.2f} to ${red3['payment_during']:,.2f} for {red3['months']} months (agent approves). "
                                         f"Term extension: ${ext['payment_during']:,.2f} (specialist)."),
            ('Promises and callbacks checked', f"Within 21 days, legal hours, holidays, the weekly cap. Affordability: the promise is {aff['promise_share_of_disposable']:.0%} of money left each month."),
            ('Notes to outcomes, quoted', 'Typed notes become proposals, each with its exact sentence; nothing applies until the agent accepts.'),
            ('Wrap-up to review', 'Note, outcome codes ' + ', '.join(call['wrap_up']['outcome_codes']) + ' and follow-ups go to a supervisor.')]:
        top = text(48, top, 350, f'<b>{escape(label)}</b>', 13.5, maximum=22)
        top = text(48, top - 2, 350, escape(body), 11, MUTED, maximum=46) - 10
    text(48, 66, 350, 'HAC-4447 (consumer proposal): the call page is blocked and its controls are off.', 11.5, RED, maximum=34)
    shot('call-JEV-1240.png', 420, 40, 492, 368, left_fraction=0.19)
    c.showPage()

    # 11. Work queue
    q = f['queue']
    page('Work queue: fixed rules, a reason on every row', f"Agent {q['agent_id']}: {q['total']} open cases, ordered by tier, then promise date or days past due, then the next legal contact time.",
         'Source: app/work_queue.py; vulnerability and protected attributes never change the order')
    top = 396
    for t in q['tiers']:
        if not t['count']:
            continue
        text(48, top, 260, f"<b>{escape(t['label'])}</b>  <font color='{TEAL}'>{t['count']}</font>", 14, maximum=22)
        top = text(48, top - 20, 260, escape(t['rule']), 10.5, MUTED, maximum=44) - 12
    text(48, 74, 260, 'No model score decides order. Each row shows the next allowed contact.', 12.5, maximum=36)
    shot('queue-viewport.png', 330, 40, 582, 350, top_fraction=0.02)
    c.showPage()

    # 12. Scale and what is at stake
    pl, val = f['plans'], f['value']
    page(f"Every open case planned nightly: {pl['customers']:,} in {pl['seconds']:.0f} s",
         f"scripts/batch_plans.py: {pl['workers']} worker processes, about {pl['plans_per_second']:,.0f} plans per second, {pl['errors']} errors. Set-based loading, a separate output file, so serving is never locked.",
         'Source: data/plans-report.json; Overview "What\'s at stake" (app/portfolio_checks.py), source amounts, not claimed savings')
    labels = {'payment_ask': 'Ask for payment', 'promise': 'Follow an open promise', 'hardship': 'Offer hardship first',
              'restriction': "Don't contact (restriction)", 'representative': 'Through a representative', 'vulnerability': 'Vulnerable-customer approach'}
    counts = sorted(pl['next_step_counts'].items(), key=lambda kv: -kv[1])
    biggest = counts[0][1]
    text(48, 392, 420, '<b>First step chosen for each open case</b>', 14, maximum=22)
    for i, (key, n) in enumerate(counts):
        y = 340 - i * 44
        text(48, y + 21, 190, escape(labels.get(key, key)), 11.5, maximum=18)
        c.setFillColor(HexColor('#E3ECE9')); c.rect(240, y + 6, 180, 16, fill=1, stroke=0)
        c.setFillColor(HexColor(RED if key == 'restriction' else TEAL)); c.rect(240, y + 6, 180 * n / biggest, 16, fill=1, stroke=0)
        text(428, y + 21, 70, f'{n:,}', 11.5, NAVY, True, maximum=18)
    for i, (key, label) in enumerate([('write_off_exposure', 'exposure on cases close to write-off'),
                                      ('hardship_overdue', 'overdue, customers in hardship with no plan'),
                                      ('contact_spend', 'outbound contact cost, last 30 days')]):
        item = val[key]
        amount = item['value']
        shown = f'${amount / 1e6:,.1f}M' if amount >= 1e6 else f'${amount / 1e3:,.1f}K'
        text(560, 392 - i * 104, 352, shown, 30, CORAL if i < 2 else NAVY, True, maximum=42)
        extra = (f"expected-loss estimate ${item['secondary'] / 1e6:,.1f}M" if key == 'write_off_exposure'
                 else f"{int(item['tertiary']):,} customers" if key == 'hardship_overdue' else f"{int(item['secondary']):,} contacts")
        text(560, 350 - i * 104, 352, f'{escape(label)} · {escape(extra)}', 12, MUTED, maximum=36)
    c.showPage()

    # 13. New data without code changes
    page('Built for the next data release, not just this one', 'Nothing in the decisions is hard-coded to this extract. A test builds a March 2027 release and the plan follows it.',
         'Source: app/snapshot.py, app/holidays.py, tests/test_unseen_release.py')
    rows = [('Snapshot date', 'read from max(collections_cases.extract_ts)', f'{SNAPSHOT}, planning at {AS_OF:%H:%M} UTC', '24 Mar 2027'),
            ('Statutory holidays', 'computed by rule for any year', '105 of 105 flagged dates, 2016-2026', 'Good Friday 2027 skipped'),
            ('Weekly contact cap', 'read per case (contact_cap_7d)', '3 attempts in 7 days', 'cap of 2 blocks 2 days'),
            ('Policy citations', 'versions from reference_documents', 'POL-COLL-004 v4.2', 'cites v5.0'),
            ('Programme rules', 'version effective on the snapshot', 'v2026.1', 'HPT-2027 v2027.1')]
    xs = [48, 236, 500, 716]
    for j, head in enumerate(['What', 'How it is found', 'This release', 'Synthetic 2027 test']):
        text(xs[j], 392, 200, f'<b>{escape(head)}</b>', 12.5, MUTED, maximum=20)
    c.setStrokeColor(HexColor(LINE)); c.setLineWidth(1)
    for i, row in enumerate(rows):
        y = 356 - i * 52
        c.line(48, y + 8, 912, y + 8)
        for j, cell in enumerate(row):
            text(xs[j], y, [180, 250, 206, 196][j], f'<b>{escape(cell)}</b>' if j == 0 else escape(cell), 12.5, TEAL if j == 3 else NAVY, maximum=40)
    text(48, 82, 864, 'The build needs the same table layout (the C360 contract); a new schema needs a mapping. '
         'The rules are plain Python and SQL, so a bank can review and version them.', 12.5, MUTED, maximum=40)
    c.showPage()

    # 14. Live questions
    dev_ok, dev_n = f['dev']
    refusals = sum(r['refused'] == 'true' for r in f['benchmark'])
    page('Ask what the data can answer, nothing else',
         'Questions compile into reviewed SQL with bound parameters. Model-written SQL is never executed.')
    top = 410
    for label, body in [
            ('One-line answer first', 'A plain-English summary computed from the result rows, then the table and its SQL.'),
            ('Trends, rankings, counts, programmes', 'Monthly trends, "which province is highest", how many customers or cases, programmes in force.'),
            ('Clarify instead of guessing', 'Unsupported questions such as "per agent" get supported rephrasings, never a substituted number.'),
            ('Refuse what is not allowed', 'Protected-attribute decisions, bulk personal data and unrelated requests are refused.')]:
        top = text(48, top, 380, f'<b>{escape(label)}</b>', 14, maximum=22)
        top = text(48, top - 3, 380, escape(body), 11.5, MUTED, maximum=34) - 14
    for i, (value, label) in enumerate([(f'{dev_ok}/{dev_n}', 'organiser reference answers matched'),
                                        (f"{len(f['benchmark'])}", f'benchmark answers, same engine ({refusals} refusals)'),
                                        (f"{f['tests']:,}", 'automated tests passing')]):
        text(48 + i * 132, 112, 124, value, 22, TEAL, True, maximum=30)
        text(48 + i * 132, 82, 124, escape(label), 9.5, MUTED, maximum=40)
    shot('ask-ranking.png', 450, 40, 462, 380, top_fraction=0.2)
    c.showPage()

    # 15. Hardship detector
    v1, v2 = f['hardship']['v1_current'], f['hardship']['c360-financial-v2']
    page('Hardship detector: measured honestly', 'Customer-grouped 5-fold cross-validation, 5 seeds, 500 labelled notes; plus the original untouched held-out split.',
         'Source: scripts/evaluate_hardship_cv.py, docs/hardship-detector-evaluation.md')
    for i, (metric, label) in enumerate([('recall', 'Recall: hardship notes found'), ('precision', 'Precision: flags that were right')]):
        top = 400 - i * 130
        text(48, top, 560, f'<b>{label}</b>', 16, maximum=24)
        for j, (name, cue, col) in enumerate([('Before', v1, '#9DB5B1'), ('After', v2, TEAL)]):
            value = cue['cross_validation']['model'][metric]['mean']
            y = top - 56 - j * 34
            text(48, y + 20, 70, name, 13, MUTED, maximum=20)
            c.setFillColor(HexColor('#E3ECE9')); c.rect(130, y, 400, 24, fill=1, stroke=0)
            c.setFillColor(HexColor(col)); c.rect(130, y, 400 * value, 24, fill=1, stroke=0)
            text(540, y + 22, 80, f'{value:.0%}', 15, col if j else MUTED, True)
    h1, h2 = v1['heldout_seed_1590']['model'], v2['heldout_seed_1590']['model']
    text(648, 392, 264, '<b>Untouched held-out notes</b>', 15, maximum=24)
    text(648, 366, 264, f"Found {h2['tp']} of {h2['tp'] + h2['fn']} hardship notes (was {h1['tp']}).<br/>False alarms: {h2['fp']} (was {h1['fp']}).", 14, TEAL, maximum=80)
    text(648, 270, 264, '<b>What changed</b>', 15, maximum=24)
    text(648, 246, 264, 'Wider English and French cues, plus illness, separation and disaster, as listed in POL-COLL-004 §4.2.', 12.5, MUTED, maximum=80)
    text(48, 112, 864, 'Caveat: the synthetic notes reuse a small set of phrasings, so this is coverage of this dataset, not real-world accuracy. '
         'Vulnerability tags and protected grounds are excluded from the model inputs.', 13, RED, maximum=60)
    c.showPage()

    # 16. Rules decide, AI suggests, people approve
    page('Rules decide, AI suggests, people approve', 'Where each kind of judgement lives in the product, and the limits we state before anyone asks.',
         'Source: app/action_plan.py, app/features.py, app/gemini.py, app/storage.py')
    for i, (tag, color, title, body) in enumerate([
            ('RULES', NAVY, 'Decide', 'Contact windows, the weekly cap, restrictions, programme eligibility and the order of steps. Each step cites its policy section and source record.'),
            ('AI', TEAL, 'Suggests', 'The cue model flags possible hardship. Gemini, when on, proposes question plans, verbatim evidence and call outcomes. Every output is checked; nothing is applied automatically.'),
            ('HUMAN', CORAL, 'Approves', 'The agent accepts or dismisses each proposal. A supervisor approves, edits or rejects every brief and call note with a reason, in a hash-chained audit.')]):
        x = 48 + i * 206
        c.setFillColor(HexColor('#FFFFFF')); c.setStrokeColor(HexColor(color)); c.setLineWidth(1.6); c.roundRect(x, 150, 194, 262, 8, fill=1, stroke=1)
        chip(x + 12, 384, tag, color)
        text(x + 12, 372, 170, f'<b>{escape(title)}</b>', 17, maximum=26)
        text(x + 12, 340, 170, escape(body), 11.5, MUTED, maximum=180)
    dev_ok, dev_n = f['dev']
    text(670, 412, 242, '<b>Verified</b>', 16, maximum=24)
    text(670, 386, 242, f"{f['tests']:,} tests passing<br/>{dev_ok}/{dev_n} numeric reference answers<br/>{f['e2e']} browser checks, desktop and phone<br/>"
         f"{f['quality']['identity']['golden_customers']:,} golden customers", 13, TEAL, maximum=110)
    text(670, 270, 242, '<b>Limits we state</b>', 16, maximum=24)
    text(670, 244, 242, 'Synthetic, templated data: no business-uplift claim. National statutory holidays only. Payday estimated for about half of cases (52%). '
         'Gemini verified live with the lite model only. Stated income unverified; identity precision unmeasured.', 11.5, MUTED, maximum=150)
    text(48, 112, 600, 'The app never sends a message, places a call or changes a source record. Approval only records a decision.', 13, maximum=40)
    c.showPage(); c.save()

    reader = PdfReader(output)
    if len(reader.pages) != SLIDES or any(not p.extract_text().strip() for p in reader.pages):
        raise ValueError('Deck export has missing pages or text.')
    print(json.dumps({'pdf': str(output), 'slides': len(reader.pages), 'tests': f['tests']}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT.parent / 'deliverables/AddaWale-Finals-Presentation.pdf')
    generate(parser.parse_args().output)
