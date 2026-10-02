#!/usr/bin/env python3
"""Render the reviewed design source into a six-page submission draft."""
import json
import sys
from pathlib import Path
from html import escape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.venv/libdeps'))
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, Flowable
from pypdf import PdfReader

NAVY = colors.HexColor('#17324D')
BURGUNDY = colors.HexColor('#9B1C43')
LIGHT = colors.HexColor('#F0F4F7')
TEAL = colors.HexColor('#087E8B')
GRAY = colors.HexColor('#556474')
WIDTH = A4[0] - 78
BODY = ParagraphStyle('body', fontName='Helvetica', fontSize=10.3, leading=14, textColor=NAVY, spaceAfter=9)
H1 = ParagraphStyle('title', fontName='Helvetica-Bold', fontSize=22, leading=26, textColor=NAVY, spaceAfter=12)
H2 = ParagraphStyle('section', fontName='Helvetica-Bold', fontSize=11.3, leading=14, textColor=BURGUNDY, spaceBefore=6, spaceAfter=5)
CELL = ParagraphStyle('cell', parent=BODY, fontSize=9.3, leading=12.2, spaceAfter=0)
SMALL = ParagraphStyle('small', parent=BODY, fontSize=9, leading=12)

def para(text, style=BODY):
    return Paragraph(escape(text), style)

class Architecture(Flowable):
    """Vector diagram with explicit human and AI boundaries, no raster scaling."""
    def __init__(self):
        super().__init__()
        self.width = WIDTH
        self.height = 555

    def draw(self):
        c = self.canv
        w = self.width

        def text(x, top, width, s, bold=False, color=NAVY, size=8.6):
            st = ParagraphStyle('node', fontName='Helvetica-Bold' if bold else 'Helvetica', fontSize=size, leading=size + 3, textColor=color)
            p = para(s, st)
            _, ph = p.wrap(width, 200)
            p.drawOn(c, x, top - ph)
            return ph

        def box(x, y, width, height, title, lines, fill=LIGHT, border=NAVY):
            c.setFillColor(fill)
            c.setStrokeColor(border)
            c.setLineWidth(.8)
            c.roundRect(x, y, width, height, 7, stroke=1, fill=1)
            text(x + 12, y + height - 11, width - 24, title, True, border, 10)
            top = y + height - 31
            for line in lines:
                ph = text(x + 12, top, width - 24, line)
                top -= ph + 5
            if top < y + 4:
                raise ValueError('Diagram node overflow: ' + title)

        def arrow(x1, y1, x2, y2):
            c.setStrokeColor(TEAL)
            c.setFillColor(TEAL)
            c.setLineWidth(1.3)
            c.line(x1, y1, x2, y2)
            import math
            a = math.atan2(y2-y1, x2-x1)
            path = c.beginPath()
            path.moveTo(x2, y2)
            path.lineTo(x2-6*math.cos(a-.45), y2-6*math.sin(a-.45))
            path.lineTo(x2-6*math.cos(a+.45), y2-6*math.sin(a+.45))
            path.close()
            c.drawPath(path, fill=1, stroke=0)

        box(0, 485, w, 70, 'INPUT | BANKING RECORDS', [
            'Accounts, collection cases, contacts, payment promises and notes',
            'Synthetic files; source fields TBC (to be confirmed).'
        ])
        arrow(w/2, 485, w/2, 468)
        box(0, 337, w, 130, 'LAYER 1 | DATA PRODUCT FACTORY', [
            'Python / Polars / DuckDB: import files, remove duplicates and check data',
            'AI suggests field mappings; a HUMAN data reviewer approves them',
            'Match customer IDs; a HUMAN reviews uncertain matches',
            'CockroachDB stores C360: one customer view with sources and dates'
        ])
        gap = 15
        col = (w-gap)/2
        arrow(w/2, 337, col/2, 311)
        arrow(w/2, 337, col+gap+col/2, 311)
        box(0, 114, col, 196, 'LAYER 2 | QUESTIONS', [
            'AI understands the plain-English question',
            'Server checks supported measures and user access',
            'Approved read-only database query (SQL)',
            'Show answer, SQL, source and date; refuse unsupported requests'
        ])
        box(col+gap, 114, col, 196, 'LAYER 3 | AGENT ASSIST', [
            'Read only the assigned customer\'s permitted records',
            'AI finds possible financial hardship; a fixed brief shows facts and sources',
            'HUMAN: agent reviews; specialist checks hardship referral',
            'Recheck permissions, record approval and simulate the action'
        ])
        box(0, 48, w, 54, 'GOVERNANCE ACROSS ALL THREE LAYERS', [
            'Access checks | No protected attributes | Human review | Action records | Monitoring'
        ], fill=colors.HexColor('#FFF3F6'), border=BURGUNDY)
        text(0, 37, w, 'Next.js: user screen. FastAPI: service. Language model provider TBC. AI suggests; people approve. No real customer actions.', size=9)

