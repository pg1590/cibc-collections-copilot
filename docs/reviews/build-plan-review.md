# Combined build-plan review

Reviewed 3 October 2026. User explicitly requested Claude's independent opinion and a consolidated plan. Claude Code was invoked directly with claude-opus-5-5 and --effort high, in read-only plan mode with Read/Glob/Grep and no subagents. Successful response metadata confirms only claude-opus-5-5 was used. Raw prompt/response remain local and ignored. The initial sandboxed attempt could not reach the API; the network-enabled retry succeeded.

No application implementation or organizer submission is authorized by this review request. A top-10 result cannot be guaranteed.

## Independent opinion and adjudication

Claude supports retaining agent assist but recommends prioritizing benchmark accuracy, earlier integration, demonstrable feature consistency and presentation over production infrastructure. Codex accepts the tighter schedule, smaller storage stack, manual source mappings, public-metric alignment, policy/bilingual evidence, real measurement and a separate fairness audit.

Corrections to Claude's review:
- Organizer wording is a working model OR agent. A trained classifier is not a mandatory Layer 4 deliverable. Train a lightweight baseline only if public label taxonomy supports the chosen task; never use self-generated weak labels as evidence of independently measured accuracy.
- Read-only SQL and SELECT parsing alone do not prevent data/file access or cross-case leakage. Expand the structured planner over approved views. A SQL-generation fallback is conditional on benchmark need and comprehensive table/column/function, external access, row-scope and resource-bound controls passing tests.
- Exact normalized multi-field matching does not automatically establish identity. Auto-link only approved, unique, nonconflicting strong rules after source-key inspection. Hand-checked precision and sample size are evidence, not blanket proof. Fuzzy suggestions remain review-only.
- The feature store must not feed a model its own predicted probability as an input feature. Store predictions separately with model/version metadata. Text language can select bilingual processing but is not a collections-risk/decision feature.
- Protected fields may be retained in a separate restricted evaluation dataset for the fairness checks explicitly allowed by organizers; they must not enter production decision features or general query catalogs. Group differences alone do not prove fairness or discrimination.

## Consolidated implementation proposal

Architecture: Polars/DuckDB for ETL, curated/C360 analytics and versioned structured/text feature snapshots; SQLite for transactional reviews/approval/audit; FastAPI API; Next.js plus shadcn/ui frontend. Explain replacing unprovisioned CockroachDB with this smaller local stack in README. Preserve the ability to migrate later; do not build migration infrastructure now. Keep Pandera, RapidFuzz and bounded per-case BM25. No voice, Feast, LangGraph, Splink or additional use cases in the first build. Use explicit reviewed source-mapping configuration rather than an AI mapping subsystem.

Layer 1: read release README/dictionary first; preserve string IDs, actual null/date conventions, raw lineage and snapshot rules. Match all five source systems under explicit rules, confidence/method/state, with unresolved cases reported. Publish after DQ checks and account-grain reconciliation pass. Generate counted DQ report and contract based on DC-COLL-001.

Layer 2: inspect benchmark categories and metric definitions immediately. Prioritize common approved metric templates, broaden structured query plans for supported filters/groups/time ranges, and handle policy questions through cited retrieval. Keep one /ask path for UI and benchmark CSV, not a question-ID answer lookup. Use public dev answers for development, reserve an untouched subset where size permits, test unseen paraphrases and refusal behavior. Actual scoring format comes from release README. SQL fallback only if needed and safe controls pass.

Layer 3: feature registry lists name/version/source/transform. Include structured financial and time-window features plus permitted text financial cues/counts with supporting source spans. One module builds both offline/training/evaluation and live features; saved artifacts include data/model versions. A parity test compares the same input/snapshot through both paths and reports mismatch counts/N. If released labels fit the task, a small TF-IDF/logistic-regression baseline uses customer-separated splits and the same preprocessing; otherwise keep the valid agent implementation and disclose that no task-appropriate supervised model was trained.

Layer 4: verified pre-call facts, uncertainty/coverage, source-cited hardship cues and policy-grounded talking points; original French evidence plus an English explanation where available. Human edits/rejects and role-scoped hardship referral review. Explain suggestions and use simulated actions only. Transaction plus unique idempotency constraint prevents duplicate approvals. Keep backend assignment/consent checks; drop production outbox and rollback UI, but retain link versions and basic correction/rebuild capability.

Differentiation: evidence-first bilingual agent assist, policy-cited suggested talking points and visible uncertainty, with measured errors and human overrides. Do not present it as proven business uplift. Run a separate basic fairness audit with explicitly protected evaluation fields and disclose sample counts and limits. Prioritize core correctness if time is short.

## Schedule, workstreams and stop rules

All times IST; milestones are targets, not claims of completion. Today (3 Oct): by13:00 data/dictionary/benchmark/label inspection, private repo, API contracts and provider choice; by15:00 a thin slice with all four layers, one real case and five representative dev answers; by21:00 full generated dev CSV, evaluation counts, feature parity and review flow. Prepare deck outline and demo storyboard today rather than waiting until tomorrow.

Tomorrow (4 Oct): morning accuracy/security/refusal/fallback fixes; feature freeze12:00; demo recording12:00-16:00; deck/export deliverables ready17:30; full timed benchmark rehearsal18:00; extra questions19:00; system-generated final CSV by20:15, final commit20:30 and form submission20:45 ahead of hard21:00 deadline. Aim for a benchmark rerun under20min; measure actual duration early. Reserve final window for new benchmarks, not video work.

Track A: ingestion/identity/C360/contract/countedDQ. Track B: query/policy retrieval/benchmark runner. Track C: feature registry/parity/agent/evaluation/review. Track D: integration/UI/reproducible run commands/architecture/demo/deck. Assign humans after confirming skills; record actual contributions and AI-tool usage, never manufacture teammate commits.

Cut new dependencies or features that take twice their allotted budget; keep main runnable and integration tests meaningful. If thin slice is late, cut UI polish/optional classifier/extra analytics first. Do not replace missing functionality with invented outputs. Explanations, authorizations, all four basic layers and required artifacts are retained. Final demo shows a dataset case, matched IDs/DQ, benchmark and unseen question with SQL/sources, legitimate refusal, evidence-backed hardship cue, human override/audit and real evaluation counts.

## Repository access

GitHub public API and connector now return404 for the existing repository, while authenticated SSH git ls-remote succeeds with the expected main SHA. This is consistent with the supervisor making the repository private; explicit owner-authenticated visibility metadata is not available through the connector. Existing SSH authenticates as pg1590 and provides the verified Git access path. No separate AI GitHub identity or collaborator invitation is required. Organizer accounts must be added after their identities are supplied; no invitations were sent.
