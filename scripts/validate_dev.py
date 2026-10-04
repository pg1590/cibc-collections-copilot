"""Independent dev validation; gold references never enter runtime planning."""
import csv,json,re,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import duckdb
from app.insights import InsightEngine
from app.settings import DATASET,DB,ROOT


def validate():
    questions={r['question_id']:r for r in csv.DictReader((DATASET/'data/benchmark_questions.csv').open(encoding='utf-8-sig',newline=''))}
    engine=InsightEngine(DB,DATASET);c=duckdb.connect(str(DB),read_only=True);c.execute('SET threads=2')
    # Gold SQL from organizer is used only in this validation executable.
    c.execute("SET search_path='curated'")
    checks=[]
    for row in csv.DictReader((DATASET/'labels/benchmark_dev_answers.csv').open(encoding='utf-8-sig',newline='')):
        result=engine.answer(questions[row['question_id']]['question_text']);sql=row['gold_sql_reference']
        check={'question_id':row['question_id'],'execution_error':result.get('reason')=='execution_error','refused':result['refused']}
        if sql:
            cursor=c.execute(sql);expected=cursor.fetchall();observed=result['rows']
            values=[tuple(x.values()) for x in observed]
            # Engine may return extra counts/metadata; compare the required gold cells.
            tolerance=1.0 if 'CAD' in questions[row['question_id']]['tolerance'] else .5
            if '±0.1' in questions[row['question_id']]['tolerance']:tolerance=.1
            if '±0.05' in questions[row['question_id']]['tolerance']:tolerance=.05
            if questions[row['question_id']]['tolerance']=='exact':tolerance=0
            good=len(expected)==len(values)
            diffs=[]
            for e,v in zip(expected,values):
                for i,x in enumerate(e):
                    y=v[i] if len(v)>i else None
                    match=abs(float(x)-float(y))<=tolerance if isinstance(x,(int,float)) and isinstance(y,(int,float)) else x==y
                    if not match:good=False;diffs.append({'expected':x,'observed':y})
            check.update(numeric_reference_match=good,differences=diffs,reference_rows=len(expected))
        else:check['manual_reference']=row['gold_answer'];check['answer']=result['answer'];check['sources']=result['sql_or_sources']
        checks.append(check)
    c.close();(ROOT/'data/dev-validation.json').write_text(json.dumps(checks,indent=2,default=str),encoding='utf-8')
    print(json.dumps([{k:v for k,v in x.items() if k not in ['manual_reference','answer','sources']} for x in checks],indent=2))

if __name__=='__main__':validate()
