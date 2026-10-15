# How we decided: architecture, models and the LLM

Every choice in Collections Copilot follows from five constraints we took from the policies and the data before writing code. This page lists them, the one rule we used to decide what kind of technology does each job, and each major decision with the options we considered and the evidence. Numbers are measured on the synthetic Maple Bank release (snapshot 28 Sep 2026) unless marked otherwise.

## The constraints

1. **Compliance first.** Contact hours, the 7-day cap, insolvency stays, representatives and hardship-before-payment are legal or policy obligations (POL-COLL-001, POL-COLL-004, PRC-COLL-010). A wrong step is a breach, not a lower score.
2. **Explainable to an agent, a supervisor and a regulator.** Every recommendation must say which record and which policy section it comes from.
3. **Customer data stays inside the bank by default.** Notes and transcripts are the most sensitive text we hold.
4. **Works on the next data release**, not only this extract.
5. **Measured, not claimed.** Every number we show can be reproduced by a script or a query.

## The decision rule

For each job the product does, we asked one question at a time:

1. **Is the answer written down in policy?** Use deterministic rules over source records. *(contact windows, caps, restrictions, programme eligibility, step order)*
2. **Is it a pattern in free text, and do we have labelled examples?** Use a small, interpretable trained model. *(hardship cues in agent notes)*
3. **Is it a language task whose output can be checked against a source?** Use an LLM, and verify its output before anyone sees it. *(question → reviewed plan, choosing verbatim evidence, call notes → proposed outcomes)*
4. **Otherwise, a person decides.** *(final hardship eligibility, approving every brief and call note)*

The rule puts the LLM where language understanding helps and its mistakes can be caught, and keeps it away from numbers and compliance decisions.

## Decisions

| Decision | Options we considered | What we chose | Why | Evidence |
| --- | --- | --- | --- | --- |
| Who decides the next step | An LLM agent; an ML ranking score; rules over source records | **Rules** (`app/action_plan.py`), one function used by the brief, Call Mode, the queue and the nightly batch | Policy states the rules explicitly; rules are deterministic, testable and cite their section; an LLM can be talked out of a restriction and a score can't explain itself | Each step cites policy + source record; unit tests and pinned demo customers; a synthetic 2027 release is followed with no code change |
| Hardship detection in notes | Rules only; logistic regression on policy cues; an LLM classifier; a deep text model | **Class-balanced logistic regression on 9 cues** from POL-COLL-004 §4.2, served as *model OR any cue sentence* | 500 labelled notes is too few for a deep model; 9 named weights are readable; no protected or vulnerability inputs; identical features offline and live; runs locally | Held-out 126 notes: model 36/38, served detector 38/38, 0 false alarms; 0 mismatches offline vs live on 100 customers; LLM comparison below |
| Where the LLM is used | No LLM; LLM writes SQL and answers; LLM chooses from reviewed options and quotes sources | **LLM only proposes, the app verifies**: a plan from our metric catalogue, verbatim evidence, call outcomes with a verbatim quote | Numbers must be exact and repeatable; a generated SQL query or paraphrase can be wrong in ways nobody sees | Model-written SQL is never executed; a quote not found verbatim in the source is dropped; 12/12 organiser reference answers match; 50 benchmark answers reproduce byte for byte |
| Which LLM | Gemini 3.8 Flash; Gemini 3.5 Flash-Lite; another provider; a local open model | **Gemini 3.5 Flash-Lite**, optional and off by default on stage | Free tier available to the team; native JSON-schema output, so every reply fits a fixed shape we can validate; fast | Live 15 Oct: under 2 s per call; 3.8 Flash returned "high demand" (503) or timed out the same day. The provider sits behind one module (`app/gemini.py`), and every output passes the same validators, so swapping providers changes no decision logic |
| Policy search | Embeddings + vector store; BM25 keyword ranking | **BM25 over policy sections** | 19 reference documents; policy language is keyword-heavy; results must cite an exact section and version; no extra model or store to run | Answers quote the section with its version, e.g. POL-COLL-001 v3.0 §5.2 |
| Analytics store | Postgres; Spark; DuckDB | **DuckDB**, opened read-only by the app | Columnar SQL over 1.02M customers, 2.69M contacts and 760K notes in one local file; reads the release's Parquet directly | A 30-day scan of all outbound contacts takes a few milliseconds; portfolio checks are single queries shown with their SQL |
| Review and audit state | Same database; a separate store | **SQLite**, separate from customer data | Writes (sessions, briefs, decisions) never touch source data; the audit must be tamper-evident | Each audit event stores the previous event's hash; database triggers refuse updates and deletes |
| Identity matching across systems | Fuzzy auto-merge; deterministic rules with a review queue | **Deterministic rules; uncertain matches held for a person** | A false merge would show one person's debt to another | 3.67M links matched, 64,145 held for review, 96,355 not matched; RapidFuzz scores are shown as diagnostics only |
| Scale | Per-customer queries; set-based batch | **Set-based loading + 8 worker processes** | The same rules must plan the whole book overnight | 93,320 customers in 21.1 s, 0 errors; about 46× faster than per-customer loading |
| Call recordings | Cloud speech API; local Whisper | **Local Whisper (base, CPU)**, evidence only | Audio is the most sensitive data; transcripts have no speaker labels, so they must not drive decisions | Transcription runs offline; cues are shown for a person to inspect and never change a recommendation |

