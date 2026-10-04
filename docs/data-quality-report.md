# Counted data quality report
Snapshot: 2026-09-28. Data built: 2026-10-03T06:37:29.700381+00:00.

The table below distinguishes handling from repair. Missing source facts and contradictory values remain unresolved when no authoritative correction is available. Raw source files remain intact. A row can fail several checks, so failed counts must not be added as a count of distinct customers.

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

| Check | Table | Affected rows | Total rows | Severity | Handling / correction |
|---|---|---:|---:|---|---|
| crm_customer_id_unique_non_null | customers | 0 | 1,020,000 | error | Check uniqueness and missing keys. No key is invented or silently reassigned; any failure requires review. |
| contact_id_unique_non_null | contact_history | 0 | 2,688,337 | error | Check uniqueness and missing keys. No key is invented or silently reassigned; any failure requires review. |
| case_id_unique_non_null | collections_cases | 0 | 367,229 | error | Check uniqueness and missing keys. No key is invented or silently reassigned; any failure requires review. |
| ptp_id_unique_non_null | promises_to_pay | 0 | 238,815 | error | Check uniqueness and missing keys. No key is invented or silently reassigned; any failure requires review. |
| case_id_referential_integrity | contact_history | 26,864 | 2,688,337 | warning | Retain raw/curated contacts and flag orphan case references. Do not invent a case link; case-joined queries cannot recover the missing case. |
| coll_customer_ref_referential_integrity | collections_cases | 10,365 | 367,229 | warning | Retain source rows in raw/curated and portfolio totals. Exclude unlinked CRM references from golden C360 cases; report the coverage gap. |
| crm_customer_id_referential_integrity | agent_notes | 21,592 | 760,594 | warning | Retain raw/curated notes. Exclude notes without a resolved CRM link from the golden latest-note view. |
| date_of_birth_missing | customers | 5,026 | 1,020,000 | warning | Preserve missing values. Match only when independent available evidence satisfies the identity rules; otherwise retain review/unmatched status. |
| primary_phone_e164_missing | customers | 15,223 | 1,020,000 | warning | Preserve missing values. Match only when independent available evidence satisfies the identity rules; otherwise retain review/unmatched status. |
| dpd_missing | card_accounts | 52,734 | 660,000 | warning | Preserve null DPD. Exclude unknown DPD from delinquency-rate calculations and report the denominator; do not impute a DPD value. |
| dpd_missing | loan_accounts | 32,179 | 404,500 | warning | Preserve null DPD. Exclude unknown DPD from delinquency-rate calculations and report the denominator; do not impute a DPD value. |
| contact_ts_utc_missing | contact_history | 0 | 2,688,337 | warning | Check timestamps and retain raw source values. Preserve missing values; do not fabricate a contact timestamp. |
| dpd_bucket_disagrees_with_dpd | card_accounts | 24,205 | 660,000 | warning | Count and retain both reported bucket and DPD. Use reported buckets for the applicable released benchmark and DPD where the metric specifies it; discrepancy remains unresolved. |
| dpd_bucket_disagrees_with_dpd | loan_accounts | 14,769 | 404,500 | warning | Count and retain both reported bucket and DPD. Use reported buckets for the applicable released benchmark and DPD where the metric specifies it; discrepancy remains unresolved. |
| current_bucket_disagrees_with_dpd | collections_cases | 3,807 | 367,229 | warning | Count and retain both reported bucket and DPD. Use reported buckets for the applicable released benchmark and DPD where the metric specifies it; discrepancy remains unresolved. |

## Identity resolution and normalization

The pipeline creates 1,014,631 golden customer records from 1,020,000 CRM rows. This is conservative identity resolution, not a claim of perfect recovery of the underlying one million people.

| Source-key outcome | Count | Handling |
|---|---:|---|
| Matched | 3,671,767 | Accept only the documented identity rules and unique-candidate margin. Rule scores are not calibrated probabilities. |
| Review | 64,145 | Keep candidate evidence for review and exclude these links from golden account balances. |
| Unmatched | 96,355 | Preserve source keys without fabricating a customer link; exclude these links from golden account balances. |

These counts refer to source keys across systems, not distinct people. Declared CRM duplicates merge only when date of birth and independent name or phone evidence agree. RapidFuzz name similarity is a review diagnostic and cannot independently authorize a match.

Mixed supported date formats become typed dates/timestamps. Customer IDs remain strings to preserve leading zeros. Only empty CSV fields become null; literal NA, N/A and na remain values. The question engine coalesces channel_v2 with channel for the recorded schema drift.

## Remaining limitations

No source row is dropped during typed curation. Golden views intentionally exclude unresolved links. Source-wide totals can therefore differ from linked C360 totals. Missing DPD, missing identity evidence, orphan references and bucket contradictions are reported rather than claimed as repaired. Matching precision and missed-match rates require independently labelled identity pairs; those measures are not available yet.

## Optional voice source verification

The official voice pack has 2,000 recordings. Every file size and SHA-256 matched `voice_samples.csv`; there were zero download/integrity mismatches. All 2,000 voice/transcript/contact links agree. Of these, 56 reference source cases that lack a linked golden case; 1,944 have verified case/customer linkage and can be served. The 56 are preserved locally and excluded from customer playback/transcription until identity resolution. No speculative customer association was added. WAV frame/format/duration checks also run on access.

For the extra cure-time question's period (1 July through 28 September), all 31,598 cured cases have nonnegative recorded cure duration consistent with `cure_date - case_open_date`; zero negative or inconsistent values were found. All 40,665 September outbound SMS send events with a payment link have a recorded click flag; zero unknown flags were found in that cohort. These focused read-only checks do not replace full-source data quality reporting.
