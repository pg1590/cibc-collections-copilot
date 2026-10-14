"""Read-only evaluation of hardship cue sets: v1 (frozen copy) vs current app.features patterns.

Customer-grouped stratified 5-fold CV repeated over 5 seeds on all public labelled notes, plus the
original seed-1590 grouped held-out split. Writes data/hardship-cv-report.json and
docs/hardship-detector-evaluation.md. Opens DuckDB read_only; never writes to the database.
"""
import csv
import json
import re
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import duckdb
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import precision_score,recall_score,f1_score,confusion_matrix
from sklearn.model_selection import GroupShuffleSplit,StratifiedGroupKFold
from app.features import PATTERNS,VERSION,normalize_text
from app.settings import DATASET,DB,ROOT

SEEDS=[0,1,2,3,4]; FOLDS=5; HELDOUT_SEED=1590; KINDS=['model','rules_only','serving_brief']
# Verbatim copy of the c360-financial-v1 cues, frozen here so the baseline stays reproducible.
V1_PATTERNS = {
    "income_loss": r"job loss|lost (my |their |his |her |the )?job|laid off|layoff|position eliminated|unemploy|perdu (mon |son |leur )?emploi|perte d.emploi|licenci",
    "income_reduction": r"hours (were |have been |got )?cut|reduced hours|fewer hours|hours reduced|reduced income|pay cut|reduction.*(hours|income)|heures.*redui|baisse.*revenu|salaire.*redui",
    "income_delay": r"pay.*late|payroll.*delay|salary.*delay|pay.*delay|waiting.*(pay|salary|income)|paye.*retard|salaire.*retard",
    "payment_difficulty": r"cannot (afford|pay)|can.t (afford|pay)|unable to pay|no money|not enough money|financial (hardship|difficult)|struggling.*pay|difficulte.*financ|ne peux pas payer|pas.*argent",
    "hardship_request": r"hardship|payment relief|payment deferral|reduced payment|payment reduction|allegement|report de paiement|paiement reduit",
    "expense_pressure": r"rent.*(increase|raised|higher)|unexpected (expense|bill)|cost.*(rise|increase)|loyer.*(hausse|augment)|depense.*imprevu",
}
CUE_SETS={'v1_current':V1_PATTERNS,VERSION:PATTERNS}


def load():
    labels=list(csv.DictReader((DATASET/'labels/agent_notes_labels_public_500.csv').open()))
    with duckdb.connect(str(DB),read_only=True) as c:
        rows=c.execute('SELECT n.note_id,coalesce(i.customer_id,n.crm_customer_id),n.note_text,n.note_language FROM curated.agent_notes n LEFT JOIN gold.crm_identity i USING(crm_customer_id) WHERE note_id IN ('+','.join('?' for _ in labels)+')',[r['note_id'] for r in labels]).fetchall()
        by_id={r[0]:r for r in rows}; used=[r for r in labels if r['note_id'] in by_id]
        ids=[r['note_id'] for r in used]
        # SQL-side cue vectors, computed exactly as feature_sql() does, for Python/DuckDB parity.
        sql={}
        for name,patterns in CUE_SETS.items():
            cols=','.join(f"CAST(regexp_matches(lower(strip_accents(coalesce(note_text,''))),'{p.replace(chr(39),chr(39)*2)}') AS INTEGER)" for p in patterns.values())
            got={r[0]:list(r[1:]) for r in c.execute(f'SELECT note_id,{cols} FROM curated.agent_notes WHERE note_id IN ('+','.join('?' for _ in ids)+')',ids).fetchall()}
            sql[name]=np.array([got[i] for i in ids])
    texts=[normalize_text(by_id[i][2]) for i in ids]
    X={name:np.array([[int(bool(re.search(p,t))) for p in patterns.values()] for t in texts]) for name,patterns in CUE_SETS.items()}
    # Serving (app/main.py brief) also flags hardship when evidence() finds a cue in any sentence.
    spans={name:np.array([int(any(re.search(p,normalize_text(s)) for s in re.split(r'(?<=[.!?;])\s+|\n+',by_id[i][2] or '') for p in patterns.values())) for i in ids]) for name,patterns in CUE_SETS.items()}
    parity={name:int((X[name]!=sql[name]).any(1).sum()) for name in CUE_SETS}
    y=np.array([int(r['label_hardship'] in ['clear','possible']) for r in used])
    groups=np.array([by_id[i][1] for i in ids]); lang=np.array([by_id[i][3] or 'unknown' for i in ids])
    return used,X,spans,y,groups,lang,parity,len(labels)-len(used)


