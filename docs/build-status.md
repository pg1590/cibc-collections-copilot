# Build status - 4 October 2026

The four-layer local application is implemented. Runtime uses no paid API. Source data, databases, models, credentials, fairness evaluation details and raw AI outputs remain local.

## Measured checks

- 35 released benchmark questions generated through the app engine; six refusals and no unresolved results.
- All 12 numeric dev questions match organizer SQL references within tolerance. Hidden test and future extra questions are unverified.
- 19 tests cover roles, assigned-case access, injection/refusal boundaries, persistent review/audit and financial features.
- Frontend TypeScript, ESLint and production build pass.
- Real-data HTTP integration passes C360, metrics, refusal, local model brief, supervisor edit and persistent audit.
- Feature parity: 100 real customers, 0 mismatches.
- Heldout note model: {"precision": 0.8929, "recall": 0.6579, "f1": 0.7576, "balanced_accuracy": 0.8119, "confusion_matrix": [[85, 3], [13, 25]]}. Customer-grouped split; 374 train / 126 test notes. Small synthetic data, no production or uplift claim.
- Exploratory five-fold customer-grouped validation: pooled precision 91.74%, recall 68.49%, F1 78.43%. This reuses the same public development labels; it is not independent production validation. The serving model is unchanged.
- Python training and SQL serving financial cues agree on all 500 public labelled notes.
- 1014631 conservative canonical customers. Uncertain links remain review/unmatched; no independently labelled match precision evaluation.
- Implemented architecture PDF/PNG rendered and visually inspected.
- Submission preparation: nine-slide PDF presentation, 4:40 demo walkthrough, counted quality handling and committed-code ZIP builder. The ZIP format/coverage check passes for the current 35 rows; final mode requires the 15 extra questions.

## Remaining before submission

The [accuracy/readiness audit](reviews/accuracy-readiness-audit.md) found planner gaps beyond the released numeric references: some requested groupings return aggregate or differently grouped results, and several metric examples are incorrectly refused. Correct or clarify these requests and improve hardship recall before claiming general accuracy. Programme eligibility suggestions and concurrent-user performance remain unimplemented/unmeasured.

1. Browser visual review and team walkthrough. Browser connector was unavailable in this session; no rendered-UI claim is made.
2. User records and uploads the <=5-minute demo using the walkthrough. Verify anyone-with-link playback. Refresh and review the prepared nine-slide PDF after the final benchmark run.
3. Invite `cibchack26` by 17:00 IST and verify repository visibility/access in owner settings. Available tools cannot send the invitation; access remains unverified. No form submission performed.
4. Import extra questions at 19:00 IST on 4 October, rerun the same exporter, check failures and freeze the final commit before 21:00.
5. User may configure a provider key locally later. Do not enable paid calls until provider/budget are agreed.

Follow [the final checklist](submission-checklist.md). The organizer permits one form submission per team. The code ZIP must match the final committed and pushed revision, including the extra questions.

Claude Opus 5.5 high effort completed the plan review and frontend source. Its separate insight attempt timed out without files; Codex implemented and checked that module. No teammate work or selection guarantee is invented.
