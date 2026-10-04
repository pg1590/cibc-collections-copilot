"""Generate benchmark CSV through the same engine as /api/ask; no gold lookup."""
import argparse
import csv
import json
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.runtime import answer as runtime_answer
from app.settings import DATASET,DB,ROOT


def run():
    p=argparse.ArgumentParser();p.add_argument('--questions',type=Path,default=DATASET/'data/benchmark_questions.csv');p.add_argument('--extra',type=Path,action='append',default=[]);p.add_argument('--output',type=Path,default=ROOT/'submission/benchmark_answers.csv');p.add_argument('--db',type=Path,default=DB);p.add_argument('--local',action='store_true',help='Disable optional Gemini calls for an explicit local baseline.');args=p.parse_args()
    if args.local:os.environ['COPILOT_GEMINI_ENABLED']='0'
    questions={}
    for file in [args.questions,*args.extra]:
        with file.open(encoding='utf-8-sig',newline='') as f:
            for row in csv.DictReader(f):
                if row['question_id'] in questions and questions[row['question_id']]['question_text']!=row['question_text']:raise ValueError('Conflicting question IDs')
                questions[row['question_id']]=row
    args.output.parent.mkdir(parents=True,exist_ok=True);errors=[];refused=0
    with args.output.open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=['question_id','answer','sql_or_sources','refused'],lineterminator='\n');writer.writeheader()
        for key,row in questions.items():
            answer=runtime_answer(row['question_text'],db_path=args.db,dataset_root=DATASET)
            writer.writerow({'question_id':key,'answer':answer['answer'],'sql_or_sources':answer['sql_or_sources'],'refused':str(answer['refused']).lower()})
            refused+=answer['refused']
            if answer.get('reason') in ['execution_error','clarification_required']:errors.append({'question_id':key,'reason':answer['reason'],'detail':answer['answer']})
            print(key,answer.get('reason') or 'answered',answer['execution_ms'],'ms',flush=True)
    status={'questions':len(questions),'refused':refused,'unresolved':errors,'output':str(args.output.relative_to(ROOT)) if args.output.is_relative_to(ROOT) else str(args.output)}
    (ROOT/'data/benchmark-status.json').write_text(json.dumps(status,indent=2),encoding='utf-8')
    print(json.dumps(status,indent=2))
    if errors:sys.exit(2)


if __name__=='__main__':run()