def make_table(t):
    rows = [[para(v, CELL) for v in t['headers']]]
    rows.extend([[para(v, CELL) for v in row] for row in t['rows']])
    col_widths = [WIDTH * .35, WIDTH * .65]
    if t['headers'][0] == 'Question':
        col_widths = [WIDTH * .43, WIDTH * .57]
    tbl = Table(rows, colWidths=col_widths, repeatRows=1, hAlign='LEFT')
    tbl.setStyle(TableStyle([
        ('BACKGROUND', (0,0),(-1,0),colors.HexColor('#E2EAF0')),
        ('ROWBACKGROUNDS', (0,1),(-1,-1),[colors.white,LIGHT]),
        ('VALIGN', (0,0),(-1,-1),'TOP'),
        ('LEFTPADDING',(0,0),(-1,-1),8), ('RIGHTPADDING',(0,0),(-1,-1),8),
        ('TOPPADDING',(0,0),(-1,-1),6), ('BOTTOMPADDING',(0,0),(-1,-1),6),
        ('LINEBELOW',(0,0),(-1,0),.7,GRAY),
    ]))
    return tbl

def page_frame(c, doc):
    c.saveState()
    c.setFillColor(BURGUNDY)
    c.rect(39, A4[1]-34, 30, 3, fill=1, stroke=0)
    c.setFillColor(GRAY)
    c.setFont('Helvetica-Bold', 7.5)
    c.drawString(78,A4[1]-35,'ADDA WALE  |  CIBC COLLECTIONS HACKATHON')
    c.setStrokeColor(colors.HexColor('#D7DFE6'))
    c.line(39,37,A4[0]-39,37)
    c.setFont('Helvetica',7)
    c.drawString(39,25,'Design draft | 02 Oct 2026 | Source fields TBC (to be confirmed)')
    c.drawRightString(A4[0]-39,25,f'{doc.page} / 6')
    c.restoreState()

def markdown(d):
    lines=[f'# {d["title"]} — {d["team"]}', '', 'Members: '+', '.join(d['members']), '', d['subtitle'], '', 'Architecture: [architecture.mmd](architecture.mmd)', '', 'Source fields remain TBC (to be confirmed). This is a design; it has not been built yet.']
    for page in d['pages']:
        lines += ['', '---', '', '## '+page['title']]
        for s in page['sections']:
            lines += ['', '### '+s['heading'], '']
            lines += [p+'\n' for p in s.get('paragraphs',[])]
            if 'table' in s:
                t=s['table']
                lines += ['| '+' | '.join(t['headers'])+' |', '| '+' | '.join(['---']*len(t['headers']))+' |']
                lines += ['| '+' | '.join(v.replace('|','/') for v in row)+' |' for row in t['rows']]
    return '\n'.join(lines).rstrip()+'\n'

def main():
    d=json.loads((ROOT/'docs/submission-content.json').read_text())
    out=ROOT/'submission'/f'{d["team"]}_SystemDesign.pdf'
    out.parent.mkdir(parents=True, exist_ok=True)
    story=[para(d['title'],H1),para(d['subtitle'],BODY),para('TEAM: '+d['team'],H2),para('MEMBERS: '+', '.join(d['members']),SMALL),Spacer(1,5),Architecture()]
    for page in d['pages']:
        story += [PageBreak(),para(page['title'],H1)]
        for s in page['sections']:
            story.append(para(s['heading'],H2))
            story.extend(para(p) for p in s.get('paragraphs',[]))
            if 'table' in s:
                story += [make_table(s['table']),Spacer(1,5)]
    doc=SimpleDocTemplate(str(out),pagesize=A4,leftMargin=39,rightMargin=39,topMargin=56,bottomMargin=47,title=d['title']+' | '+d['team'],author=', '.join(d['members']))
    doc.build(story,onFirstPage=page_frame,onLaterPages=page_frame)
    reader=PdfReader(out)
    if len(reader.pages)!=6:
        raise ValueError(f'Expected six pages; generated {len(reader.pages)}. Revise layout before delivery.')
    texts=[p.extract_text() for p in reader.pages]
    for name in [d['team']]+d['members']:
        assert name in texts[0],f'Missing first-page name: {name}'
    joined='\n'.join(texts)
    for heading in ['Summary','Business value','Layer 1','Layer 2','Layer 3','AI usage','Scalability','Governance','Build plan']:
        assert heading in joined,f'Missing heading: {heading}'
    assert 'Quality rules' in texts[-1] and 'Owner:' in texts[-1]
    (ROOT/'docs/system-design.md').write_text(markdown(d))
    print(f'{out}\nVerified six pages, required headings and page-one names. Visual QA still required.')

if __name__=='__main__':
    main()
