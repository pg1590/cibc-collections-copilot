"""Train/evaluate a small local review-triage classifier on public note labels."""
import csv
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import duckdb
import joblib
import numpy as np
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import precision_score,recall_score,f1_score,balanced_accuracy_score,confusion_matrix
from sklearn.model_selection import GroupShuffleSplit
from app.features import TEXT_FEATURES,VERSION,text_features,build_store
from app.settings import DATASET,DB,MODEL,MODEL_REPORT,ROOT


def metrics(y,p):
    return {'precision':round(precision_score(y,p,zero_division=0),4),'recall':round(recall_score(y,p,zero_division=0),4),'f1':round(f1_score(y,p,zero_division=0),4),'balanced_accuracy':round(balanced_accuracy_score(y,p),4),'confusion_matrix':confusion_matrix(y,p,labels=[0,1]).tolist()}


def train():
    conn=duckdb.connect(str(DB));conn.execute("SET memory_limit='2GB'");conn.execute('SET threads=2')
    labels=list(csv.DictReader((DATASET/'labels/agent_notes_labels_public_500.csv').open()))
    texts=conn.execute('SELECT n.note_id,coalesce(i.customer_id,n.crm_customer_id),n.note_text,n.note_language,c.gender_code FROM curated.agent_notes n LEFT JOIN gold.crm_identity i USING(crm_customer_id) LEFT JOIN curated.customers c ON c.crm_customer_id=i.customer_id WHERE note_id IN ('+','.join('?' for _ in labels)+')',[r['note_id'] for r in labels]).fetchall()
    by_id={r[0]:r for r in texts}; used=[r for r in labels if r['note_id'] in by_id]
    groups=np.array([by_id[r['note_id']][1] for r in used]);y=np.array([int(r['label_hardship'] in ['clear','possible']) for r in used])
    X=np.array([[text_features(by_id[r['note_id']][2])[k] for k in TEXT_FEATURES] for r in used])
    train_idx,test_idx=next(GroupShuffleSplit(n_splits=1,test_size=.25,random_state=1590).split(X,y,groups))
    assert not set(groups[train_idx])&set(groups[test_idx])
    model=LogisticRegression(class_weight='balanced',random_state=1590,max_iter=1000).fit(X[train_idx],y[train_idx])
    pred=model.predict(X[test_idx]);baseline=DummyClassifier(strategy='most_frequent').fit(X[train_idx],y[train_idx]).predict(X[test_idx])
    groups_report={}
    # Restricted audit only: labels are not model inputs or serving outputs.
    for field,index in [('language',3),('gender_audit_only',4)]:
        values=[by_id[used[i]['note_id']][index] or 'unknown' for i in test_idx]
        groups_report[field]={}
        for v in sorted(set(values)):
            mask=np.array([x==v for x in values]); yy=y[test_idx][mask];pp=pred[mask]
            groups_report[field][v]={'n':int(mask.sum()),'positive_n':int(yy.sum()),'recall':round(recall_score(yy,pp,zero_division=0),4) if yy.sum() else None}
    report={'name':'Financial hardship review triage','version':VERSION,'algorithm':'class-balanced logistic regression','target':'public note label clear/possible versus none','input_features':TEXT_FEATURES,'train_rows':len(train_idx),'test_rows':len(test_idx),'missing_label_records':len(labels)-len(used),'split':'Customer-grouped heldout split, seed 1590','heldout':metrics(y[test_idx],pred),'majority_baseline':metrics(y[test_idx],baseline),'restricted_fairness_audit':groups_report,'limitations':['Small synthetic labelled set; no demonstrated production or business uplift.','Financial-cue-only classifier misses unsupported wording and nonfinancial hardship.','Rule cues are binary; score is a review aid, not an eligibility decision.','No protected fields or unrestricted text are model inputs. Fairness groups are evaluation-only.','Low support groups cannot establish fairness.'],'coefficients':dict(zip(TEXT_FEATURES,model.coef_[0].round(4).tolist()))}
    # Preserve heldout estimator; do not silently refit before reporting test results.
    joblib.dump({'model':model,'features':TEXT_FEATURES,'version':VERSION},MODEL)
    MODEL_REPORT.write_text(json.dumps(report,indent=2))
    parity=build_store(conn,ROOT/'data/features-report.json');conn.execute('CHECKPOINT');conn.close()
    public={k:v for k,v in report.items() if k!='restricted_fairness_audit'}
    (ROOT/'docs/model-evaluation.md').write_text('# Local model evaluation\n\n```json\n'+json.dumps(public,indent=2)+'\n```\n\nFeature parity:\n```json\n'+json.dumps(parity['parity'],indent=2)+'\n```\n')
    print(json.dumps({'heldout':report['heldout'],'baseline':report['majority_baseline'],'parity':parity['parity']},indent=2))

if __name__=='__main__':train()
