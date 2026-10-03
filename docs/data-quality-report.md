# Counted data quality report
Snapshot: 2026-09-28. Built: 2026-10-03T06:37:29.700381+00:00.

Invalid typed values become null in curated data; raw files retain original values. Identity review records are excluded from linked balances. Confidence is a rule score, not a probability.

| Table | Raw rows | Curated rows |
|---|---:|---:|
| customers | 1,020,000 | 1,020,000 |
| card_accounts | 660,000 | 660,000 |
| loan_accounts | 404,500 | 404,500 |
| deposit_accounts | 780,000 | 780,000 |
| collections_cases | 367,229 | 367,229 |
| contact_history | 2,688,337 | 2,688,337 |
| promises_to_pay | 238,815 | 238,815 |
| agent_notes | 760,594 | 760,594 |
| call_transcripts | 25,000 | 25,000 |
| voice_samples | 2,000 | 2,000 |
| external | 1,000,000 | 1,000,000 |
| loan_instalments | 14,832,472 | 14,832,472 |
| transactions | 12,401,924 | 12,401,924 |
| card_statements | 7,531,283 | 7,531,283 |
| account_monthly_snapshot | 12,569,692 | 12,569,692 |
| bureau_history | 4,679,562 | 4,679,562 |
| salary_credit_history | 6,000,000 | 6,000,000 |
| model_scores | 1,718,841 | 1,718,841 |
| offers | 40,767 | 40,767 |
| metric_definitions | 15 | 15 |
| benchmark_questions | 35 | 35 |
| reference_documents | 19 | 19 |
| hardship_programs | 18 | 18 |
| qa_checklist | 10 | 10 |
| agents | 1,000 | 1,000 |
| case_assignment_history | 423,830 | 423,830 |
| agent_shifts | 15,317 | 15,317 |
| channel_capacity | 287 | 287 |
| ops_events | 6 | 6 |
| geo_reference | 656 | 656 |
| code_lookups | 113 | 113 |

| Check | Table | Failed rows | Total rows | Severity |
|---|---|---:|---:|---|
| crm_customer_id_unique_non_null | customers | 0 | 1,020,000 | error |
| contact_id_unique_non_null | contact_history | 0 | 2,688,337 | error |
| case_id_unique_non_null | collections_cases | 0 | 367,229 | error |
| ptp_id_unique_non_null | promises_to_pay | 0 | 238,815 | error |
| case_id_referential_integrity | contact_history | 26,864 | 2,688,337 | warning |
| coll_customer_ref_referential_integrity | collections_cases | 10,365 | 367,229 | warning |
| crm_customer_id_referential_integrity | agent_notes | 21,592 | 760,594 | warning |
| date_of_birth_missing | customers | 5,026 | 1,020,000 | warning |
| primary_phone_e164_missing | customers | 15,223 | 1,020,000 | warning |
| dpd_missing | card_accounts | 52,734 | 660,000 | warning |
| dpd_missing | loan_accounts | 32,179 | 404,500 | warning |
| contact_ts_utc_missing | contact_history | 0 | 2,688,337 | warning |
| dpd_bucket_disagrees_with_dpd | card_accounts | 24,205 | 660,000 | warning |
| dpd_bucket_disagrees_with_dpd | loan_accounts | 14,769 | 404,500 | warning |
| current_bucket_disagrees_with_dpd | collections_cases | 3,807 | 367,229 | warning |

Identity outcomes: `{"review_name_similarity_sample_size": 1000, "matched": 3671767, "review": 64145, "unmatched": 96355, "golden_customers": 1014631, "crm_records": 1020000, "confidence_kind": "Rule scores, not calibrated probabilities. Review/unmatched records are excluded from linked accounts."}`

Limits: referential and typing checks are measured across loaded tables. Matching precision requires independently labelled identity pairs; no claim of measured precision is made. No source row is dropped during typed curation.
