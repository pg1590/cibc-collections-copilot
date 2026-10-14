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
from reportlab.lib.fonts import addMapping
addMapping('BuildSans',0,0,'BuildSans');addMapping('BuildSans',1,0,'BuildBold');addMapping('BuildSans',0,1,'BuildSans');addMapping('BuildSans',1,1,'BuildBold')
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
 used=text(x+15,y+height-51,width-30,body,9.5)
 if used>height-62:raise ValueError('Architecture node text exceeds available height: '+title)


def arrow(x1,y1,x2,y2):
 c.setStrokeColor(teal);c.setFillColor(teal);c.setLineWidth(1.5);c.line(x1,y1,x2,y2)
 p=c.beginPath();p.moveTo(x2,y2);p.lineTo(x2-7,y2+4);p.lineTo(x2-7,y2-4);p.close();c.drawPath(p,stroke=0,fill=1)

text(32,H-25,W-64,'<b>Collections Copilot</b>',24)
text(32,H-65,W-64,'Adda Wale | Finals build | Snapshot 28 September 2026 | <font color="#087f80"><b>AI</b></font> = model output, <b>RULES</b> = reviewed code and SQL, <font color="#c2533d"><b>HUMAN</b></font> = person decides',10,muted)
text(32,H-100,W-64,'<b>Source release:</b> CRM, cards, lending, core banking, collections and bureau data. CSV / Parquet, bilingual notes/transcripts, current policies and optional synthetic WAV audio.',10)
width=(W-100)/2;height=153;left=32;right=W/2+18;top=H-307;bottom=top-184
box(left,top,width,height,1,'Data Product Factory','<b>RULES:</b> DuckDB raw → curated → C360.<br/>Typed checks keep raw values; identity rules hold uncertain links for review.<br/><b>Outputs:</b> C360, lineage, counted quality report, YAML contract, holiday calendar.')
box(right,top,width,height,2,'Insight / NLP','<b>RULES:</b> reviewed metric compiler → bound SQL (never model-written SQL). Trends, rankings, counts, programmes; one-line summary computed from rows; unsupported → supported rephrasings.<br/><b>AI (optional):</b> Gemini picks a reviewed plan; local Whisper for audio.')
box(left,bottom,width,height,3,'Feature Store','<b>RULES:</b> one versioned offline/live definition: case, promise, contact features and nine bilingual hardship cues (POL-COLL-004 §4.2).<br/>Parity checked offline vs live.<br/><b>Outputs:</b> stored features and registry.')
box(right,bottom,width,height,4,'Decisioning','<b>RULES:</b> ordered action plan (restriction → representative → hardship programmes → promise → legal contact window → payment ask), work queue tiers, portfolio checks.<br/><b>AI:</b> logistic classifier flags possible hardship only.<br/><b><font color="#c2533d">HUMAN:</font></b> supervisor approves / edits / rejects; audit.')
arrow(left+width,top+height/2,right,top+height/2)
arrow(left+width,bottom+height/2,right,bottom+height/2)
c.setStrokeColor(teal);c.line(left+width/2,top,left+width/2,bottom+height)
c.setFillColor(teal);p=c.beginPath();p.moveTo(left+width/2,bottom+height);p.lineTo(left+width/2-4,bottom+height+7);p.lineTo(left+width/2+4,bottom+height+7);p.close();c.drawPath(p,fill=1,stroke=0)
c.setFillColor(HexColor('#e4eeea'));c.roundRect(24,18,W-48,69,6,fill=1,stroke=0)
text(32,81,W-64,'<b>Application:</b> Next.js → FastAPI. Pages: Overview with portfolio checks, Work queue, Customers, Ask, Agent brief, Supervisor review, Data and features. DuckDB analytics; SQLite sessions, reviews and append-only audit. No key means fully local.',9)
text(32,49,W-64,'<b>Governance across layers:</b> server-side roles and assigned-case access; every step cites policy and source record; protected fields and vulnerability never enter the model or queue order; no automatic customer contact.',9)
c.showPage();c.save()
assert len(PdfReader(OUT).pages)==1
print(OUT)