## Why a small model and not an LLM for hardship detection

We measured it instead of assuming. `scripts/compare_llm_classifier.py` scored the same 126 held-out notes (38 with hardship; the customer-grouped split from `train_model.py`) with Gemini 3.5 Flash-Lite, zero-shot, given the POL-COLL-004 §4.2 hardship definition and told that vulnerability markers alone are not hardship. Measured 15 Oct 2026; raw results in `data/llm-comparison.json`.

| Detector | Hardship found | False alarms | Time per note | Same answer twice | Note text leaves the bank | Explains itself |
| --- | --- | --- | --- | --- | --- | --- |
| **What the app serves: model OR any cue** | **38 / 38** | **0** | under 1 ms | always | no | the cue and the sentence |
| Logistic regression alone | 36 / 38 | 0 | under 1 ms | always | no | 9 named weights |
| Rules only (any cue) | 38 / 38 | 0 | under 1 ms | always | no | the cue and the sentence |
| Gemini 3.5 Flash-Lite, zero-shot | 38 / 38 | 4 | 1.4 s median (5.7 s at the 95th percentile) | 40 of 40 re-asked notes | yes | a yes or no |

**What the four false alarms were.** Three are notes containing "cust vulnerable - financial hardship". In this bank's notes that phrase is a vulnerability tag (POL-COLL-004 §4.5), not a statement of hardship, which is why our cues deliberately exclude the bare word "hardship". Gemini flagged them despite the instruction. The fourth is a consumer proposal: an insolvency restriction, not a hardship case.

**At portfolio scale.** At the measured rate, scoring all 760,594 notes one at a time would take Gemini about 12 days of calls and send every note off-site; the local detector does the whole set in minutes on a laptop.

**Where an LLM can still help.** The synthetic notes reuse a small set of phrasings, so this test cannot show what an LLM would catch in real, free-form notes. That is why the LLM's role is to propose outcomes from a call note with a verbatim quote, which the agent accepts, and never to decide on its own.

## Backend request path

1. The browser (Next.js) calls `/api/*`; FastAPI checks the session and the role on every request (agents only see customers on their own cases).
2. The endpoint calls one engine: the **Rules engine** (`action_plan`, `call_session`, `work_queue`), the **Ask engine** (`insights`: question → validated plan → reviewed SQL with bound parameters, or BM25 policy search), or **Customer 360** (`customer360`).
3. Engines read DuckDB through a read-only connection and return JSON that carries its sources (record IDs, policy sections, SQL).
4. Only briefs, call notes, review decisions and audit events are written, to SQLite.
5. Gemini, when enabled, sits behind FastAPI: it receives a fixed task and a JSON schema, and its reply is validated before it reaches the engine's output. Without a key or on any failure, the local path answers.

Measured on the demo laptop: a Call Mode update takes about 0.17 s and a full brief about 0.23 s.
