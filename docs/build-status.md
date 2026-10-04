# Build status - 4 October 2026

The four-layer local application and priority correctness fixes are implemented. Optional Gemini is integrated; without a key, calculations, extraction, classifier and reviews run locally. Source data, databases, models, credentials, restricted fairness details and raw AI outputs stay local.

## Verified

- 210 automated tests pass, including roles, hardship/hold priority, metric/date/cohort validation, provider fallback/concurrency, privacy, evidence and persistent review/audit.
- All 12 numeric public development references match within tolerance. All 50 benchmark rows (35 original plus 15 extra) regenerate through the shared API pipeline, with nine refusals and zero unresolved results.
- 62 reviewed metric/grouping SQL combinations pass EXPLAIN. The 15 metric-definition examples return a supported plan or explicit clarification.
- Frontend TypeScript, lint and production build pass. Local HTTP checks pass customer views, metrics, refusals, local-model briefs, supervisor edits, audit and assigned-case access. No rendered-browser claim is made.
- Voice pack: all 2,000 sizes/checksums verified; 1,944 case/customer-linked recordings served. Local offline Whisper base transcribed three evaluation calls; a fourth real API job completed through the frontend proxy. Playback, source hash and cached transcript checks passed. Exploratory three-call WER is 22.03%; no broad accuracy or speaker-attribution claim.
- Offline/live feature parity remains 100 customers, zero mismatches. The classifier is unchanged: heldout precision 89.29%, recall 65.79%, F1 75.76% on 126 customer-grouped notes; 374 training notes. These are small synthetic-data results, not production or business-uplift evidence.
- The counted quality report and proposed C360 contract are present. The pipeline has 1,014,631 conservative canonical customer records; identity precision remains unmeasured.
- Architecture PDF/PNG and nine-slide presentation are refreshed and visually inspected. A 4:40 recording walkthrough and clean-commit ZIP builder are available.

Actual Claude Opus 5.5 high-effort reviews and extractive implementation were integrated and independently checked by Codex. See [the correctness release](reviews/correctness-gemini-release.md) for decisions, evidence, exclusions and remaining gaps.

## Before final submission

1. The owner confirmed `cibchack26` was invited and appears in repository access before 17:00 IST. Acceptance has not been independently checked. The repository must stay private.
2. Save the Free-tier Gemini key locally if live verification is wanted. The key file was absent during checks; mocked tests do not prove provider availability or server-side schema compatibility.
3. Record/upload the <=5-minute video using [the walkthrough](demo-walkthrough.md), then check anyone-with-link playback. Complete the browser rehearsal.
4. The 15 extra questions are included and the 50-row CSV is generated. Refresh the PDF and archive from the final clean committed/pushed revision before 21:00.

Programme eligibility, rolling per-case contact enforcement, classifier improvements and multi-user capacity remain outside the verified build. No deployment, automatic customer contact or one-time form submission has occurred. Follow [the submission checklist](submission-checklist.md).
