# Proposed target data model

The supervisor authorizes the team to choose tables, columns and relationships. This is the designed target model, not a claim about the organizer's physical 31-table schema. Incoming names, sensitivity tags and source enum meanings will be mapped when the dataset arrives. All timestamps use UTC after source-timezone validation; monetary values use DECIMAL(20,2) plus ISO currency, never floating point.

## Boundaries and tables

| Zone / table | Key | Essential proposed columns | Ownership / use |
|---|---|---|---|
| raw.ingest_manifest | ingest_id UUID | source_system, file_sha256, format, mapping_version, file_uri, row_count, rejected_count, loaded_at | Data steward; immutable raw drops outside OLTP |
| identity.golden_customer | golden_customer_id UUID | created_at, active/retired, superseding_id nullable | Stable identity registry; merge/split history retained |
| identity.source_identifier | identifier_id UUID | source_system, source_customer_key, identifier_type, approved normalized identifier, source_record_ref, validity | Restricted matching only; multiple identifiers of a type allowed; direct PII excluded from product/AI prompts |
| identity.crosswalk | source_system + source_customer_key + version | golden_customer_id nullable, state, method, confidence nullable, valid_from, reviewer_id | Current state linked/pending_review/quarantined/separate; history retained |
| identity.match_review | candidate_id UUID | left/right source references, match reasons, score, status, reviewer_id, reviewed_at | Candidate scores are not calibrated probabilities; no fuzzy auto-merge in MVP |
| curated.account | account_id + publish_run_id | source_system, source_account_key, product, currency, balance, dpd, is_joint, event_ts, lineage | Product card/loan/deposit; versioned account grain |
| curated.account_holder | account_id + golden_customer_id + publish_run_id | ownership_type, source_relationship_ref | Many-to-many; unknown sharing fraction never invented |
| curated.collection_case | case_id + publish_run_id | golden_customer_id nullable, account_id nullable, assigned_agent_id, status, event_ts, lineage | Customer may have multiple cases; unresolved identity does not grant broader access |
| curated.contact_event | contact_id + publish_run_id | case_id, golden_customer_id, channel, outcome, event_ts, source_record_ref | Event ID preserved; channel enums adapted, not invented as source facts |
| curated.promise | promise_id + publish_run_id | case_id, amount, currency, due_at, source_status, status_event_ts, lineage | Keep source outcome vs derived due/overdue status separate |
| product.publish_run | publish_run_id UUID | as_of_ts, completed_at, state, crosswalk_version, mapping_version, dq_report_uri, input_manifest_ids | staging/passed/failed; current pointer advances only after DQ passes |
| product.c360_customer | golden_customer_id + publish_run_id | identity_status, pending_link_count, account_counts, case_count, worst_dpd, dpd_bucket, contact_count_30d, promise_counts_90d, consent_map, reviewed_hardship_status, field_lineage | Proposed row-grain contract; normalized child exposure table avoids currency mixing |
| product.c360_exposure | golden_customer_id + publish_run_id + credit_product + currency | own_balance, joint_balance, source_account_ids/lineage | Credit products only; portfolio totals use account table, not sum of customer exposures |
| assist.evidence_item | evidence_id + publish_run_id | golden_customer_id, case_id nullable, source_record_ref, event_ts, span offsets, restricted_text_ref, sanitized_text, flags | Authorized and snapshot-bound before ranking; pending-identity text not cross-linked |
| assist.draft | draft_id + draft_version | case_id, publish_run_id, crosswalk_version, validated_features, cue_candidates with evidence IDs/offsets, coverage, rules_version, state, model/prompt metadata | Separate real-time possible cues from reviewed C360 hardship state |
| assist.hardship_review | review_id UUID | draft_id/version, golden_customer_id, specialist_id, reviewed_status, approved_category, evidence_ids, reason_code, reviewed_at | Different human from agent approver; no diagnoses/protected categories |
| ops.approval | approval_id UUID | draft_id/version, actor_id, role, precondition_versions/hash, accepted/rejected, approved_at | Unique draft/version/actor; changed consent/assignment/identity invalidates approval |
| ops.audit_outbox | event_id UUID | approval_id nullable, actor_id, event_type, refs, occurred_at, simulated_action nullable | Append-only; approval and simulated action row atomic, unique per approved draft action |

Eighteen compact tables are a proposed logical model; the implementation may combine review metadata into JSON columns while preserving invariants. No separate production feature-store service is required: C360 and each draft hold versioned feature snapshots. Semantic catalog definitions live in reviewed versioned configuration rather than a runtime-editable SQL table.

## Relationships
- One customer has many source references, accounts (through holders), cases, contacts and C360 versions.
- An account can have several holders; balances are counted once per account in portfolio measures. Seeing a joint balance never grants access to another holder's identity or accounts.
- A passing publish run supplies accounts, cases, events, C360 and evidence consistently. Composite foreign keys include publish_run_id wherever snapshot data join.
- A draft belongs to one case and immutable version; its evidence references and action preconditions are retained. One or more approval/review events accompany it. Simulated outbox entries require the approval in the same transaction.
- Crosswalk rollback writes history, identifies dependent drafts and forces review where underlying identity changed.

## Chosen semantic catalog (initial eight metrics)

| Metric ID | Definition / grain | Dimensions and guardrails |
|---|---|---|
| resolved_customer_count | Distinct resolved golden IDs in a passing run | Approved assigned-case scope; never mix provisional count into total silently |
| provisional_customer_count | Distinct separate/unresolved provisional IDs | Quality indicator, not a count of true unique people |
| card_exposure | Sum unique card-account balance per currency | Portfolio: account grain; case brief: own vs joint exposure |
| loan_exposure | Sum unique loan outstanding per currency | Source balance meaning confirmed by mapper; deposits excluded |
| dpd_distribution | Customer worst known credit DPD in proposed bands 0 / 1-29 / 30-59 / 60-89 / 90+ | Unknown DPD separate; exact treatment buckets not inferred |
| contact_count_30d | Count distinct contact events in (as_of-30 days, as_of] | Channel/outcome from approved source enums; event dedup keys required |
| promise_status_90d | Count distinct promises created in window, grouped by validated outcome at as_of | Unsupported source status mappings block the metric rather than guessing kept/broken |
| identity_linkage_coverage | Linked source references / eligible references, with pending/quarantine counts | Steward aggregate; metric is not identity accuracy |

Analyst aggregates suppress small cells and monitor repeated queries. Customer-level hardship is restricted to review workflows and not a general query dimension. Metric definitions are frozen before prompt tuning and evaluated using gold SQL plus held-out paraphrases.

## Scalability and verification
Use UUID primary keys, composite indexes on (publish_run_id, golden_customer_id), (golden_customer_id, event_ts), and source-key lookups. Select only needed Parquet partitions and fields; bound match candidate blocks, job batch sizes and per-case evidence. Do not infer tested throughput from source counts. A build-time measured capacity report declares rows processed, history range, bytes, elapsed time and peak memory on actual hardware.