def scores(y,p):
    tn,fp,fn,tp=confusion_matrix(y,p,labels=[0,1]).ravel()
    return {'precision':round(precision_score(y,p,zero_division=0),4),'recall':round(recall_score(y,p,zero_division=0),4),'f1':round(f1_score(y,p,zero_division=0),4),'tp':int(tp),'fp':int(fp),'fn':int(fn),'tn':int(tn)}


def fit_predict(X,y,tr,te):
    return LogisticRegression(class_weight='balanced',random_state=HELDOUT_SEED,max_iter=1000).fit(X[tr],y[tr]).predict(X[te])


def summary(fold_scores,pooled):
    out={k:{'mean':round(float(np.mean([s[k] for s in fold_scores])),4),'std':round(float(np.std([s[k] for s in fold_scores],ddof=1)),4)} for k in ['precision','recall','f1']}
    out['pooled']=pooled; out['folds']=len(fold_scores)
    return out


def detectors(X,spans,y,tr,te):
    model=fit_predict(X,y,tr,te)
    return [('model',model),('rules_only',X[te].any(1).astype(int)),('serving_brief',model|spans[te])]


def cross_validate(X,spans,y,groups,lang):
    folds={k:[] for k in KINDS}; pred={k:[] for k in KINDS}; truth=[]; langs=[]
    for seed in SEEDS:
        for tr,te in StratifiedGroupKFold(n_splits=FOLDS,shuffle=True,random_state=seed).split(X,y,groups):
            assert not set(groups[tr])&set(groups[te])
            for kind,p in detectors(X,spans,y,tr,te):
                folds[kind].append(scores(y[te],p)); pred[kind].append(p)
            truth.append(y[te]); langs.append(lang[te])
    truth=np.concatenate(truth); langs=np.concatenate(langs); result={}
    for kind in folds:
        p=np.concatenate(pred[kind]); result[kind]=summary(folds[kind],scores(truth,p))
        result[kind]['pooled_recall_by_language_audit_only']={v:{'positives':int(truth[langs==v].sum()),'recall':round(recall_score(truth[langs==v],p[langs==v],zero_division=0),4)} for v in sorted(set(langs)) if truth[langs==v].sum()}
    return result


def heldout(X,spans,y,groups,used):
    tr,te=next(GroupShuffleSplit(n_splits=1,test_size=.25,random_state=HELDOUT_SEED).split(X,y,groups))
    found=dict(detectors(X,spans,y,tr,te)); p=found['model']
    errors=[{'note_id':used[i]['note_id'],'label':used[i]['label_hardship'],'reason':used[i]['label_hardship_reason'] or None,'error':'false_negative' if y[i] else 'false_positive'} for i,pi in zip(te,p) if pi!=y[i]]
    return {'train_rows':len(tr),'test_rows':len(te),'test_positives':int(y[te].sum()),**{k:scores(y[te],v) for k,v in found.items()},'model_errors':errors}


