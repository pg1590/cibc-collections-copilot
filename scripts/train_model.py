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
from sklearn.model_selection import GroupShuffleSplit,StratifiedGroupKFold
from app.features import TEXT_FEATURES,VERSION,text_features,build_store
from app.settings import DATASET,DB,MODEL,MODEL_REPORT,ROOT


def metrics(y,p):
    return {'precision':round(precision_score(y,p,zero_division=0),4),'recall':round(recall_score(y,p,zero_division=0),4),'f1':round(f1_score(y,p,zero_division=0),4),'balanced_accuracy':round(balanced_accuracy_score(y,p),4),'confusion_matrix':confusion_matrix(y,p,labels=[0,1]).tolist()}


def cross_validate(X,y,groups,seeds=(0,1,2,3,4),folds=5):
    """Customer-grouped stratified k-fold repeated over seeds: mean/std across folds plus pooled counts."""
    found={'model':[],'rules_only':[]};pooled={'model':[],'rules_only':[]};truth=[]
    for seed in seeds:
        for tr,te in StratifiedGroupKFold(n_splits=folds,shuffle=True,random_state=seed).split(X,y,groups):
            assert not set(groups[tr])&set(groups[te])
            model=LogisticRegression(class_weight='balanced',random_state=1590,max_iter=1000).fit(X[tr],y[tr])
            for kind,p in [('model',model.predict(X[te])),('rules_only',X[te].any(1).astype(int))]:
                found[kind].append(metrics(y[te],p));pooled[kind].append(p)
            truth.append(y[te])
    truth=np.concatenate(truth);out={'protocol':f'StratifiedGroupKFold({folds}) by customer, shuffled, seeds {list(seeds)}; mean/std over {folds*len(seeds)} folds; pooled counts over all folds','rules_only_definition':'positive when any cue fires'}
    for kind in found:
        out[kind]={k:{'mean':round(float(np.mean([m[k] for m in found[kind]])),4),'std':round(float(np.std([m[k] for m in found[kind]],ddof=1)),4)} for k in ['precision','recall','f1','balanced_accuracy']}
        out[kind]['pooled']=metrics(truth,np.concatenate(pooled[kind]))
    return out


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
    cv=cross_validate(X,y,groups);rules=X[test_idx].any(1).astype(int)
    groups_report={}
    # Restricted audit only: labels are not model inputs or serving outputs.
    for field,index in [('language',3),('gender_audit_only',4)]:
        values=[by_id[used[i]['note_id']][index] or 'unknown' for i in test_idx]
        groups_report[field]={}
        for v in sorted(set(values)):
            mask=np.array([x==v for x in values]); yy=y[test_idx][mask];pp=pred[mask]
            groups_report[field][v]={'n':int(mask.sum()),'positive_n':int(yy.sum()),'recall':round(recall_score(yy,pp,zero_division=0),4) if yy.sum() else None}
    report={'name':'Financial hardship review triage','version':VERSION,'algorithm':'class-balanced logistic regression','target':'public note label clear/possible versus none','input_features':TEXT_FEATURES,'train_rows':len(train_idx),'test_rows':len(test_idx),'missing_label_records':len(labels)-len(used),'split':'Customer-grouped heldout split, seed 1590','heldout':metrics(y[test_idx],pred),'heldout_rules_only':metrics(y[test_idx],rules),'majority_baseline':metrics(y[test_idx],baseline),'cross_validation':cv,'restricted_fairness_audit':groups_report,'limitations':['Small synthetic labelled set; no demonstrated production or business uplift.','Cue-only classifier misses unsupported wording, typos and hardship not covered by POL-COLL-004 s4.2 cue phrases.','Cues were designed with error analysis on training notes of the seed-1590 split; CV folds include those notes, so CV is optimistic. See docs/hardship-detector-evaluation.md.','The regularised model can score a note with a single cue below 0.5; serving also flags any cue sentence for review.','Rule cues are binary; score is a review aid, not an eligibility decision.','No protected fields or unrestricted text are model inputs. Fairness groups are evaluation-only.','Low support groups cannot establish fairness.'],'coefficients':dict(zip(TEXT_FEATURES,model.coef_[0].round(4).tolist()))}
    # Preserve heldout estimator; do not silently refit before reporting test results.
    joblib.dump({'model':model,'features':TEXT_FEATURES,'version':VERSION},MODEL)
    MODEL_REPORT.write_text(json.dumps(report,indent=2))
    parity=build_store(conn,ROOT/'data/features-report.json');conn.execute('CHECKPOINT');conn.close()
    public={k:v for k,v in report.items() if k!='restricted_fairness_audit'}
    (ROOT/'docs/model-evaluation.md').write_text('# Local model evaluation\n\n```json\n'+json.dumps(public,indent=2)+'\n```\n\nFeature parity:\n```json\n'+json.dumps(parity['parity'],indent=2)+'\n```\n')
    print(json.dumps({'heldout':report['heldout'],'heldout_rules_only':report['heldout_rules_only'],'cv_model':{k:cv['model'][k] for k in ['precision','recall','f1']},'cv_rules_only':{k:cv['rules_only'][k] for k in ['precision','recall','f1']},'baseline':report['majority_baseline'],'parity':parity['parity']},indent=2))

if __name__=='__main__':train()
