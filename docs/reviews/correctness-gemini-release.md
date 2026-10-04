# Correctness fixes and optional Gemini integration

Implemented 4 October 2026 after the supervisor approved the combined review. The work addresses the priority gaps in `improvement-plan.md`; it does not claim production readiness or a higher organizer score.

## What changed

- Briefs check hardship recorded on open C360 cases, with case IDs as evidence. Holds take priority, then recorded hardship, then possible financial cues/model signals. Every recommendation explains the rule that fired. Source hardship, possible cues, human review and programme eligibility remain separate.
- The metric compiler supports 13 reviewed metric definitions/extensions and 47 metric/grouping combinations. Identifiers are fixed in code and dates are bound parameters. Local intents and optional Gemini plans use the same compiler. Unknown groupings, filters, historical snapshots and ambiguous cohorts clarify instead of silently substituting a population.
- Period parsing handles calendar months, previous month, years, quarters and explicit ISO dates. Cross-year natural-language ranges request ISO endpoints. Roll-rate plans use the two requested available month ends and supported destination buckets; they do not always bind June. Late-fee comparisons require explicit valid days.
- The pilot diagnostic selects the first randomized assignment before filtering hardship at that assignment. It measures cures within 30 days of assignment, includes only fully observed assignments, and applies the documented cure exclusions. The output states that current holds are used because historical hold status is unavailable. This is a descriptive comparison, not a causal uplift claim or an eligibility rule.
- Policy extraction retains complete source paragraphs and qualifications. It falls back to the full section if shortening could lose conditions. HPT-2026 now has its real `document` citation. Call answers group exact statements and confirmations with original speakers and timestamps; no hardship determination is inferred.
- README, API contract and proposed C360 contract describe actual behavior, design changes, configuration and limitations. The architecture and presentation use conventional code-drawn shapes and text. The classifier, features and eight-field C360 summary are unchanged.

## Optional Gemini

`app.runtime` is shared by the API and benchmark exporter. Gemini receives a metric catalog and question, returns a structured plan, and never supplies executable SQL. Backend validation checks the metric, grouping, dates and empty filter set before compiling reviewed SQL. Numeric answers remain DuckDB results.

Optional explanations select up to three complete supplied evidence units. Every source identifier and entire quotation must match before display. Explanations and brief evidence are separate from original facts, recommendations and drafts. A timeout, quota failure, invalid response or exhausted process budget preserves local behavior or requests clarification; it does not fabricate an answer.

By default, provider evidence is limited to approved aggregate columns, current policy paragraphs, and redacted brief facts/reasons. Case/note IDs in outbound brief text are redacted. Notes and transcripts remain local unless `COPILOT_GEMINI_TEXT_EVIDENCE=1` is explicitly set. Queries/catalogs may be sent for planning. Requests use `store=false`, bounded input/output, no retries, short network locks and a bounded cache. Generation stages and evidence source identifiers are audited.

The default is `gemini-3.8-flash`, with `gemini-3.5-flash-lite` allowed as an alternative. Use a Free-tier AI Studio project. The client cannot inspect billing tier; its budget is per process and resets on restart. Protocol fields were checked against the [official Interactions reference](https://ai.google.dev/api/interactions-api) and [structured-output examples](https://ai.google.dev/gemini-api/docs/get-started). This is not a fine-tuned model: the dataset remains the local calculation and evidence source.

At verification, `data/gemini-key.txt` was absent and health reported local mode. Mocked provider tests pass, but a live call and server-side schema compatibility remain unverified. Save the key only in that ignored local file or an environment variable, never Git or chat.

## Verification

- 131 automated tests pass: roles, hardship/hold priority, source evidence, metric cohorts, dates, refusals, provider failures/concurrency, privacy and persistent review/audit.
- All 12 numeric public development references match within tolerance. The exporter generates all 35 released questions, six refusals and zero unresolved answers; no answer cells were manually edited.
- All 15 released metric-definition examples produce a supported plan or an explicit clarification. This is coverage of those examples, not a heldout rephrasing accuracy score.
- All 47 catalog/grouping SQL combinations passed read-only EXPLAIN against the actual schema.
- Frontend typecheck, lint and production build pass. Local HTTP checks pass customer views, questions, brief generation, supervisor edit, audit, roles and assigned-case access. A rendered-browser walkthrough remains for the team.
- The architecture PDF/PNG and all nine presentation pages were rendered and inspected. The backup ZIP must be refreshed from the final clean commit.

## Claude collaboration and remaining work

Actual Claude Opus 5.5 at high effort completed improvement-plan, runtime and final core reviews, and implemented `app/policy_summary.py` with focused tests. Response metadata confirmed that model only. Codex independently evaluated the reviews, implemented/integrated the core changes and ran verification. A larger Claude query-engine implementation attempt was stopped without a patch; its work is not credited as completed. The supervisor explicitly approved relevant private source-code transfer to Anthropic; keys and raw datasets were excluded from the new scoped tasks. Raw prompts/responses remain local and ignored.

Deferred items need separate validation: programme eligibility and missing inputs, rolling per-case/channel contact enforcement, transcript-label scoring, classifier recall improvements, broader C360 fields, unseen-question accuracy and multi-user capacity. The existing customer-wide contact feature is not used to assert compliance with the rolling per-case call limit. No retraining, production deployment, automatic contact or form submission occurred.

The owner confirmed the organizer invitation appears in repository access before 17:00; acceptance has not been independently checked. The recorded video and 15 extra questions released at 19:00 remain. Final answers, presentation and code ZIP must be refreshed before the 21:00 deadline.
