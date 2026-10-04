# Demo recording walkthrough

Target length: **4 minutes 40 seconds**, leaving room under the five-minute limit. Record the running website and speak over it. Use the actual synthetic dataset and keep the website readable at 100% zoom. The user will record and upload this video.

## Before recording

1. Confirm the backend is running at `http://127.0.0.1:8000` and the website at `http://127.0.0.1:3000`.
2. Sign in as `supervisor` with password `supervisor-demo`, unless you exported a different password. Use Customers search to open `HAC-4447` for voice evidence (`VS-3510819`, 53 seconds); `HOR-9340` has a shorter 15-second recording (`VS-11130`). Both were transcribed locally during verification, so their text is cached. Load audio and rehearse playback, then generate a rehearsal brief so you know the controls. Use a fresh pending brief during the recording.
3. Close unrelated tabs and notifications. Keep API keys, terminal secrets and account settings out of the recording.
4. Rehearse the three questions below. Their expected results apply to the synthetic snapshot of 28 September 2026. This walkthrough uses verified questions; it does not imply every possible grouping or wording is supported.
5. Start your recorder with microphone enabled. Use 1080p if available and verify that your voice is audible.
6. Keep [Aryan's C360 report](c360-contract-validation.md) and [Ved's feature parity report](feature-parity-validation.md) open in separate tabs for the verification segment. These are CLI checks; the website's Feature registry still shows the original 100-customer build check. The independently verified 1,000-customer result is in Ved's report. Prepare the reports before recording rather than waiting for the checker during the video.
7. Generate a fresh brief for `HAC-4447`: its consumer proposal and insolvency hold override hardship. The box is labeled **Internal note — do not contact the customer** and cites POL-COLL-001 §7.3. Describe supervisor verification of the hold, not a customer payment conversation. Older stored briefs keep their original text.

## Timed script

| Time | Show | Suggested narration |
|---|---|---|
| 0:00-0:25 | Overview | "We are Adda Wale. Collections Copilot brings customer records together, answers collections questions with evidence, and prepares briefs for human review. We use the synthetic Maple Bank release, with a snapshot of 28 September 2026." |
| 0:25-0:55 | Overview, then Customers | "The portfolio has 96,000 open cases. The data pipeline handles 31 source tables. This customer view links accounts, cases and the latest note, with the matching rule and source identifiers visible." |
| 0:55-1:35 | Ask Collections, numeric question and expanded SQL | "The application calculates this answer from source data. It shows the SQL and bound parameters so a reviewer can inspect how we obtained the number. Open means no recorded case outcome." |
| 1:35-2:05 | Policy question, then refusal | "Policy answers cite the current document. Requests to prioritize collections using protected attributes are refused with a reason." |
| 2:05-2:35 | Customer: Voice evidence, play a few seconds, show generated transcript and cue candidates | "We also process the optional synthetic recordings with local Whisper. Generated words and timestamps are review evidence. Speakers are not attributed, so these cue candidates do not change customer decisions." |
| 2:35-3:15 | Generate a brief for the customer selected earlier | "The brief combines actual case facts, financial text evidence, a local model score and policy references. Recorded hardship remains relevant even without a note cue; holds take priority, and the reason explains which rule fired. The model's heldout recall is 65.8%, so a low score cannot establish that hardship is absent. Every draft starts pending review." |
| 3:15-3:55 | Reviews: edit the internal hold note for HAC-4447 (or draft for a non-hold brief), enter reason, submit, refresh and show audit | "A supervisor can approve, reject or edit. For this held customer, the text is an internal note. I am documenting verification of the restriction. Refreshing preserves the decision and contact-hold indicator, and the audit records the change. Approval does not contact the customer or clear the hold." |
| 3:55-4:20 | Data quality and Feature registry; briefly show the prepared C360 and parity reports | "We count data issues and explain their handling. Uncertain identity links stay out of linked balances. Aryan's checker passes 23 contract and availability checks. Ved's checker finds zero differences across 1,000 customers and 15 feature columns, and checks customer keys across the full store. Feature values are sampled." |
| 4:20-4:40 | Overview | "All 337 automated tests pass, all 12 numeric references match, and all 50 benchmark answers are generated. Hidden scores and production performance remain unverified. The app runs locally without an API key. A company pilot would add incremental refresh, shared storage, capacity testing and broader model validation." |

## Questions to paste

1. `How many collections cases are open today by current bucket?`
   - Expected buckets: 1-30 = 33,639; 31-60 = 25,389; 61-90 = 16,312; 91-120 = 10,251; 121-150 = 6,184; 151-180 = 4,045; 180+ = 180. Total = 96,000.
2. `What is the grace period before a promise is considered broken?`
   - Expected: two business days, citing PRC-COLL-010 v2.1 section 3.3.
3. `Rank customers for collection priority using gender.`
   - Expected: refusal explaining that protected attributes cannot drive collection decisions.

Use only source-supported statements about the selected customer. If their brief shows no financial cue or a contact hold, describe that actual outcome. Do not invent hardship, support eligibility or a business improvement percentage. You can select a different permitted customer in rehearsal, but do not manually alter source records to create a demo outcome.

## Upload and access check

Export the recording and check its duration is no more than five minutes. Upload to Drive or a similar service. Set access to **Anyone with the link**, copy the playback link, then open it in a signed-out/incognito window and confirm that video and audio play without requesting access. Send the link to the teammate handling the team's single submission. Keep the code ZIP and presentation PDF as separate form attachments.
