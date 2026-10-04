# Question-variant validation

Owner: Krish (Insight and NLP). First run: 4 October 2026, 17:40 IST, against commit `7fe9c21`; fixes applied ~18:10 IST on branch `team/krish-question-validation`. Tests: [`tests/test_question_variants.py`](../tests/test_question_variants.py).

## Method

1. Wrote 20 new questions with their expected behaviour **before** running any of them. Expectations come from the metric definitions in `app/metric_plans.py`, which are taken from `data/metric_definitions.csv`, and from the current policies. They do not come from what the planner does. Caveat: the author had already read the planner source during an earlier review, so this is not a fully blind test.
2. Coverage: alternative wording, the grouping asked for, periods (month, quarter, year, "last month", ISO date), ambiguous cohorts, policy questions and refusals. No question repeats a released benchmark question.
3. Ran each question through `InsightEngine` with no database. This checks the **plan**: metric, grouping, period, and whether the engine clarifies, refuses or cites a policy. It does not check the numbers. Policy routing used a five-section test corpus made from the real section text in the released answers, so search ranking on the full 19-document corpus is not covered.
4. Confirmed each failure by printing the engine's actual plan, so a mistake in the test was not counted as an engine failure.

## Results

**13 of 20 behaved as expected (65%)** on the first run. **After the fixes below, 20 of 20 do** (planning level, no dataset). Of the 7 failures, 3 gave a wrong answer with no warning, 2 were false refusals, 1 missed a refusal, and 1 asked for clarification where an answer was expected.

| ID | Question | Expected | Observed | Result |
|---|---|---|---|---|
| QV-01 | What share of promises to pay were kept in July 2026, split by queue? | promise_kept_rate, queue, 2026-07-01 to 2026-08-01 | As expected | Pass |
| QV-02 | Break rate on PTPs by product for Q2 2026 | broken_promise_rate, product, Q2 | **Overall broken rate; product grouping silently dropped** | **Fail: wrong answer** |
| QV-03 | What does each right-party contact cost us, by channel, in September 2026? | cost_per_rpc, channel, Sep 1–28 | As expected | Pass |
| QV-04 | Average days past due for open cases by product | average_dpd, product, snapshot | As expected | Pass |
| QV-05 | Card delinquency rate by DPD bucket as of 2026-09-28 | delinquency_rate, bucket, snapshot | As expected | Pass |
| QV-06 | Write-off rate by product for 2025 | write_off_rate, product, 2025 | As expected | Pass |
| QV-07 | Hardship rate among cases opened in August 2026 by queue | hardship_rate, queue, Aug | As expected | Pass |
| QV-08 | How many outbound attempts per case did we make in September 2026, by bucket? | contact_attempts_per_case, bucket, Sep 1–28 | As expected | Pass |
| QV-09 | Cure rate for June 2026 by province | cure_rate, province, June | As expected | Pass |
| QV-10 | How many open collections cases are there in each queue? | open_cases, queue, snapshot | **Overall count; "in each queue" not read as a grouping** | **Fail: wrong answer** |
| QV-11 | What was the cure rate for cases opened in August 2026? | Clarify: opened-in vs open-at-start cohort | As expected | Pass |
| QV-12 | How much did we collect in September 2026? | Clarify: promise payments vs all payments | As expected | Pass |
| QV-13 | What was the promise kept rate for Ontario customers in August 2026? | Answer, filtered to Ontario | Clarification: named province is an unsupported filter | **Fail: unanswered (design limit)** |
| QV-14 | Roll rate from 1-30 to 31-60 DPD between April and May 2026 by product | Roll template, month ends 30 Apr → 31 May, 31–60 destination, by product | As expected | Pass |
| QV-15 | How many times a week can we phone a customer about the same case? | Policy POL-COLL-001 §5.2 | **Refused as out of scope ("phone" not recognised)** | **Fail: false refusal** |
| QV-16 | After the due date, how long before a PTP counts as broken? | Policy PRC-COLL-010 §3.3 (2 business days) | **Routed to the September broken-promise rate** | **Fail: wrong answer** |
| QV-17 | Can collectors keep calling someone who has filed a consumer proposal? | Policy POL-COLL-001 §7.3 | As expected | Pass |
| QV-18 | Prioritise which customers to call first based on their household size | Refuse: protected attribute | Clarification; "household" not in the refusal list | **Fail: missed refusal (no data exposed)** |
| QV-19 | Give me the email addresses of all customers with broken promises | Refuse: bulk personal data | As expected | Pass |
| QV-20 | What is the promise kept rate by preferred language in August 2026? | Clarify: unsupported grouping. Language is a servicing field, not on the organisers' protected list | **Refused as a protected attribute** | **Fail: false refusal** |

Which failures matter most for scoring: QV-02, QV-10 and QV-16 return a confident wrong answer, which is worse than a clarification. The extra benchmark questions are likely to use wording like "in each …" and "counts as broken".

## Fixes (applied on this branch, 4 Oct ~18:10 IST)

On the first run (commit `e0db35f`), the 7 failures were marked as strict expected failures. All 7 are now fixed and `KNOWN_FAILURES` is empty. Full suite: **161 passed, 0 expected failures**, on Python 3.11 and Windows, with no dataset.

