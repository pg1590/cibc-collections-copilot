# Collections Copilot — Adda Wale

A local collections workbench built for the CIBC hackathon. It connects Customer 360, source-backed questions, a versioned Feature Store and agent briefs that require human review.

Team: Prakhar Gupta, Aryan Shrivastava, Krish Agarwal and Ved Maurya.

## Run locally

Python 3.10+ and Node.js 20.9+ are required. Use a separate virtual environment. The main release needs about 11 GB including the downloaded ZIP, extracted files and generated database. Allow additional room for build output. The optional voice pack is not required.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
.venv/bin/python scripts/fetch_data.py
.venv/bin/python scripts/build_data.py
.venv/bin/python scripts/train_model.py
```

The first command may require your OS's Python venv package. If the release is already available, put it at `data/maple_collections_release` or set `COPILOT_DATASET` to its absolute path. Dataset and model files stay local. The data build resumes completed tables and quality checks; `--reload` reloads source data. Stop API processes before rebuilding DuckDB.

Data source: [Maple Bank synthetic collections release](https://huggingface.co/datasets/nuxsh/maple-collections-hackathon), published by nuxsh under CC BY 4.0. Original files are preserved; this repository contains derived code, aggregate checks and generated benchmark answers. `requirements-lock.txt` and the frontend package lock record the verified dependency versions.

Start the backend in one terminal:

```bash
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Start the frontend in another:

```bash
cd frontend
npm ci
npm run dev
```

Open <http://127.0.0.1:3000>. Local demo accounts:

| Username | Password | Access |
|---|---|---|
| analyst | analyst-demo | Portfolio questions, C360 and data checks |
| agent | agent-demo | Customers with assigned cases and brief generation |
| supervisor | supervisor-demo | Portfolio, briefs, review decisions and audit |

Defaults are for the local synthetic-data demo. Environment variables in `.env.example` override them; export variables in your terminal before starting the backend. API credentials are not accepted in chat or committed. No paid runtime API calls are made. The agent defaults to the actual agent with the most open assigned cases; `COPILOT_AGENT_ID` selects another actual source agent. Role and case access are enforced by the backend.

## Demo flow

1. Sign in as supervisor and inspect the actual counts and data-quality report.
2. Search Customers and open a case. Compare its source keys, match rule scores, balances and latest note.
3. Ask a portfolio or policy question. Inspect the SQL or cited sources. Try an out-of-scope or protected-attribute request and inspect the refusal.
4. Generate a brief from a customer record. It shows financial evidence, structured features, model version, policy references and a draft.
5. Approve, reject or edit the draft with a reason. The decision persists and appends an audit event. Approval does not send a message or change a source case.
6. Inspect the Feature Store definitions, measured offline/live parity and heldout model evaluation.

## Four connected layers

| Layer | Implementation |
|---|---|
| Data Product Factory | Immutable raw CSV/Parquet; typed DuckDB curation; checked CRM duplicates and cross-source matches; C360; counted data-quality report |
| Insight/NLP | Local question planner, parameterized metric queries, current-policy retrieval, transcript evidence and explicit refusals |
| Feature Store | Structured case/payment/contact features and bilingual financial text cues; shared versioned definitions for batch/live paths; eager Polars/Pandera validation |
| Models/Decisioning | Local logistic classifier trained on public note labels; customer-grouped holdout and baseline; cited agent brief; persistent supervisor override |

Source names and types come from the actual release schema and headers. Identifiers preserve leading zeros. Only empty CSV fields become null: `NA`, `N/A` and `na` remain literal values. Invalid typed values are counted and preserved in raw data. Identity scores are rule scores, not calibrated probabilities. Review/unmatched identities are excluded from linked accounts. Loan status is derived from DPD/charge-off fields because the source has no `account_status` column.

The classifier receives only explicit binary financial cues. Protected attributes and unrestricted raw text are excluded from its input vector. Fairness groups are used only in a restricted evaluation report. The small synthetic labelled set does not establish production performance or measured business uplift.

## Benchmark and checks

```bash
.venv/bin/python scripts/run_benchmark.py --help
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q
cd frontend
npm run typecheck
npm run lint
npm run build
```

The benchmark exporter calls the same question engine as `/api/ask` and writes `question_id,answer,sql_or_sources,refused`. Released dev answers are for validation only, never runtime answer lookup. Extra questions must be added when released at 19:00 IST on 4 October. No answers are edited manually. The local query planner's supported intents and ambiguities are documented in its implementation review.

## Deliverables and design changes

- [C360 contract](config/c360-contract.yaml)
- [Implemented architecture](docs/architecture-build.pdf) and [PNG](docs/architecture-build.png)
- [Released benchmark CSV](submission/benchmark_answers.csv)
- [Counted data quality](docs/data-quality-report.md) — generated by the data build
- [Model evaluation](docs/model-evaluation.md) — generated by training
- [API contract](docs/api-contract.md)
- [Combined build plan](docs/reviews/build-plan-review.md)
- [Submitted design](docs/system-design.md) — historical design-phase document

DuckDB replaces the proposed CockroachDB storage for this local build. It can query the release's Parquet history directly and keeps setup manageable. SQLite stores reviews, sessions and append-only audit records. The Feature Store uses explicit versioned definitions rather than a separate service. Voice processing and optional orchestration frameworks remain outside this first build. The frontend uses Next.js, Tailwind and local shadcn-style components on Radix. RapidFuzz provides review-only name similarity diagnostics; acceptance requires the independent identity rules.

The implemented architecture has been rendered and visually checked. Pitch/demo artifacts still need preparation and the interface still needs browser visual review. Organizer submission, external deployment and collaborator invitations have not been performed. The deadline is 4 October 2026 at 21:00 IST; later commits are excluded. Keep the repository private and give access to the organizer identities once provided.

Verified locally: all 35 released benchmark rows generated without unresolved errors; all 12 numeric dev questions match the organizer's SQL references within tolerance; offline/live feature parity checked for 100 actual customers with zero mismatches; API integration covers source-backed questions, real-data briefs, persistent supervisor edits and audit. These are local checks, not an organizer score. The hidden test split and future extra questions are unverified.

## AI tool disclosure

Codex coordinates implementation, integrates modules and independently checks the result. Claude Opus 5.5 at high effort provided architecture reviews, the combined build-plan critique and assigned frontend/insight implementation work. Actual model metadata is checked locally; raw prompts/responses remain ignored. The original Feature Dev architect consultation used its default Sonnet subagent; later reviews and assigned engineering used direct Opus. No teammate contributions are fabricated and no top-10 selection is guaranteed.

This build starts without paid runtime LLM APIs. Later provider access can add narration or broader planning after its credentials, spend limit and checks are configured. The current local model and deterministic query paths remain reproducible.
