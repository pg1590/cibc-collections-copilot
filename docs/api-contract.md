# Local application API v1

Base `/api`, JSON. Snapshot 2026-09-28. Local calculations and reviews; optional Gemini requires a locally configured key. Backend is FastAPI on 127.0.0.1:8000; frontend on 127.0.0.1:3000. Frontend proxies `/api` to backend. Error responses use `detail`. Bearer token required except health and login. No fabricated fallback data.

- `GET /health`: `{status, dataset_ready, snapshot_date, runtime_mode}`.
- `POST /auth/login`: `{username, password}` → `{token, user:{username, role}}`. Demo credentials configured by local environment; README provides defaults for local use. Roles analyst, agent, supervisor. UI chooses account, never sends a trusted role claim.
- `GET /overview`: `{customers, open_cases, overdue_cad, identity:{matched, review, unmatched}, quality_issues, pending_reviews}`. Counts are actual pipeline results.
- `GET /customers?search=&limit=20`: `{items:[{customer_id,name,province,open_cases,total_overdue,max_dpd,identity_confidence}],total}`.
- `GET /customers/{customer_id}`: `{customer:{customer_id,name,province,preferred_language,identity_confidence},accounts:[],cases:[],identity:[],notes:[],features:{},snapshot_date}`. Agent restricted to assigned cases. Arrays contain source keys and evidence, never protected attributes.
- `POST /ask`: `{question}` → `{answer,sql_or_sources,refused,reason,rows:[],sources:[],execution_ms,snapshot_date}`. Analyst/supervisor only for aggregate questions; an agent can use scoped customer briefs.
- `POST /briefs`: `{customer_id}` → `{brief_id,customer_id,summary,signals:[{name,value,evidence}],recommendation,policy_sources:[],draft,status:"pending",model:{name,version},features:{}}`.
- `GET /reviews`: `{items:[{brief_id,customer_id,summary,recommendation,draft,status,created_at,decision,reason,reviewer}]}`.
- `POST /reviews/{brief_id}`: `{decision:"approve"|"reject"|"edit",reason,draft?}` → updated record. Supervisor only. A reason is required and editing requires a draft. Review records are persistent and append an audit event. Approval records a decision; it does not contact customers.
- `GET /audit`: `{items:[{event_id,at,actor,action,resource,details}]}`. Supervisor only.
- `GET /quality`: pipeline JSON `{snapshot_date,raw_counts,curated_counts,checks:[{check,table,failed_rows,total_rows,severity}],identity:{},built_at}`.
- `GET /features`: `{version,definitions:[],parity:{checked,mismatches},model:{}}`. Actual checked parity, never assumed.

## Additional review and generation fields

`/health` includes `gemini_configured` and the current runtime description. `/ask` can include a validated `plan:{metric_id,grouping,start_date,end_date,denominator,definition_source}`; the end date is exclusive. Numeric `answer` and `rows` remain local. Optional `explanation` and `explanation_sources` contain verified, complete evidence quotations shown separately.

Briefs/reviews include `recommendation_reason`, `hardship_status:"recorded"|"possible"|"not_established"`, and `recorded_hardship_cases`. Recorded hardship is a source flag, not reviewed eligibility. Holds override recommendations. The supervisor's `reason` remains separate from the system's recommendation reason. Optional `summary_evidence`/`summary_sources` never replace facts, recommendations or drafts.

`generation:{provider,status,model?,stages:{plan,summary},evidence_source_ids}` labels local/generated/fallback stages. Ask/brief audit records include generation metadata and evidence source identifiers. Keys and raw provider responses are excluded. Provider errors preserve local answers or request clarification, rather than inventing a result.

## Internal question module contract

`app.insights.InsightEngine(db_path, dataset_root, planner=None)` provides `answer(question, role="analyst")`. `app.runtime.answer` is the shared API/benchmark entry point; it caches immutable retrieval indexes and opens a separate read-only SQL connection for each request. Optional planning emits a validated metric/grouping/date object, compiled by `app.metric_plans`; no user/model SQL is executed. Database schema `curated` retains source-wide metric populations; linked customer briefs use C360. Policies/transcripts are local, with protected fields excluded from serving. Public reference answers are used only by the independent validation script. Default provider evidence permits only approved aggregate columns, policy paragraphs and redacted brief facts; note/transcript text requires explicit opt-in.
