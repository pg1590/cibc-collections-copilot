"""Export the implemented four-layer architecture as a one-page PDF."""
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import landscape,A4
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/architecture-build.pdf'
pdfmetrics.registerFont(TTFont('BuildSans','/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'))
pdfmetrics.registerFont(TTFont('BuildBold','/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'))
W,H=landscape(A4);c=canvas.Canvas(str(OUT),pagesize=(W,H))
c.setTitle('Collections Copilot - implemented architecture');c.setAuthor('Adda Wale')
navy=HexColor('#18343c');teal=HexColor('#087f80');muted=HexColor('#547078');paper=HexColor('#f5f7f4')
c.setFillColor(paper);c.rect(0,0,W,H,fill=1,stroke=0)
style=ParagraphStyle('body',fontName='BuildSans',fontSize=10,leading=15,textColor=navy)


def text(x,y,width,value,font=10,color=navy):
 s=ParagraphStyle('s',parent=style,fontSize=font,leading=font*1.45,textColor=color)
 p=Paragraph(value,s);_,height=p.wrap(width,400);p.drawOn(c,x,y-height);return height


def box(x,y,width,height,num,title,body):
 c.setStrokeColor(HexColor('#ccdcd8'));c.setFillColor(HexColor('#ffffff'));c.roundRect(x,y,width,height,9,fill=1,stroke=1)
 c.setFillColor(teal);c.roundRect(x+14,y+height-35,23,21,4,fill=1,stroke=0)
 c.setFillColor(HexColor('#ffffff'));c.setFont('BuildBold',10);c.drawCentredString(x+25.5,y+height-29,str(num))
 text(x+45,y+height-15,width-56,f'<b>{title}</b>',12)
 text(x+15,y+height-51,width-30,body)


def arrow(x1,y1,x2,y2):
 c.setStrokeColor(teal);c.setFillColor(teal);c.setLineWidth(1.5);c.line(x1,y1,x2,y2)
 p=c.beginPath();p.moveTo(x2,y2);p.lineTo(x2-7,y2+4);p.lineTo(x2-7,y2-4);p.close();c.drawPath(p,stroke=0,fill=1)

text(32,H-25,W-64,'<b>Collections Copilot</b>',24)
text(32,H-65,W-64,'Adda Wale | Implemented local build | Snapshot 28 September 2026',10,muted)
text(32,H-100,W-64,'<b>Source release:</b> CRM, cards, lending, core banking, collections and bureau data. Immutable CSV / Parquet, English and French notes/transcripts, current policy documents.',10)
width=(W-100)/2;height=153;left=32;right=W/2+18;top=H-307;bottom=top-184
box(left,top,width,height,1,'Data Product Factory','<b>DuckDB raw → curated → C360</b><br/>String IDs and leading zeros preserved. Typed/date checks retain raw values.<br/>Checked duplicates and cross-source identity rules. Review/unmatched links quarantined.<br/><b>Outputs:</b> C360, lineage crosswalk, counted quality report, YAML contract.')
box(right,top,width,height,2,'Insight / NLP','<b>FastAPI question engine</b><br/>Fixed query plans with bound parameters. SQL and source evidence accompany answers.<br/>BM25/current-policy retrieval; latest call evidence. Explicit refusals and clarification.<br/><b>Outputs:</b> app answers and system-generated benchmark CSV.')
box(left,bottom,width,height,3,'Feature Store','<b>One versioned offline/live definition</b><br/>Case, promise and contact features plus bilingual financial text cues.<br/>Eager Polars / Pandera checks. Measured parity: 100 customers, zero mismatches.<br/><b>Outputs:</b> stored feature rows and registry with source/version.')
box(right,bottom,width,height,4,'Model / Decisioning','<b>Local model and grounded review brief</b><br/>Logistic classifier trained on public note labels; customer-grouped holdout and baseline.<br/>Facts, exact evidence, policy references and a draft. Supervisor approve / reject / edit.<br/><b>Outputs:</b> persistent decisions and append-only SQLite audit.')
arrow(left+width,top+height/2,right,top+height/2)
arrow(left+width,bottom+height/2,right,bottom+height/2)
c.setStrokeColor(teal);c.line(left+width/2,top,left+width/2,bottom+height)
c.setFillColor(teal);p=c.beginPath();p.moveTo(left+width/2,bottom+height);p.lineTo(left+width/2-4,bottom+height+7);p.lineTo(left+width/2+4,bottom+height+7);p.close();c.drawPath(p,fill=1,stroke=0)
text(32,83,W-64,'<b>Application:</b> Next.js / Tailwind / shadcn-style Radix components → FastAPI. Server-issued roles; agents restricted to assigned cases. Only supervisors can record review decisions.',9)
text(32,49,W-64,'<b>Controls:</b> No paid runtime API calls or automatic customer contact. Protected attributes excluded from classifier/features; restricted fairness evaluation only. Match scores are uncalibrated rule scores.',9)
c.showPage();c.save()
assert len(PdfReader(OUT).pages)==1
print(OUT)
