# Improvement plan: gaps against the build-phase requirements

Review date: 3 October 2026. Reviewer: Krish (with Claude). Deadline: **4 October 2026, 21:00 IST**; extra benchmark questions arrive at **19:00 IST**.

This is a static review of commit `efc21f4` against the build-phase instructions, the design-phase problem statement, the challenge deck and our own design PDF (`Adda Wale_SystemDesign.pdf`). The code was read, not run (the dataset is not on the reviewer's machine). Numbers quoted come from the repository's own reports and `submission/benchmark_answers.csv`. Items marked **verify** need a run on real data before acting.

Second pass (same day) added: the recorded case `hardship_flag` is ignored by the brief (2.3), the C360 is narrower than the design's contract (2.13), the design's three LLM components are absent (2.14), and Windows/Python 3.14 setup failures (2.8).

## 0. Status at 17:10 IST, 4 October (review of `7fe9c21`)

Sections 1–4 below are the original plan, kept for history. This section supersedes them for the remaining time.

### Done

| Item | Evidence |
|---|---|
| 2.3 step 0, recorded hardship | `brief()` reads open-case `hardship_flag`. Order: hold → recorded → possible → default. Case IDs are cited; tests are in `tests/test_brief_decisions.py`. |
| 2.3 step 1, reason sentence | `recommendation_reason` on every branch, shown in the brief and review UI, and stored in the audit record |
| 2.1 semantics (most of it) | `app/metric_plans.py`: 13 metrics, 47 grouping combinations, grouping honoured or clarified. No June-30 or late-fee constants. Dates are parsed (`may` and `mar` collisions fixed). |
| 2.2 BQ-014 | Anchored to first assignment, mature assignments only; now 2.45% vs 3.98% |
| 2.2 call summaries | `app/policy_summary.py`: structured extractive summary with timestamps |
| 2.4 README | Design-changes section, Windows/`PYTHONUTF8` notes, Gemini configuration, AI-tool disclosure |
| 2.5 DQ report | Handling column for every check, plus an identity outcome table |
| 2.7 contract | Business owner and technical steward split; inherited DC-COLL-001 thresholds; third-party processing section |
| 2.8 encoding | `encoding='utf-8'` across app and scripts; BOM-tolerant question CSV |
| 2.9 engine caching | `app/runtime.py` caches `InsightEngine` per process |
| 2.14 LLM | Optional Gemini: planning via the reviewed compiler (no model-written SQL) and verified extractive quotes. **Never called live** (no key at verification). |

### Deferred (do not start today; list as "next steps" in the deck)

Programme eligibility (2.3 step 3), per-case rolling contact rule (2.3 step 4), transcript evidence in briefs (2.3 step 2), recall tuning (2.3 step 5), C360 field expansion (2.13). Feature freeze was 15:00.

### Remaining, in order

**Before 19:00 (extra questions):**

1. **Rehearse extra questions (highest scoring value).** The engine now prefers `clarification_required` over guessing. An automatically scored benchmark almost certainly counts a clarification as wrong: it is not a refusal and not an answer.
   - Write 20 questions in the style of the 35 released ones, reworded, with filters such as "in Ontario", "for card", "for open cases", "last quarter". Use someone who did not write the planner.
   - Run them through `scripts/run_benchmark.py --questions <file> --output <scratch.csv> --local`. Count the `clarification_required` rows by message.
   - Expect most to come from three `PlanError`s in `_generic_plan()` (`app/insights.py` ~lines 309–315): named province/site, cohort words (`for`/`only`/`with` …), and the "open cases" filter.
2. **If (1) shows filters dominate: support one equality filter.** In `compile_plan()`, allow `filters` with **one** key from a fixed allowlist (`province`, `queue`, `product`, `site`/`agent_site`, `bucket`). Map each key to the same column expression as the grouping, bind the value as a parameter, and validate the value against `SELECT DISTINCT` of that column (else clarify). Detect it locally with the existing province regex plus a value lookup. Gemini already emits `filters`, so widen `PLAN_SCHEMA` the same way. Add tests. Budget 1 hour; skip if (1) shows few filter questions.
3. **Gemini: test live or switch off explicitly.**
   - Live test: save the key to `data/gemini-key.txt`, check `/api/health` shows `gemini_configured: true`, then ask 3 questions the local planner does not recognise. First list the models (`GET https://generativelanguage.googleapis.com/v1beta/models` with the key header) and confirm `gemini-3.8-flash` exists. The model name and the Interactions endpoint have only been tested against mocks.
   - Note: Gemini is consulted only when `_plan()` returns `None`. A local `PlanError` (most clarifications) goes straight to the outer `except` and never reaches Gemini. If Gemini works, also try it on a local `PlanError` and keep the local clarification if Gemini also fails. This is about 10 lines in `InsightEngine.answer()`.
   - If the live test fails or there is no time: generate the final benchmark with `--local`. Say "optional, not used for the submitted answers" in the deck and video. Do not demo or claim it.
4. **Protected-attribute refusal regex** (`app/insights.py` ~line 129):
   - It now includes `language|french|english`. Preferred language is a servicing attribute (French service is required), not one of the organisers' protected fields. "Promise kept rate by preferred language" and "show the hardship policy in French" would be refused. Drop those three words unless the team decides language is protected.
   - It also lacks `household` and `vulnerab\w*`, which *are* on the organisers' list. Add them, but do not trip on the certified-for-vulnerable pilot question (BQ-014). Run `tests/test_insights.py` afterwards.
5. **Dry-run the extra-question path** with a two-row fake file in the answers-template format (BOM, CRLF). Confirm the output still has 35+2 rows and that exit code 2 (unresolved rows) does not stop anyone from committing. The CSV is written before the exit.

**19:00–20:30:**

6. Run `run_benchmark.py --extra <file>` (plus `--local` if decided in step 3). Fix *engine* issues only, regenerate, and check row count (50), header and lower-case `true`/`false`. Commit and push by **20:30**.
7. Refresh the deck (`scripts/generate_pitch_pdf.py`) and the ZIP (`scripts/package_submission.py --final`) from the pushed commit.

**Parallel, any time before 20:30 (not code):**

8. Record the video (`docs/demo-walkthrough.md`, 4:40). Its script mentions Gemini in the last segment; cut that line if step 3 did not pass live.
9. Confirm `cibchack26` has *accepted* the invite, not just been invited.
10. Decide whether to commit this file. `docs/reviews/improvement-plan-review.md` refers to it, but it is currently untracked.

**Low priority, only if idle:**

- Policy answers are still whole sections. BQ-026 is 2,242 characters, BQ-019 and BQ-026 both open with §4.2, and BQ-001 and BQ-005 are identical. `summarize_policy()` falls back to the full section whenever shortening could drop a condition.
- BQ-010 shows 0.0% out-of-hours for every province except NL. `CASE WHEN NOT flag` counts a null flag as compliant. Count nulls in `within_permitted_hours_flag` before trusting it.

## 1. Requirement checklist

| Requirement (build-phase PDF) | Status | Evidence / gap |
|---|---|---|
| L1: raw → curated → golden C360 pipeline (code) | Done | `scripts/build_data.py`; 1,014,631 golden customers |
| L1: ID matching across five source systems with match confidence | Done | `gold.identity_crosswalk`; crm, cards, lending, core, collections, bureau; rule scores, not probabilities |
| L1: data-quality checks | Done | Uniqueness, referential, missing, DPD/bucket checks |
| L2: plain-English questions over the C360 | Partial | Keyword router only; most portfolio SQL reads `curated.*`, not the C360 (section 2.1) |
| L2: SQL or source shown with every answer | Done | `sql_or_sources` on every answer |
| L2: out-of-scope questions refused | Done | Regex refusals; brittle to rewording |
| L3: features from structured data **and** text/voice | Done | `app/features.py`; 5 structured + 6 text features |
| L3: one definition for training and live scoring | Done | `feature_sql()` shared; 100-customer parity check |
| L4: working model/agent for the use case, "built in depth" | Partial | Brief is one of three template branches (section 2.3) |
| L4: plain-English explanation of each decision | Partial | Recommendation text exists but does not say *why* |
| L4: human review/override point | Done | Supervisor approve / reject / edit, append-only audit |
| Rules: no protected attributes | Done | Gender used only in offline fairness audit |
| Rules: flag financial hardship | Partial | Brief ignores the source case `hardship_flag`; only the note model/regex can trigger the hardship path (section 2.3, step 0) |
| Consistency with our design PDF | Partial | No LLM anywhere (design had three AI components); C360 has 8 of the designed fields; no specialist role (sections 2.13, 2.14) |
| Deliverable 1: README covers run / **what changed from design** / AI tools | Partial | No "what changed" section; run steps are Mac/Linux only and fail on Python 3.14 |
| Deliverable 2: architecture diagram PDF/PNG | Partial | Does not mark where AI is used, where humans review, or governance across layers |
| Deliverable 3: data contract YAML based on DC-COLL-001 | Mostly done | `config/c360-contract.yaml`; owner should be a business role |
| Deliverable 4: data-quality report with counts **and how handled** | Partial | Counts only; no handling column; some known issues missing |
| Deliverable 5: benchmark CSV generated by the system | Partial | 35/35 rows; several answers look wrong or weak (section 2.2) |
| Deliverable 6: ≤5-minute demo video | Not started | |
| Deliverable 7: ≤10-slide PDF pitch deck | Not started | |
| Private repo + organiser collaborators | Pending | Repo is private; organiser identities not yet given |

## 2. Prioritised changes

### P0 (highest scoring impact)

#### 2.1 Make the question engine handle unseen questions

**Problem.** `app/insights.py` `_plan()` (lines ~124–193) is an ordered list of keyword checks. Several branches are fitted to individual released questions:

- `'late fee'` with default days 15–22 (line ~128).
- `'certified' and 'pilot'` (line ~163).
- `'roll' … 'march'`, which always uses **30 June** as the end date regardless of the question (line ~174).
- The `preferred` policy-section map in `_policy()` (line ~199).

Any rewording falls through to "clarification required". The 19:00 extra questions and the judges' live questions are the main risk. The accuracy audit (`docs/reviews/accuracy-readiness-audit.md`) already lists wrong groupings and false refusals:

- "by queue / tier / site / bucket" returns an overall or a different grouping.
- "how much did we collect" is refused.
- "attempts per case by bucket" is refused.

**Change.**
1. Keep the existing templates as the fast path. Add an **LLM fallback** when `_plan()` returns `None`:
   - Prompt with the C360/curated schema (table and column names plus descriptions from the data dictionary) and `data/metric_definitions.csv`.
   - Ask for a single DuckDB `SELECT` as JSON (`sql`, `params`, `explanation`, `refuse`, `refuse_reason`).
   - Validate it: parse with `sqlglot` or DuckDB `EXPLAIN`; allow `SELECT`/`WITH` only, with an allow-listed schema; reject protected columns; add a `LIMIT` and timeout.
   - Execute on the existing read-only connection (`enable_external_access=false` is already set).
2. Make templates honour the requested grouping or return a clarification. Never substitute a different grouping silently.
3. Remove question-specific constants: the June-30 roll end date, the default late-fee day range, and the hand-picked policy sections. Derive dates from the question via `date_range()`.
4. Prefer `gold.*` tables where they exist, to satisfy "answered over the C360".
5. Keep the regex refusals as a pre-filter. Also let the LLM return `refuse`, so reworded protected-attribute or bulk-export requests are caught.

**Done when:**
- All 12 numeric dev questions still match (`scripts/validate_dev.py`).
- The 15 metric-definition example questions from the audit return the requested grouping or a clarification.
- A held-out set of 20 reworded questions, written by a teammate who has not seen the templates, answers at least 15 correctly.
- All refusal tests in `tests/test_insights.py` still pass.

**Constraint.** `CLAUDE.md`/`AGENTS.md` say paid runtime API calls wait until the supervisor (Prakhar) configures a key. The build-phase PDF explicitly allows paid LLM APIs with synthetic data. Agree on the provider, model and spend cap first. Read the key from an environment variable and keep it out of Git. With no key set, fall back to today's behaviour.

#### 2.2 Fix benchmark answers that look wrong or weak

| Row | Issue | Action |
|---|---|---|
| BQ-014 | `cure_30d_pct` is **0.0 for both** certified groups; almost certainly a bug | **Verify:** check `cure_flag`/`days_to_cure` types and nulls for pilot cases; check the `case_open_date<=snapshot-30` filter |
| BQ-016, 021, 022 | "Summarise the call" returns raw customer turns, not a summary | Add an LLM summary grounded in turns, citing turn timestamps. Without a key, use a structured extractive summary (reason for call, promise amount/date, hardship cue, next step). Score against the 500 public transcript labels. |
| BQ-001/005, 002, 009, 019/026, 033 | Policy answers paste whole sections | Return a one- or two-sentence direct answer first, then the cited section. BQ-019 and BQ-026 return the identical §4.2 text for different questions. |
| All | Answers are raw CSV dumps | **Verify** against `labels/benchmark_dev_answers.csv` and the answers template. If dev answers are short scalars, lead with a one-line answer and put the table after it. |

Re-run `scripts/run_benchmark.py` after every change. Do not hand-edit the CSV; the rules forbid it.

#### 2.3 Build the agent-assist use case in depth

Currently (`app/main.py` `brief()`, lines ~150–185) the recommendation is one of three fixed strings. The only text input is the **latest note**, and the model sees 6 regex flags.

Add, in this order:

0. **Use the recorded hardship flag** (rule: "Flag financial hardship"). `curated.collections_cases.hardship_flag` is used only by the Ask analytics (`app/insights.py` line ~187). `brief()` never reads it. Today a customer whose open case is flagged for hardship, but whose latest note has no regex cue and scores below 0.5, gets the generic "confirm circumstances" recommendation.
   - Add `recorded_hardship = bool_or(hardship_flag) FILTER (WHERE outcome IS NULL)` to `gold.customer_summary` (`scripts/build_data.py`) and to the `cases` CTE in `feature_sql()` (`app/features.py`). Treat it as a structured feature, not a classifier input, so the trained model and the parity check stay valid.
   - In `brief()`, branch order becomes: hold → recorded hardship → model/regex hardship → default. Label the two clearly: "Hardship recorded on case CS-…" versus "Possible hardship (AI cue, needs review)". The design PDF said AI cues stay "possible" and cannot clear a recorded flag; enforce that.
   - Add it to the brief's `signals` with `collections_cases:<case_id>` as evidence.
1. **"Why" sentence per decision** (required: "every decision shown to an agent comes with a plain-English reason"). For example: "Flagged for hardship review because the 12 Sep note says 'hours were cut' (income_reduction) and the review score is 0.82; 2 of the last 3 promises were broken." Build it from the triggered features, the model coefficients (already in `model-report.json`) and the evidence spans.
2. **Transcript evidence.** Include the latest call transcript for the customer's open case, not just the latest note. Reuse `_transcript()` extraction.
3. **Hardship programme suggestions** from `data/hardship_programs.csv`:
   - Check the effective date, product, DPD, time on book, previous use and approval level.
   - List missing inputs explicitly.
   - Present suggestions only; the supervisor decides.
   - Currently this file is never read.
4. **Contact-rule check.** Apply the 3-attempts-per-rolling-7-days rule (POL-COLL-001 §5.2) using `contacts_7d`, which is already a feature. Also apply consent per channel and the calling-hours rule, then recommend the channel and time to use or avoid.
5. **Improve hardship recall** (currently 65.8% held-out):
   - Do error analysis on the 46 false negatives in the five-fold run.
   - Widen the regexes and/or add an LLM cue extractor that returns cited spans. Keep its output as a *feature* with the same offline/online definition.
   - Report precision and recall against the public labels.
6. **Hardship flag in lists.** Show both the recorded flag and the AI "possible" flag in the customer list and the review queue so supervisors can triage.

**Done when:**
- A customer with a recorded case hardship flag and no note cue gets the hardship path, with the case ID cited.
- Each brief shows a reason sentence, evidence with source IDs, programme options with eligibility status, and contact-rule status.
- Model recall on the held-out split improves without precision dropping below about 85%.
- Tests cover the hold-path priority: insolvency, cease-contact and deceased holds override the model.

### P1 (required deliverables)

#### 2.4 README

- Add a **"What changed from our design"** section (required). Main items:

  | Design (2 Oct PDF) | Build | Why |
  |---|---|---|
  | CockroachDB | DuckDB + SQLite | Local setup; queries Parquet directly |
  | LLM query plan + Pydantic | Fixed templates (+ LLM fallback if 2.1 lands) | No key yet; deterministic SQL |
  | LLM hardship-cue extraction | Regex cues + logistic regression (+ LLM cue feature if 2.14 lands) | No key; explainable; measurable on labels |
  | Three layers | Four layers (separate Feature Store) | Build-phase requirement |
  | Specialist approves hardship referral | Supervisor reviews every brief | Simpler role model for demo |
  | AI schema-mapping suggestions | Mappings from the release schema | Release schema made it unnecessary |
  | C360 with consent, promise/contact counts, reviewed hardship status | Whatever 2.13 ends up adding; list anything still missing | Time; say which fields were dropped |
  | Identity matching: exact links + RapidFuzz suggestions | Rule-scored blocking on DOB + phone/postal/name; RapidFuzz only on a 1,000-row review sample | Scale (1M customers); fuzzy never auto-merges |

  Update this table to match what actually ships. Write the final version once features freeze.

- Add Windows setup steps. Python 3.14 is the default on at least one team laptop, and `requirements-lock.txt` pins numpy 2.2.6 and scipy 1.15.3, which will not install on Python 3.13+. Document "use Python 3.10–3.12" (on Windows: `py -3.11 -m venv .venv`, then `.venv\Scripts\python ...`), or add a looser fallback requirements file. Also state that the app does not load `.env`, and show the PowerShell form for setting variables (`$env:COPILOT_DATASET="..."`).

#### 2.5 Data-quality report

The instructions ask for "the issues you found, how many records each affected, and **how you handled them**". In `scripts/build_data.py` (the report writer near the end):

- Add a **Handling** column to the checks table. Examples:
  - "Orphan contact rows kept in portfolio counts, excluded from C360".
  - "Bucket recomputed from DPD for features; source bucket retained".
  - "Missing DPD excluded from delinquency denominators".
- Add rows for known issues that are handled but not reported:
  - CRM duplicates merged: 1,020,000 → 1,014,631 = **5,369**.
  - Mixed date formats: count rows parsed by each non-ISO format.
  - `channel` → `channel_v2` schema drift in late September: count rows.
  - Identity review: 64,145; unmatched: 96,355.
  - Invalid typed values per column; these are already counted in `report['checks']` as warnings.

#### 2.6 Architecture diagram

`scripts/generate_build_architecture.py` → `docs/architecture-build.{pdf,png}`:

- Mark **where AI is used**: the classifier, the LLM fallback/summaries if added, and BM25 retrieval.
- Mark **where a human reviews**: supervisor review of briefs, and identity review records.
- Draw **governance as a band across all four layers** (RBAC, audit, protected-attribute exclusion, monitoring), not as a footer.
- Name tools in each box: DuckDB, Polars/Pandera, scikit-learn, FastAPI, Next.js, SQLite.

#### 2.7 Data contract

`config/c360-contract.yaml`:

- Owner: a business role (for example "Collections Operations lead"), with the team as technical steward.
- Express quality rules as testable rules with thresholds, matching the DC-COLL-001 example's structure. For example: `customer_id unique & non-null: 100%`, `contact→case orphans < 1%`, `open_cases >= 0`.
- Make the refresh cadence explicit.
- Keep the column list in step with 2.13. Every column in `gold.customer_summary` should be in the contract, and vice versa.

#### 2.13 Bring the C360 closer to the design's contract

The design PDF (page 6) promised these C360 fields. `gold.customer_summary` currently has 8 columns: `customer_id`, `name`, `province`, `preferred_language`, `open_cases`, `total_overdue`, `max_dpd`, `identity_confidence`.

| Designed field | Status | Cheapest source |
|---|---|---|
| `identity_status`, `pending_link_count` | Missing | `gold.identity_crosswalk` status counts per customer |
| `account_count_by_product` | Missing | `gold.accounts` grouped by `source_system`/`product` |
| `worst_dpd`, bucket | Partial (`max_dpd` only) | Add the bucket using the same CASE as the DQ check |
| `promise_counts_90d` | Missing (feature store has all-time counts only) | `curated.promises_to_pay`, `status_ts` within 90 days of snapshot |
| `contact_count_30d`, `last_contact_ts` | Missing (`contacts_7d` only) | `curated.contact_history` |
| `consent_by_channel` | In `gold.customers`, not in the summary | `consent_call/sms/email` |
| `reviewed_hardship_status` | Missing | Recorded case `hardship_flag` (2.3 step 0) |
| `dq_status`, `lineage_ref` | Missing | Count of failed checks touching the customer; crosswalk method |

Add the fields that the brief and the demo actually use: identity status, the 30/90-day counts, consent, and recorded hardship. The C360 then backs the brief rather than the brief re-querying curated tables. Mark the rest as "not built" in the README table (2.4). Rerun `train_model.py` afterwards so `gold.features` and the parity check are rebuilt.

#### 2.14 Decide on the LLM now (blocks 2.1, 2.2 and 2.3 step 5)

Our design used an LLM in three places: schema-mapping suggestions, question → query plan, and hardship-cue extraction. The build uses none, and the README says so. "Innovative ideas" is 15% of the build score, and the design was judged partly on "smart use of AI". The build rules explicitly allow paid LLM APIs on this synthetic data.

- **Decision needed today (supervisor):** provider, model, a spend cap, and who holds the key. Read it from an environment variable and keep it out of Git.
- **Where to use it, in order of payoff:**
  1. Question fallback, when `_plan()` returns `None` (2.1).
  2. Call summaries and short policy answers (2.2).
  3. Hardship-cue extraction with cited spans, as an extra feature (2.3 step 5).
- **Guardrails, matching what the design promised:**
  - Validate every LLM output (SQL allow-list, citations must point to real turns/notes, numbers must come from query results).
  - Treat retrieved text as untrusted input.
  - Log the model name and version in the audit record.
  - With no key set, fall back to today's deterministic behaviour so the benchmark still runs.
- If the team decides against an LLM, say so and why in the README's "what changed" table and in the deck. Do not leave the design's claims unaddressed.

### P2 (robustness and polish)

| # | Change | Where |
|---|---|---|
| 2.8 | Pass `encoding='utf-8'` to every `read_text()` / `open()` / `write_text()`. Windows defaults to cp1252, including on Python 3.14 (UTF-8 mode only becomes the default in 3.15). The policy documents contain § and accented French, so the app breaks on Windows without this. Stopgap until fixed: set `PYTHONUTF8=1` before running anything. | `app/insights.py` lines 63, 68, 228; `app/main.py` 99, 234, 241, 243; `scripts/run_benchmark.py` 16, 21; `scripts/train_model.py` 24; `scripts/validate_dev.py` 11, 16; `scripts/build_data.py` 48, 58 |
| 2.9 | Build `InsightEngine` once at startup, not per `/api/ask` request; it re-reads every policy document and rebuilds BM25 on each call | `app/main.py` `ask()` |
| 2.10 | Use `date_range()` defaults deliberately. Questions without a period currently default to 1–28 Sep. Either say so in the answer or ask for a period. | `app/insights.py` `date_range()` |
| 2.11 | Add API tests for brief hold-priority, the recorded-hardship path and the reason sentence | `tests/` |
| 2.12 | Browser walkthrough of every screen for all three roles (never done) | frontend |

## 3. Submission work (not code)

1. **Pitch deck** (≤10 slides, PDF):
   - Problem.
   - The C360 and identity matching, with numbers.
   - Live Q&A with SQL shown.
   - Agent-assist brief and the "why".
   - Human review and audit.
   - Governance and fairness.
   - Measured results (benchmark, model precision/recall, parity).
   - What changed and what's next.
   - Team.
2. **Demo video** (≤5 minutes, real data): supervisor overview → customer C360 with identity links → ask 3 questions including one refusal → generate a brief for a hardship customer → supervisor edits and approves → audit log → agent login showing restricted scope.
3. **19:00 on 4 Oct:** run `scripts/run_benchmark.py --extra <file>`, review unresolved rows, fix *engine* issues only, regenerate, and commit before **20:45** for a buffer.
4. Add organiser collaborators once their identities are announced. The supervisor does this.

## 4. Suggested split (4 people, about 30 hours)

| Owner (proposal) | Items |
|---|---|
| Supervisor (first, today) | 2.14 decision: provider, key, spend cap |
| Insight engine | 2.1, 2.2, 2.9, 2.10 |
| Decisioning / model | 2.3 (start with step 0), 2.11 |
| Data and docs | 2.13, 2.5, 2.6, 2.7, 2.4, 2.8 |
| Frontend, deck and video | 2.3 UI pieces (reason sentence, programmes, recorded and AI hardship flags), 2.13 fields on the customer page, 2.12, section 3 |

2.13 and 2.3 step 0 both touch `gold.customer_summary` and `feature_sql()`. Agree the new column names before either person starts.

Follow `AGENTS.md` file ownership: one person or agent per file at a time, with changes reviewed before merging. Freeze features at 4 Oct 15:00 IST, as in the original build plan.
