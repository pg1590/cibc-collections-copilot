# Consolidated design review

## Outcome
Select grounded agent assist: purpose-limited financial cue extraction, validated source references and a templated pre-call brief, with optional narrative. This can be assessed against deterministic baselines without assumed treatment/outcome labels. Next-best-action ranking is not implemented or claimed.

## Collaboration evidence
- Initial architect synthesis: Claude Opus 5.5, high effort. Feature Dev code-architect consulted once; its default subagent model was Sonnet 5.5. No application changes were made by Claude.
- Independent review of Codex corrections: directly Opus 5.5, high effort, no subagents.
- Final submission-source review after scale information arrived: directly Opus 5.5, high effort, no subagents.
- Completed response metadata confirms the model IDs. Raw responses and prompts are local and ignored by Git.

## Material changes from initial proposal
1. Conservative identity: no uncalibrated fuzzy auto-merges. Separate reference/customer states, pending-link warnings, source-specific fallback for a quarantined case key, coverage/precision reporting and rollback.
2. Correct grain: credit exposure only, own/joint balances separate by currency, account-grain portfolio reconciliation, no co-holder identity disclosure, multiple cases preserved.
3. Immutable publish run binding replaces the claim that a database historical timestamp is a publish-run identifier. Snapshot windows use data time.
4. Hardship: explicit approved financial context only. Broken promises/DPD do not imply hardship. Model cues remain in the restricted review store; C360 contains reviewed or authoritative source status.
5. Provenance is not semantic support: validate spans/numbers and independently review assertions. Measure coverage and abstention alongside precision; do not claim perfect protection from text filters or citation checks.
6. Approval: recheck live preconditions, separation of duties for referrals, atomic audit/outbox and idempotency. No LLM/network side effects inside retried transactions. No real customer actions.
7. Scope/scale: bounded CSV/Parquet jobs, latest snapshot plus necessary history, scoped/capped text retrieval, <=10 metrics and no ten-year backfill promise. Actual throughput/memory must be measured; one million customers is a source scale, not demonstrated capacity.

## Review judgment
The design includes all required headings and contract items. Its main unresolved limitation is missing field-level dictionary sheets: exact linkage coverage, approved identifiers, source sensitivity tags, metric definitions and consent semantics cannot yet be confirmed. No shortlisting guarantee is made.

The final Opus review suggested approving fuzzy score bands after sampled calibration if exact coverage is low. Codex retained individual/batch steward review of suggested links for the MVP: a sparse sample alone does not establish safe identity merges, and unresolved coverage should be reported rather than hidden. This may reduce unification coverage; the limitation is stated explicitly.

## Artifact validation
The generator checks six pages, all nine required design headings, contract owner/rules and all five team/member names on page 1. Poppler page renders are inspected locally before delivery. These are artifact checks, not application tests; application development has not started.

Latest visual QA after the supervisor's balanced technical revision: all six rendered pages inspected. Poppler text bounds keep body text above the footer (maximum body bottom 783.2 pt vs 795 pt bound). Required-heading/member/page checks pass; git diff whitespace check passes. The submission uses standard engineering terminology with contextual explanations while keeping only required design sections. The revision was checked by Codex; the earlier Opus reviews apply to the underlying design, not this wording revision. No application tests are claimed.
