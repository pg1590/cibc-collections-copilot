# Local question engine review

Codex implemented the engine after the assigned Claude Opus 5.5 run timed out at 25 minutes without delivering files. That attempt is not credited as completed engineering. The earlier actual Opus plan review and completed frontend source remain credited separately.

`app/insights.py` uses fixed metric query templates with bound dates and grouping choices from a controlled catalog. It never executes user SQL, reads user-supplied files or looks up benchmark answer IDs. The same `answer(question)` method serves HTTP and benchmark export. Runtime DuckDB opens read-only, disables external access and allows only the trusted dataset data folder for Parquet views. Policy retrieval uses BM25 and explicit authoritative topic routing, excluding superseded and future-effective documents. Transcript summaries cite the actual most recent recorded call and exact turn timestamps. Original language is retained.

Supported metric families cover the release's 15 definitions: roll, cure, promise-kept, broken promise, RPC, PTP, cost/contact, cost/RPC, collected amount, hardship, delinquency, write-off, average DPD, contacts/case and payroll delay. Specific supported comparison plans include randomized champion/challenger, randomized agent-certification pilot, late-fee dispute intervals, and historical March-to-June roll. The planner supports common paraphrases and explicit month ranges; arbitrary combinations and generic historical roll periods still require clarification. Policy answers are extracts, not generated legal advice. Requests for bulk PII, protected-attribute decisions/disclosure, geographic hardship exclusion, arbitrary commands and unrelated questions are refused.

## Measured verification

All 35 released benchmark rows generated automatically, with six refusals and no unresolved or execution-error rows. All 12 numeric dev questions matched the organizer's SQL reference within their supplied tolerance, including reported categories/counts. Document and transcript answers were inspected against the public reference and cited source content. This is local validation, not an organizer score; hidden test and future extra questions remain unverified.

Validation caught and fixed three material issues: shared read-only connections could not reconfigure external-access paths once disabled; roll-share wording initially selected delinquency; and bulk export wording with identifiers before `every customer` bypassed the first refusal regex. Dedicated security/precedence tests now cover them. Current policy routing corrected the consent section and incident documents without section headings. No benchmark answer was edited manually.

## Limits

The no-API runtime is a bounded local planner. Unsupported intents ask for clarification rather than fabricate results. Comparative pilot estimates are restricted to the randomized subset and do not establish general production causality. Identity matching uses rule scores and conservative quarantine, with no independently labelled precision evaluation. Numeric metrics retain reported buckets to reproduce the organizer's definitions, while DPD/bucket disagreement is separately counted in the quality report.