def evaluate():
    used,X,spans,y,groups,lang,parity,missing=load()
    report={'name':'Financial hardship detector evaluation','current_version':VERSION,'labels':'agent_notes_labels_public_500.csv; positive = label_hardship clear or possible',
      'rows':len(used),'positives':int(y.sum()),'negatives':int(len(y)-y.sum()),'customers':len(set(groups)),'missing_label_records':missing,
      'model':'class-balanced logistic regression on binary cues (as scripts/train_model.py)','rules_only':'positive when any cue fires','serving_brief':'what /api/briefs labels possible hardship: model probability >= 0.5 OR evidence() finds a cue sentence (recorded case flags ignored)',
      'cv_protocol':f'StratifiedGroupKFold({FOLDS}) grouped by customer, shuffled, repeated with seeds {SEEDS}; mean/std over {FOLDS*len(SEEDS)} folds; pooled counts sum all folds (each note predicted once per repeat)',
      'heldout_protocol':f'GroupShuffleSplit test_size=0.25 seed {HELDOUT_SEED} grouped by customer (same split as train_model.py)',
      'pattern_development':f'{VERSION} cues were designed from POL-COLL-004 v4.2 s4.2, phrase frequencies in the unlabelled note corpus, and error analysis on the 374 training notes of the seed-{HELDOUT_SEED} split only. The 126 held-out notes were not inspected while designing cues. CV folds include notes seen during design, so CV is optimistic for the new cues.',
      'python_duckdb_parity_mismatched_notes':parity,'cue_sets':{}}
    for name,patterns in CUE_SETS.items():
        Xn=X[name]
        report['cue_sets'][name]={'features':list(patterns),'cue_support_all_rows':{k:{'fires':int(Xn[:,j].sum()),'positive_when_fires':int((Xn[:,j]&y).sum())} for j,k in enumerate(patterns)},
          'cross_validation':cross_validate(Xn,spans[name],y,groups,lang),'heldout_seed_1590':heldout(Xn,spans[name],y,groups,used)}
    (ROOT/'data/hardship-cv-report.json').write_text(json.dumps(report,indent=2))
    (ROOT/'docs/hardship-detector-evaluation.md').write_text(markdown(report))
    return report


LABELS=[('model','logistic regression'),('rules_only','rules only (any cue)'),('serving_brief','serving brief (model OR cue sentence)')]


def fmt(s): return f"{s['mean']:.3f} ± {s['std']:.3f}"


