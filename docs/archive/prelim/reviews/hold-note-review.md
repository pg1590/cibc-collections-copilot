# Restriction-specific internal hold notes

Implemented the supervisor's request in the local `claude-hold-draft-request.md` handoff. A generated hold brief now persists `contact_hold: true`, used by both Briefs and Reviews to label the text as an internal no-contact note. Ordinary briefs receive false; historical records are not rewritten.

The note lists actual recorded case/customer restrictions once. Insolvency, bankruptcy or consumer proposal cites POL-COLL-001 v3.0 §7.3 and conditional representative guidance from §5.4. Cease-contact/communication cites §5.4. Deceased-only notes request supervisor verification without inventing a procedure or citation. Combined insolvency/deceased holds suppress the cease-communication letters exception. The existing recommendation priority, pending status, policy_sources list and internal do-not-call behavior remain unchanged.

Codex verified the policy text in the supplied release. Actual Claude Code review completed using `claude-opus-5-5`, high effort, all tools disabled and no permission denials; relevant source/tests only were supplied. Raw prompts and responses remain ignored. The combined-hold guidance and review edit labels were corrected after review. Conditional serializer/boolean concerns were checked: the payload is persisted intact and hold is already computed with bool(hold_evidence).

Verification:

- **337 Python tests passed**, including restriction-specific notes, combined holds, hold priority, review persistence and mocked Gemini success/failure preserving the note and indicator.
- Frontend typecheck, lint and production build passed.
- A fresh **HAC-4447** brief through the website API names its consumer proposal and **CS-2026-883987** insolvency hold, remains pending with recorded hardship, and persists contact_hold true.
- All **50 benchmark answer rows** remained byte-for-byte unchanged.

No rendered browser was available for visual inspection. The local API and production build were verified; regenerate the brief in the website to see the new label. No source data, classifier, eligibility rule or customer-contact action was changed.
