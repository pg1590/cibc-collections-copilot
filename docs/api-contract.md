# Local application API v1

Base `/api`, JSON. Snapshot 2026-09-28. Runtime uses no paid API. Backend is FastAPI on 127.0.0.1:8000; frontend on 127.0.0.1:3000. Frontend proxies `/api` to backend. Error responses use `detail`. Bearer token required except health and login. No fabricated fallback data.

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

## Internal question module contract

`app.insights.InsightEngine(db_path: str|Path, dataset_root: str|Path)` has `answer(question: str, role="analyst") -> dict` with the `/ask` response keys. Database contains schema `curated` with source table names and dictionary physical types, normalized dates, empty-only nulls. Raw text remains in schema `raw`; keys retain leading zeros. Parquet history views are in curated. Policies and transcript JSON are local under dataset root; no gold-answer lookup at runtime. Public dev gold can only support independent validation. Module opens read-only DuckDB connections, disables external access after opening, uses fixed query templates with bound parameters. It does not execute user SQL or call an API. Own CLI benchmark exporter calls this same method.
