# Krish question-validation merge review

Reviewed contribution: `team/krish-question-validation` at `4bb298f`, based on `main` at `7fe9c21`. The four original contribution commits are retained. Follow-up `5b38359` fixes the review findings before integration.

## Changes and resolutions

- Reject province exclusions rather than incorrectly selecting the excluded province.
- Detect coordinated province codes such as `ON and QC`, `ON/QC`, and mixed names/codes; ask for one province.
- Reject null, list, object, numeric, unknown and injected province values with controlled compiler/provider errors.
- Require provider plans to preserve the requested province; a model cannot drop, add or invert the cohort.
- Preserve the newer main metrics, period/cohort validation, proxy safeguards, vulnerability safeguards, policy routes and voice work while adding Krish's question variants, province support and portable citation paths.
- Case-based extension metrics share the existing case province compiler. The SMS payment-link extension explicitly disallows province filters because it has no reviewed province compiler branch.

## Verification

Run against an isolated preview combining the contribution with the current main working changes, using local execution and mocked providers:

- Full Python suite: **256 passed**. FastAPI tests ran with local test sockets available; no paid/provider requests were made.
- Independent organizer numeric references: **12/12 matched**.
- Original 35 plus 15 extra benchmark questions: **50 rows**, **zero unresolved**, **9 expected refusals**; every generated CSV row matched the current main working output.
- Real DuckDB schema checks: **56** supported metric/grouping province combinations passed `EXPLAIN` with bound parameters.
- Ontario promise-kept query executed against the real database with a nonempty denominator; test data separately verifies province selection and exclusion of unlinked records.

These checks cover the released examples and reviewed variants; they do not establish correctness for every possible natural-language question. The live Gemini service was not invoked.
