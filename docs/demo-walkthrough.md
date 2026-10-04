# Demo recording walkthrough

Target length: **4 minutes 40 seconds**, leaving room under the five-minute limit. Record the running website and speak over it. Use the actual synthetic dataset and keep the website readable at 100% zoom. The user will record and upload this video.

## Before recording

1. Confirm the backend is running at `http://127.0.0.1:8000` and the website at `http://127.0.0.1:3000`.
2. Sign in as `supervisor` with password `supervisor-demo`, unless you exported a different password. Open a customer record and generate a rehearsal brief so you know the controls. Use a fresh pending brief during the recording.
3. Close unrelated tabs and notifications. Keep API keys, terminal secrets and account settings out of the recording.
4. Rehearse the three questions below. Their expected results apply to the synthetic snapshot of 28 September 2026. This walkthrough uses verified questions; it does not imply every possible grouping or wording is supported.
5. Start your recorder with microphone enabled. Use 1080p if available and verify that your voice is audible.

## Timed script

| Time | Show | Suggested narration |
|---|---|---|
| 0:00-0:25 | Overview | "We are Adda Wale. Collections Copilot brings customer records together, answers collections questions with evidence, and prepares briefs for human review. We use the synthetic Maple Bank release, with a snapshot of 28 September 2026." |
| 0:25-0:55 | Overview, then Customers | "The portfolio has 96,000 open cases. The data pipeline handles 31 source tables. This customer view links accounts, cases and the latest note, with the matching rule and source identifiers visible." |
| 0:55-1:35 | Ask Collections, numeric question and expanded SQL | "The application calculates this answer from source data. It shows the SQL and bound parameters so a reviewer can inspect how we obtained the number. Open means no recorded case outcome." |
| 1:35-2:05 | Policy question, then refusal | "Policy answers cite the current document. Requests to prioritize collections using protected attributes are refused with a reason." |
| 2:05-2:55 | Generate a brief for the customer selected earlier | "The brief combines actual case facts, financial text evidence, a local model score and policy references. These six financial cues support hardship review. The model's heldout recall is 65.8%, so a low score cannot establish that hardship is absent. Every draft starts pending review." |
| 2:55-3:35 | Reviews: edit draft, enter reason, submit, refresh and show audit | "A supervisor can approve, reject or edit. I am editing the draft and recording why. Refreshing preserves the decision, and the audit records the change. Approval records a decision and does not contact a customer." |
| 3:35-4:10 | Data quality and Feature registry | "We report issue counts and explain their handling. Uncertain identity links stay out of linked account balances. Training and live scoring share versioned features, and the offline/live check found zero mismatches across 100 customers." |
| 4:10-4:40 | Feature registry/model evaluation or Overview | "All 12 numeric development questions match the reference SQL. We have not verified hidden answers or production performance. A company pilot would add incremental refresh, shared persistent storage, concurrent-user testing and broader model validation. The app runs without paid AI API calls." |

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