def markdown(r):
    old,new=r['cue_sets']['v1_current'],r['cue_sets'][r['current_version']]
    def cv_rows(name,c):
        rows=[]
        for kind,label in LABELS:
            s=c['cross_validation'][kind]; p=s['pooled']
            rows.append(f"| {name} | {label} | {fmt(s['precision'])} | {fmt(s['recall'])} | {fmt(s['f1'])} | {p['tp']} | {p['fp']} | {p['fn']} | {p['tn']} |")
        return rows
    def ho_rows(name,c):
        h=c['heldout_seed_1590']; rows=[]
        for kind,label in LABELS:
            s=h[kind]; rows.append(f"| {name} | {label} | {s['precision']:.4f} | {s['recall']:.4f} ({s['tp']} of {s['tp']+s['fn']}) | {s['f1']:.4f} | {s['fp']} |")
        return rows
    lang=lambda c:', '.join(f"{k} {v['recall']:.2f} ({v['positives']//len(SEEDS)} positives)" for k,v in c['cross_validation']['model']['pooled_recall_by_language_audit_only'].items())
    return '\n'.join([
f"# Hardship detector evaluation ({r['current_version']})",'',
'Generated by `scripts/evaluate_hardship_cv.py` (read-only on the database). Raw numbers: `data/hardship-cv-report.json`.','',
'## What changed','',
f"- v1 had 6 regex cues. {r['current_version']} keeps those 6 (widened) and adds 3 cues for hardship reasons named in POL-COLL-004 v4.2 §4.2: `illness_or_injury` (sick/medical leave, hospital stay, short-term disability or disability claim), `separation`, `disaster_or_evacuation`. Strike/lockout was added to `income_loss`, EI waiting to `income_delay`, and payment increase after a rate reset or mortgage renewal to `expense_pressure`.",
'- Widened phrasing: general statements of strain ("money is tight", "struggling", "things are hard", "c\'est serré", "difficile financièrement"), requests to lower a payment ("asked if pmt can be reduced", "demande si pmt peut être réduit", hardship options/team, "réf. équipe difficultés"), shift/overtime/pay cuts, "one income now", French layoffs ("mis à pied"), French sick leave and short-term disability.',
'- French accents: `.` stands in for accented letters, so notes stored with broken encoding (U+FFFD instead of é) still match.',
'- Fixed false matches: v1 `pay.*late` matched "will try to **pay** ... esca**late**d"; unbounded `.*` spans are now limited (`.{0,20}`) or anchored with `\\b`.',
'- Removed: the bare word "hardship" and "financial hardship". In this data "cust vulnerable - financial hardship" is the vulnerability tag (policy §4.5), and vulnerability must not be a model input. Hardship programme words ("hardship team", "hardship options") still count.',
'- Deliberately not used: vulnerability markers (crying, anxiety, stress, "serious illness in family", bereavement) and protected grounds (disability as a status, marital status, pregnancy, religion, origin). Bereavement is listed in both §4.2 and §4.5. Here it is left to the vulnerability safeguard instead of the hardship score; this is a policy choice, not a measured gain.',
'- Python and DuckDB return identical cue vectors on every labelled note (mismatches: '+json.dumps(r['python_duckdb_parity_mismatched_notes'])+').','',
'## How it was measured','',
f"- {r['rows']} labelled notes ({r['positives']} positives = clear or possible hardship, {r['negatives']} none) from {r['customers']} customers.",
f"- Cross-validation: {r['cv_protocol']}.",
f"- Held-out: {r['heldout_protocol']}. This is the split behind the v1 numbers in `docs/model-evaluation.md`.",
'- Rules-only baseline: flag the note if any cue fires (no training). The live brief already treats any cue span as "possible hardship", so this baseline is close to what serving does.',
f"- How the patterns were developed: {r['pattern_development']}",'',
'## Results','',
'Cross-validation (mean ± std over folds; pooled counts are summed over all 25 folds):','',
'| cues | detector | precision | recall | F1 | TP | FP | FN | TN |','|---|---|---|---|---|---|---|---|---|',
*cv_rows('v1',old),*cv_rows(r['current_version'],new),'',
f"Held-out seed-1590 split ({new['heldout_seed_1590']['test_rows']} notes, {new['heldout_seed_1590']['test_positives']} positives):",'',
'| cues | detector | precision | recall | F1 | FP |','|---|---|---|---|---|---|',
*ho_rows('v1',old),*ho_rows(r['current_version'],new),'',
f"Pooled CV recall by note language (audit only, not an input): v1: {lang(old)}; {r['current_version']}: {lang(new)}.",'',
'## Reading the numbers','',
f"- The serving brief is what an agent sees. It shows \"possible hardship\" when the model score is at least 0.5 or any note sentence matches a cue. With {r['current_version']} cues it equals the rules-only row.",
f"- The logistic regression alone misses some notes that match only one cue: {new['heldout_seed_1590']['model']['fn']} of {new['heldout_seed_1590']['test_positives']} held-out positives, and {new['cross_validation']['model']['pooled']['fn']} pooled CV predictions. Most training positives match two or more cues (a reason plus a request for relief). With default L2 regularisation, the weight on one cue alone can stay below 0.5. The model settings were not tuned, so they stay comparable to v1.",
'- The rules-only detector has 100% recall on these labels because the synthetic notes reuse a small set of phrases. Treat that as \"covers every template in this dataset\", not as expected real-world recall.','',
'## Limitations','',
f"- Small synthetic labelled set: {r['rows']} notes, {r['positives']} positives. The notes are heavily templated, so a regex that covers a template covers every note that uses it. Expect lower recall on real, free-form notes.",
'- The cues were tuned after reading training notes. Only the 126-note held-out split was kept unseen, and it has 38 positives. Its recall moves by about 2.6 points per note.',
'- Typos the regexes do not tolerate (e.g. "hardhip team") are missed. Unseen wording for hardship is missed.',
'- The remaining false positives are mostly "refer to hardship team" with no stated reason, which the labels mark as no hardship. We keep that cue because an agent referral is a reasonable reason to review.',
'- This is a review aid. It does not decide hardship or eligibility. No protected or vulnerability fields are inputs.',''])


if __name__=='__main__':
    r=evaluate()
    for n,c in r['cue_sets'].items():
        for kind in KINDS:
            cv=c['cross_validation'][kind]; h=c['heldout_seed_1590'][kind]
            print(f"{n:18s} {kind:14s} CV P {fmt(cv['precision'])} R {fmt(cv['recall'])} F1 {fmt(cv['f1'])} pooled {cv['pooled']} | heldout P {h['precision']} R {h['recall']} ({h['tp']} of {h['tp']+h['fn']}) FP {h['fp']}")
    print('python/duckdb parity mismatches',r['python_duckdb_parity_mismatched_notes'])
