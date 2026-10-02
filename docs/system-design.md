# Collections Copilot — Adda Wale

Members: Prakhar Gupta, Aryan Shrivastava, Krish Agarwal, Ved Maurya

Unified customer data. Evidence-based insights. Human-reviewed agent assist.

Architecture: [architecture.mmd](architecture.mmd)

Source fields remain TBC (to be confirmed). This is a design; it has not been built yet.

---

## Data foundation and business value

### Summary

Problem: fragmented customer records increase the time collections agents spend preparing for calls.

Use case: AI-assisted pre-call briefs with financial hardship flags for human review.

Users: collections agents, analysts, data stewards and hardship specialists.


### Business value

Primary metric: reduce median case-preparation time while maintaining factual accuracy. Compare the Customer 360 screen with the AI-assisted brief using the same five tasks: identify loan/card balances, overdue payments, payment promises, last contact and hardship evidence. Vary case order across testers; report task time, completion rate, correctness and sample size.

Evaluate hardship detection against a keyword-search baseline on independently labelled test cases. Report precision (how many flags are correct), recall (how many actual cues are found), false flags and uncertain cases. These are evaluation plans; no business improvement has been measured yet.


### Layer 1

Data pipeline: build Customer 360 (C360), a unified record with one golden customer ID. Python, Polars and DuckDB handle ETL: extracting source files, transforming them into consistent formats and loading checked records into CockroachDB. Preserve raw files, deduplicate records and validate schemas. AI suggests source-to-output field mappings; a data steward approves them.

Entity resolution: link customer IDs across product systems using approved, nonconflicting exact identifiers where available. RapidFuzz suggests similar records for manual review; fuzzy matches never merge automatically. Keep unresolved records separate and flag incomplete views. A versioned crosswalk, the source-ID-to-golden-ID mapping, supports rollback of incorrect links.

Data model: aggregate account and event records before joining them to customers, preventing duplicate balances or counts. Preserve multiple collection cases. Separate credit exposure (loan/card balances) by currency and sole/joint ownership; keep deposits separate. Portfolio totals count each joint account once without revealing another holder's identity.

Data lineage links every displayed fact to its source, transformation rule and date. Calculate recent-history windows from the supplied 28 September 2026 snapshot. A quality gate publishes a consistent data version only after required checks pass. On failure, retain the last passing version and show its freshness. Exact source mappings remain TBC (to be confirmed).


---

## Natural-language query service

### Layer 2

The Insight and NLP layer converts plain-English questions into controlled database queries. Example: "How many of my assigned card customers are at least 30 days overdue?" FastAPI exposes the backend API; Next.js provides the frontend.

1. Parse: a large language model (LLM) converts the question into a structured query plan containing a metric, filters and date range. It receives the metric catalog, which defines supported calculations, rather than raw customer rows. Unclear requests trigger clarification.

2. Validate: Pydantic checks the plan's structure and allowed values. Server-side authorization enforces user roles and assigned-case access. Reject unknown metrics, protected dimensions, unsafe combinations and SQL fragments. Model output never grants access.

3. Execute: SQLAlchemy builds parameterized, read-only SQL from approved templates. Filter values are passed as parameters rather than executable SQL. Use a restricted database account, a five-second timeout, a 100-row limit and one consistent published data version.

4. Respond: return the result, interpreted filters, SQL with sensitive parameters masked, source references and data freshness. Numbers come directly from query results; any AI explanation must stay within the verified output.

The initial catalog contains eight metrics: resolved customer count, provisional ID count, card exposure, loan exposure, days-past-due distribution, contacts in 30 days, payment-promise status in 90 days and identity-link coverage. Provisional IDs are unmatched or unconfirmed source identities, not confirmed unique customers. Disable metrics whose source definitions are unverified.

Refuse unsupported questions, cross-case access, protected-attribute profiling and write actions such as fee waivers. Explain the refusal briefly. Suppress aggregate results for groups smaller than five and monitor repeated queries that could expose individual information.

Validate 20 questions against reviewer-written reference SQL and test 15 refusal/access scenarios. Report result correctness, incorrect refusals and latency. No unauthorized or write query should execute.


---

## One AI use case: agent assist

### Layer 3

Inputs and features: when an agent opens an assigned case, use one published C360 version to assemble balances, days past due (DPD), recent promises/contacts, contact consent and reviewed hardship status. Exclude records newer than the snapshot. If identity matching is unresolved, show authorized source-specific facts and an incomplete-view warning instead of combined balances.

Evidence retrieval: check case access before loading notes or transcripts. BM25 keyword ranking and recency select a limited set of relevant customer records, each retaining its source and date. Mask direct personal identifiers before provider calls. The organizer-approved LLM provider is TBC. Treat retrieved text as untrusted input and give the model no tools or credentials.

The LLM extracts explicit financial hardship cues, such as income disruption or stated affordability difficulty, with supporting text spans. A template-based brief combines verified C360 facts with cited cues. Validate numbers, citation ownership and dates; remove unsupported statements. Overdue payments or broken promises alone do not establish hardship.

Human-in-the-loop review: AI cues remain "possible" until reviewed and cannot clear confirmed hardship flags. The agent inspects, edits or rejects the brief; a separate specialist reviews hardship referrals. Every suggested talking point shows the underlying fact or reviewed evidence.

Approval workflow: recheck assignment, consent and supporting-data changes before approval. Persist approval and the action record in one database transaction; use an idempotency key to prevent duplicate approvals. The prototype simulates actions only, with no customer messages, fee waivers or payment-plan changes.

