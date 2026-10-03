# Accuracy and company implementation readiness audit

Audit date: 3 October 2026. Dataset snapshot: 28 September 2026. This review records measured evidence and required follow-up; it does not certify production readiness. The serving model and question engine were not changed by this audit.

## What the release specifies

The authoritative local sources are the release README, `data/metric_definitions.csv`, `data/benchmark_questions.csv`, `labels/benchmark_dev_answers.csv`, public NLP labels, current policy documents, `data/hardship_programs.csv`, `data/qa_checklist.csv`, and the build-phase instructions.

| Source | What is available | What it establishes |
|---|---|---|
| Metric definitions | 15 metrics with formulas, grain, time basis, filters, units, owners and examples | The intended business meaning of analytic results |
| Benchmark | 35 questions: 21 development and 14 test | Questions the system must answer or refuse |
| Development references | 21 answers, including 12 numeric SQL references | A public check of those specific questions; test answers remain hidden |
| Public note labels | 500 notes with hardship, evidence, payment promises, disputes, contact restrictions and summary labels | Development/evaluation targets for supported NLP outputs |
| Public transcript labels | 500 calls with evidence timestamps, summaries and QA labels | Targets for transcript extraction, summary and call-quality evaluation |
| Hardship programmes | 18 rows with versions, effective dates, product and eligibility criteria, terms and approval levels | Source rules to check when suggesting options; rows are not necessarily 18 distinct current programmes |
| QA checklist | 10 weighted checks and critical flags | Expected call-review behavior and evidence requirements |
| Policies and contracts | Versioned synthetic documents, including current hardship policy and a contact data contract | Source-backed behavior and data-quality expectations for this fictional bank |

The required submitted reports are the data contract, counted data-quality report, generated benchmark CSV, architecture, demo and deck. These sources do not provide CIBC production acceptance thresholds, representative real customer labels, a load-test target or a measured business uplift for our implementation.

## Current accuracy evidence

- All 12 numeric development questions match the released SQL references within tolerance.
- All 35 released benchmark rows were generated, including six refusals and no unresolved results. Generation is not proof that all 35 answers are correct.
- The saved classifier reproduces its original 126-note heldout evaluation: precision 89.29%, recall 65.79%, F1 75.76%, balanced accuracy 81.19%.
- There is no overlap of resolved customer IDs in the original training and test groups. Unresolved duplicate identities can still limit this protection.
- Python training and SQL serving text cues were compared on all 500 labelled notes: zero mismatches.
- Offline/live feature recomputation was checked on 100 customers: zero mismatches. This checks implementation consistency, not label accuracy or completeness.

### Additional classifier check

An exploratory five-fold evaluation used `StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=1590)`, grouping by the same resolved customer IDs as training. Each fold trained a fresh class-balanced logistic regression with seed 1590 and `max_iter=1000` on the six existing financial cues. No customer's resolved ID overlapped within a fold's training and test sets. The saved serving model was not overwritten.

| Fold | Test notes | Positive labels | Precision | Recall | F1 | Balanced accuracy |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 99 | 33 | 95.65% | 66.67% | 78.57% | 82.58% |
| 2 | 100 | 26 | 94.74% | 69.23% | 80.00% | 83.94% |
| 3 | 100 | 29 | 87.50% | 72.41% | 79.25% | 84.09% |
| 4 | 101 | 27 | 85.00% | 62.96% | 72.34% | 79.45% |
| 5 | 100 | 31 | 95.65% | 70.97% | 81.48% | 84.76% |

Pooled out-of-fold results: precision **91.74%**, recall **68.49%**, F1 **78.43%**, balanced accuracy **82.98%**. Counts: 100 true positives, 46 false negatives, 9 false positives and 345 true negatives.

This evaluation reuses the same public development set. It is not an independent production test, and it does not establish calibration, fairness, future-data performance or the accuracy of the complete brief workflow. Roughly one-third of positive reference labels were missed. A low score must not be treated as evidence that no hardship exists.

## Planner gaps found outside the released numeric references

The audit ran the example questions in all 15 metric-definition rows through the current engine. These examples expose gaps that the existing development benchmark does not cover:

| Example question | Current behavior | Required correction |
|---|---|---|
| Promise-kept rate this month by queue | Returns an overall rate | Honor the requested grouping or explicitly request clarification |
| Broken promise rate by tier | Returns an overall rate | Resolve the business meaning and source of tier, or explicitly request clarification |
| PTP rate by agent site | Returns a channel breakdown | Honor site grouping; never substitute a different grouping silently |
| Card delinquency rate by bucket today | Returns a product breakdown | Honor bucket grouping and validate the denominator |
| How much did we collect in September? | Returns an out-of-scope refusal | Recognize the collections metric and clarify its payment source/definition; do not equate all collections with payments against promises |
| Attempts per case by bucket | Returns an out-of-scope refusal | Recognize the metric and apply its documented period and denominator |
| Roll rate from 1-30 to 31-60 this month by product | Returns an out-of-scope refusal | Explain that required September endpoints are unavailable; the released account snapshots end in June 2026 |
| Cure rate for cases opened in August | Calculates cases open at period start | Clarify opened-during-period versus open-at-start cohorts before answering |

The cure metric's example wording and its formal denominator can lead to different interpretations. Specific question wording, reference SQL and documented metric semantics must be reconciled; an ambiguous cohort must not be chosen silently. Counts of write-offs and the write-off rate must also remain distinct outputs.

## Relevant agent-assist improvements

The current brief cites policies and proposes a generic next step. It does not yet apply individual hardship programme eligibility and terms. Programme suggestions should check effective dates, product, DPD, time on book, previous use, recorded exclusions and approval level. Missing inputs must be stated and routed for confirmation, not guessed. Any option remains a suggestion for a human reviewer, not an automatic eligibility decision.

The release also supports checking financial hardship evidence, promised amounts/dates, stated next steps, disputes and contact restrictions. Expand only the outputs that strengthen the selected agent-assist use case, and evaluate each against the applicable public labels and evidence. Protected fields remain excluded from decisions.

## Scale evidence and production gaps

The current pipeline covers 31 source tables totaling **68,162,322 raw rows**, including history queried from partitioned Parquet views. It produces 1,014,631 golden customer records. This demonstrates handling the release's data volume, not an accurate one-to-one recovery of the underlying million people or performance under concurrent users.

| Area | Current implementation | Company implementation path |
|---|---|---|
| Refresh | Manual full snapshot build | Scheduled incremental ingestion, late-arrival handling, quality gates and freshness monitoring |
| Analytics | Local DuckDB and Parquet | Managed shared analytics storage; retain reviewed metric definitions and lineage |
| Reviews and sessions | Local SQLite | Shared transactional storage, backups, recovery and concurrent-write validation |
| Customer features | Batch store plus live recomputation | Versioned, precomputed customer features refreshed when inputs change; verify training/serving consistency |
| API | One local FastAPI service | Independently deployable instances, controlled database access, measured capacity and request limits |
| Model | Six-cue classifier on 500 synthetic labels | Broader representative labels, error analysis, calibration, approved review thresholds and drift monitoring |
| Customer matching | Conservative rules and quarantine | Independently labelled identity pairs, measured false-match/missed-match rates and supervised resolution |
| Security | Demo role accounts and backend authorization | Company identity integration, managed secrets and operational access/audit controls |

No concurrency, p95 latency, availability or recovery target has been measured or approved. Hosting the existing application alone would not resolve these gaps.

## Order of work

1. Correct or clarify mismatched metric grouping, period, cohort and denominator requests; add semantic checks alongside the public references.
2. Improve financial hardship recall through labelled error analysis and evaluate the complete brief, evidence and contact-rule workflow.
3. Suggest policy-backed support options with explicit eligibility checks and missing-data handling.
4. Measure customer lookup, questions and brief generation under concurrent use on stated hardware; report p50/p95, errors and memory without claiming production capacity.
5. Add repeatable deployment packaging and persistent review storage. Treat incremental ingestion, company identity, backups and monitored model rollout as requirements for a company pilot.

Business success should measure factual errors, missed hardship, policy violations, supervisor corrections, time per case and support outcomes. The company must approve target thresholds and validate real-data performance before operational use.
