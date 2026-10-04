# Changes on `team/krish-question-validation`

Owner: Krish (Insight and NLP), with Claude Opus 5.5. Base: `main` at `7fe9c21`. 4 October 2026.

## Summary

- Added 20 new question variants as tests. On the first run, 13 behaved correctly and 7 failed: 3 confident wrong answers, 2 false refusals, 1 missed refusal and 1 clarification where an answer was expected.
- Fixed all 7 in the question engine, including support for **one bound province filter**.
- All 35 released benchmark questions produce **identical** plans, refusals and policy answers on `main` and on this branch, so no released answer changes.
- Full suite: **162 passed** (Python 3.11, Windows, no dataset).

Details, evidence and the full question table are in [question-variant-validation.md](question-variant-validation.md).

## Commits

| Commit | What |
|---|---|
| `e0db35f` | 20 variants with expectations written first, and a validation report. The 7 confirmed failures were marked as strict expected failures. |
| `d8591ff` | Engine fixes for all 7 failures, plus the province filter |
| `efa0195` | Citation paths are the same on Windows and Linux. Records the checks against the release files. |

## Code changes

| File | Change | Fixes |
|---|---|---|
| `app/insights.py` `_refusal` | Adds `household` and `vulnerability` as protected words. Language words (`language/french/english/…`) are refused only with a decision verb (rank, prioritise, target, exclude, deny, call first), not for a "by language" breakdown. | QV-18, QV-20 |
| `app/insights.py` `answer`, `_policy` | "counts as / treated as / deemed broken" go to PRC-COLL-010 §3.3. The scope gate also accepts `ptp`, `broken`, `phone`, `sms`, `text message`. The §5.2 route accepts phone/contact/reach plus week/7 days. | QV-15, QV-16 |
| `app/insights.py` `_generic_plan` | "break rate … PTP/promise" is recognised. Groupings are read from "each/every/per <dimension>" and "across <dimension>s", not only "by", with plural forms. | QV-02, QV-10 |
| `app/insights.py` `_generic_plan` | Province names and "in/from ON"-style codes become `filters={'province': code}`. Two provinces or a city/site still ask for clarification. | QV-13 |
| `app/metric_plans.py` | `filters` may contain one key, `province`, from the 13 province/territory codes. It is matched on `collections_cases.province_code` and bound as a parameter. Supported for promise, contact, case and attempts metrics. Delinquency and write-off rates have no reviewed province source, so they still ask for clarification. The answer note says records without a linked case are excluded. | QV-13 |
| `app/gemini.py` | The plan schema, instruction and validation accept the same `{"province": code}` filter (enum of the 13 codes). | — |
| `app/insights.py` `_documents` | Policy citation paths use `as_posix()`. On Windows they used backslashes, so `sql_or_sources` depended on the OS. | — |

## Test changes

- **New: `tests/test_question_variants.py`.**
  - The 20 variants.
  - Province-filter SQL run on an in-memory DuckDB.
  - Unsupported province cases ask for clarification.
  - Injected or unknown codes are rejected.
  - For every filterable metric and grouping, placeholders equal parameters and the province is bound last.
  - Citation paths use forward slashes.
- **`tests/test_insights.py`:** "RPC rate in Ontario in September 2026" moved from the must-clarify list into a new test, `test_single_province_is_a_bound_filter_not_a_clarification`. This is a deliberate behaviour change. Every other edge case in that list still asks for clarification.

## Ownership note

The team plan assigned `app/insights.py`, `app/metric_plans.py`, `app/gemini.py` and `tests/test_insights.py` to Prakhar. This branch changes them at Krish's request. Merge carefully if there are concurrent edits.

## Checks before merging (need the DuckDB database)

1. `scripts/validate_dev.py`: 12/12 numeric dev answers must still match.
2. `scripts/run_benchmark.py --local`, then `git diff submission/benchmark_answers.csv`. Expected: no diff, since the 35 plans are identical. Inspect anything that changes.
3. Ask one province question (for example "Promise kept rate for Ontario customers in August 2026") to run the filtered SQL on the real schema. So far it has only run on test tables.

## Also in this branch

[improvement-plan.md](improvement-plan.md) is the gap review and the time-boxed remaining-work list (section 0) written on 3–4 October. It was previously untracked and is referenced by `docs/reviews/improvement-plan-review.md`.