Evaluation: compare cue extraction with keyword search and the assisted brief with a template-only baseline. Use independently labelled test cases; check factual support, precision, recall and uncertain responses. Report errors and cases where the model abstains because evidence is insufficient.


### AI usage

| AI component | Purpose and control |
| --- | --- |
| Schema-mapping suggestions | Interprets unfamiliar source columns; data steward approves the mapping. |
| Natural-language query planning | Interprets question wording; validators and authorization control SQL execution. |
| Agent-assist cue extraction | Finds financial hardship expressed in varied language; cited evidence and human review control use. |

---

## Scalability and governance

### Scalability

Batch processing: ingest files, resolve identities, run data-quality checks and publish C360. Start with the latest snapshot and required 30/90-day history. Process partitioned files in bounded batches to control memory usage.

Real-time APIs: handle questions, customer briefs and approvals. Use indexed customer IDs and retrieve only the current case's required records. The source overview lists about 1 million customers and 1.84 million accounts; benchmark throughput, peak memory and latency before claiming capacity at that scale.

Failure handling: if the LLM is unavailable, fall back to a template brief and metric-selection menu. If the database is unavailable, return a service error and disable approvals. Keep external AI calls outside database transactions.


### Governance

Role-based access control (RBAC): agents see assigned cases, analysts approved aggregates, specialists referral evidence and stewards identity/mapping reviews. Enforce authorization in the backend for queries, retrieval, citations and actions. Use least-privilege database roles and verify record-level restrictions.

Privacy and responsible AI: exclude protected attributes and proxy fields used as substitutes from decisions and query catalogs. Use only approved identifiers for matching. Limit model output to relevant financial categories; sensitive or uncertain evidence remains restricted to authorized reviewers.

Human review and audit: flag possible financial hardship without inferring diagnoses or protected identity. Customer-impacting actions require human approval. Maintain audit records containing the actor, data/model versions, evidence references and review outcome.

Monitor data freshness, quality failures, denied requests, unsupported claims, reviewer overrides, latency and provider errors. Use supplied synthetic data. Source sensitivity tags, retention rules and permission to send text to an AI provider remain TBC.


### Build plan

| Time (IST) | 36-hour implementation plan |
| --- | --- |
| 3 Oct, 09:00-10:00 | Profile dataset; confirm source mappings, target schema, metrics and database access. |
| 10:00-17:00 | Parallel tracks: ETL/C360, identity/quality, query API and agent-assist frontend. Integrate one complete case. |
| 17:00-23:00 | Add evidence retrieval, hardship extraction, review queues, approvals and audit. Run end-to-end checks. |
| 23:00-07:00 | Rest, light bug triage and reproducible batch-job checks; no new features. |
| 4 Oct, 07:00-15:00 | Test access control, reconciliation, identity rollback and failure paths. Run accuracy and task-time evaluation. |
| 15:00-21:00 | Freeze features, fix blockers, prepare demo and complete final team review. |

---

## Draft data contract

### Collections 360

Owner: Collections Operations lead (proposed, TBC). Technical steward: Adda Wale data team. Record grain: one customer per published data version. The schema below defines proposed output fields; physical source mappings remain TBC.


### Schema

| Proposed fields | Type and meaning |
| --- | --- |
| golden_customer_id; publish_run_id | UUID identifiers; together form the composite primary key for one customer/version row. |
| as_of_ts; published_at; crosswalk_version | UTC timestamps for snapshot/publication; integer version of the customer-ID mapping. |
| identity_status; pending_link_count | Status: resolved / partially_resolved / unresolved; nonnegative count of pending links. Pending links excluded from balances. |
| c360_exposure (child table) | Customer/version IDs, product, currency and own/joint credit balances (DECIMAL). Deposits separate; portfolio totals at account level. |
| account_count_by_product; open_case_count | Nonnegative integer counts of distinct accounts and cases. |
| worst_dpd; bucket | Nullable integer overdue days; overdue category definitions TBC. |
| promise_counts_90d; contact_count_30d; last_contact_ts | Nonnegative counts and nullable timestamp; promise-status definitions TBC. |
| consent_by_channel; reviewed_hardship_status; referral_status | Consent: allowed / denied / unknown. Source-confirmed or human-reviewed hardship/referral status. AI cues stored separately. |
| dq_status; lineage_ref | Data-quality status and references to source records, transformation rules and checks. |

### Quality rules and enforcement

1. Composite primary key is non-null and unique. 2. Every source customer record has an explicit matching status. 3. Credit balances reconcile to source accounts by currency, with joint accounts counted once in portfolio totals. 4. Events do not exceed the snapshot date and contributing facts share one published version. 5. Counts are nonnegative and protected/proxy fields are excluded from decision inputs.

Blocking failures stop publication. Retain the last passing version with its freshness shown. Missing optional values remain null; they are not inferred.


### Allowed uses and refresh frequency

Allowed: assigned-customer servicing, reviewed agent assist/referrals, authorized aggregate insights and data-quality monitoring. Prohibited: protected profiling, underwriting, marketing, autonomous customer actions and unapproved export/model training.

Hackathon: refresh on each organizer data drop. Proposed production: daily C360 plus intraday contact/promise updates. Cadence and retention are TBC with the owner. Recheck permissions at approval. Breaking changes need owner approval, a new contract version and consumer checks.
