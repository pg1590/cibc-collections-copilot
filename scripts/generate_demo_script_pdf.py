"""Export the exact recording walkthrough as a printable PDF recording aid."""
import re
import sys
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.settings import ROOT
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pypdf import PdfReader


def export(source=ROOT / 'docs/demo-walkthrough.md', output=ROOT / 'presentation/AddaWale-Finals-Demo-Script.pdf',
           label='Finals live demo script - narration in the Say column', title_text='Adda Wale - finals live demo script'):
    pdfmetrics.registerFont(TTFont('DemoSans', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'))
    pdfmetrics.registerFont(TTFont('DemoBold', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'))
    normal = ParagraphStyle('body', fontName='DemoSans', fontSize=9.6, leading=12.6, spaceAfter=3)
    spoken = ParagraphStyle('spoken', parent=normal, fontName='DemoBold', fontSize=10.4,
                            leading=14.3, spaceBefore=3, spaceAfter=8, textColor=colors.HexColor('#18343C'))
    heading = ParagraphStyle('heading', parent=normal, fontName='DemoBold', fontSize=13.2,
                             leading=18, spaceBefore=6, spaceAfter=4, keepWithNext=True)
    title = ParagraphStyle('title', parent=heading, fontSize=21, leading=27)
    cell = ParagraphStyle('cell', parent=normal, fontSize=8.5, leading=11.5, spaceAfter=0)

    def markup(value):
        value = value.replace('—', '-').replace('–', '-')
        value = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', value)
        value = escape(value)
        value = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', value)
        return value.replace('`', '')

    story = []
    lines = source.read_text().splitlines()
    breaks = ('## 0:00', '## 1:40', '## 3:15', '## Copy-ready')
    index = 0
    while index < len(lines):
        line = lines[index]
        index += 1
        if not line:
            continue
        if line.startswith(breaks):
            story.append(PageBreak())
        if line.startswith("The brief's exact generated internal note is:"):
            story.append(PageBreak())
        if line.startswith('# '):
            story.append(Paragraph(markup(line[2:]), title))
        elif line.startswith('## '):
            story.append(Paragraph(markup(line[3:]), heading))
        elif line.startswith('> '):
            story.append(Paragraph(markup(line[2:]), spoken))
        elif line.startswith('```'):
            block = []
            while index < len(lines) and not lines[index].startswith('```'):
                block.append(lines[index]); index += 1
            index += 1
            story.append(Paragraph(markup(' '.join(block)), spoken))
        elif line.startswith('|'):
            rows = [line]
            while index < len(lines) and lines[index].startswith('|'):
                rows.append(lines[index]); index += 1
            data = [[Paragraph(markup(value.strip()), cell) for value in row.strip('|').split('|')]
                    for row in rows if not re.fullmatch(r'[|:\-\s]+', row)]
            widths = [140, A4[0] - 220] if len(data[0]) == 2 else [38, 165, A4[0] - 80 - 203]  # three columns: time, do, say
            table = Table(data, colWidths=widths, repeatRows=1, hAlign='LEFT')
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E3F0ED')),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LINEBELOW', (0, 0), (-1, -1), .3, colors.HexColor('#CCD8D5')),
                ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ]))
            story.extend([table, Spacer(1, 10)])
        else:
            story.append(Paragraph(markup(line), normal))

    def footer(canvas, doc):
        canvas.setFont('DemoSans', 8)
        canvas.setFillColor(colors.HexColor('#52676B'))
        canvas.drawString(40, 20, label)
        canvas.drawRightString(A4[0] - 40, 20, str(doc.page))

    output.parent.mkdir(parents=True, exist_ok=True)
    SimpleDocTemplate(str(output), pagesize=A4, leftMargin=40, rightMargin=40,
                      topMargin=35, bottomMargin=38, title=title_text,
                      author='Adda Wale').build(story, onFirstPage=footer, onLaterPages=footer)
    pdf = PdfReader(output)
    assert all(page.extract_text().strip() for page in pdf.pages)
    print(f'{output}: {len(pdf.pages)} pages')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Printable finals scripts in presentation/: the live demo script, or the 15-minute presentation script.')
    parser.add_argument('--presentation', action='store_true', help='Print docs/final-presentation-script.md instead of the demo script.')
    parser.add_argument('--finals', action='store_true', help=argparse.SUPPRESS)  # kept for old commands; the demo script is the default
    if parser.parse_args().presentation:
        export(ROOT / 'docs/final-presentation-script.md', ROOT / 'presentation/AddaWale-Final-Presentation-Script.pdf',
               'Final presentation script - 15 minutes, four speakers', 'Adda Wale - final presentation script')
    else:
        export()