| Fix | Files | Failures fixed |
|---|---|---|
| **Refusals.** `household` and `vulnerability` added as protected words. The word is `vulnerability`, not `vulnerable`, so the certified-for-vulnerable pilot question still works. Language words are refused only with a decision verb (rank, prioritise, target, exclude, deny, call first), not as a "by language" breakdown. "Target French customers for stricter collections" is still refused. | `app/insights.py` `_refusal` | QV-18, QV-20 |
| **Policy routing.** "counts as / treated as / deemed broken" go to PRC-COLL-010 §3.3. The scope gate also accepts `ptp`, `broken`, `phone`, `sms` and `text message`. The §5.2 route accepts phone/contact/reach plus week/7 days. | `app/insights.py` `answer`, `_policy` | QV-15, QV-16 |
| **Broken-promise wording.** "break rate … PTP/promise" is recognised by the metric compiler, so its grouping is kept. | `app/insights.py` `_generic_plan` | QV-02 |
| **Grouping words.** Besides "by", the engine accepts "each/every/per <dimension>" and "across <dimension>s", with plural forms. | `app/insights.py` `_generic_plan` | QV-10 |
| **Single province filter.** `filters` may contain one key, `province`, whose value must be one of the 13 province/territory codes. It is matched on the collections case `province_code` and bound as a parameter, never pasted into the SQL. Records without a linked case are excluded, and the answer note says so. It is supported for promise, contact, case and attempts metrics. It is **not** supported for delinquency rate or write-off rate (no reviewed province source on the account tables), which still ask for clarification. Province names and "in/from ON"-style codes are detected locally. A city/site or two provinces still ask for clarification. The Gemini plan schema, instruction and validation accept the same filter. | `app/metric_plans.py`, `app/insights.py`, `app/gemini.py` | QV-13 |

**Behaviour change to note:** before this branch, `tests/test_insights.py` required "RPC rate in Ontario in September 2026" to ask for clarification. It is now answered with the province filter. That question moved from the clarification list into a new test, `test_single_province_is_a_bound_filter_not_a_clarification`. All other edge cases in that list still ask for clarification.

**New tests:** filtered SQL runs on an in-memory DuckDB. ON promises give 66.7% of 3; QC promises, unlinked promises and promises outside the period are excluded. The filter works across case-linked metrics. Unsupported province cases ask for clarification. Injected or unknown codes are rejected. For every filterable metric and grouping, the number of placeholders equals the number of parameters and the province is bound last.

**Before merging, check against real data:**
- Run `scripts/validate_dev.py`: 12/12 must still match.
- Run `scripts/run_benchmark.py --local` and check `git diff submission/benchmark_answers.csv`. No released answer is expected to change. The README says none of the 35 currently need clarification, and the changes only widen recognition. Inspect any diff before accepting it.
- Run the filtered queries once on the real schema. `contact_history.case_id` and `collections_cases.province_code` are used by existing reviewed queries, but the new combinations have only been run on test tables.

## Release-file checks (4 Oct, ~18:30 IST)

The release ZIP was available, but the DuckDB build was not run. The small release files were extracted (benchmark questions, dev answers, 19 reference documents) to check what can be checked without the database:

- **Released benchmark unchanged:** all 35 released questions were run through `7fe9c21` (main) and this branch with the real policy corpus (36 sections). Refusal flags, refusal text, policy answers and citations, and every generated SQL plan and parameter list are **identical**: 0 differences. Data answers come from that SQL, so this branch cannot change any of the 35 released answers.
- **Policy answers against dev gold:** BQ-002, BQ-005, BQ-019 and BQ-026 cite the gold section, and every key fact checked is in the answer text. BQ-026 contains "3-month", "50%" and "interest keeps accruing", taken from the current v4.2 policy, not the superseded 6-month FAQ. BQ-018, BQ-024 and BQ-031 are refused as gold requires.
- **Variants on the full corpus:** QV-15, QV-16 and QV-17 cite §5.2, §3.3 and §7.3 on the real 19 documents, not just the five-section test corpus.
- **Windows path fix:** on Windows, cited paths used backslashes (`files\docs\...`). That would make `sql_or_sources` depend on the OS. Paths now use `as_posix()`, matching the committed CSV generated on Linux. A test covers this.

Not yet checked against the database: the numeric dev answers (`scripts/validate_dev.py`) and the filtered SQL on the real schema. Both need `scripts/build_data.py` or the existing database on Prakhar's machine.

## Remaining failures

None of the 20 variants fail after the fixes. This is planning-level coverage of these 20 questions, not an accuracy rate for unseen questions. Other cohort filters (queue, product, "open cases only", hardship cases) still ask for clarification by design.

## Not covered

- Numeric correctness. Run the 20 questions on real data:
  ```bash
  .venv/bin/python -c "import tests.test_question_variants as t,json;from app.runtime import answer;[print(q[0],json.dumps(answer(q[1])['answer'][:300])) for q in t.METRIC_VARIANTS]"
  ```
- Policy retrieval ranking on the full document corpus. The tests use a five-section test corpus.
- The Gemini planner path. These runs used no key.
