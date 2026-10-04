# Exact video script: HAC-4447

Target: **4 minutes 40 seconds**. Start already signed in. Read only the quoted narration aloud. Carry out the numbered actions while speaking. Values below were checked against the running website on 4 October 2026, using its 28 September snapshot.

## Set up before recording

1. Sign in at `http://localhost:3000` using **supervisor / supervisor-demo**. Set browser zoom to 100%. Enable your microphone and system audio in the recorder. Play back a short test recording.
2. Open these tabs in this order: **Overview** (`/overview`), **Customer HAC-4447** (`/customers/HAC-4447`), **Ask Collections** (`/ask`), **Briefs** (`/briefs?customer=HAC-4447`), **Reviews** (`/reviews`), **Data quality** (`/quality`), and the updated **AddaWale-Presentation.pdf**. Put the PDF on **slide 8** before recording.
3. In the customer tab, find **Voice evidence**. Confirm **VS-3510819**, duration **0:53**, and the cached machine-generated transcript with the **payment difficulty** candidate. Click **Load recording** and rehearse playback. Pause and rewind to the beginning. When the cached transcript is present, the speech-to-text button is disabled; that is expected. Do not delete the cache for the recording.
4. Have the three questions, note addition and review reason below ready to copy from a second screen or text editor. Read this script from a phone, printout or second display outside the captured browser window.
5. Do not prepare the final brief yet. Generate it at 2:30 during the recording so it is fresh and pending. A reviewed brief cannot be reviewed again. Keep its displayed brief ID in mind so you edit that exact record.
6. Avoid reading changing pending-review counts or generation times. Do not show passwords, API keys or settings. Start the recorder on **Overview**, after login.

## 0:00-0:20 - Overview

**Actions**

1. Show the Overview page. Point to the customer count and open cases.
2. Keep the cards visible while speaking.

**Say**

> We are Adda Wale, and this is Collections Copilot. It combines customer records, answers collections questions with evidence, and supports supervisor review. This synthetic snapshot contains 1,014,631 customer records and 96,000 open collections cases. I will demonstrate one customer throughout.

## 0:20-0:50 - Customer HAC-4447

**Actions**

1. Switch to the customer tab. The ID must be **HAC-4447**.
2. Briefly show **Identity matching** and **Accounts**, then stop at **Collections cases**.
3. Point to case **CS-2026-883987**, status **insolvency_hold**, overdue **314.53** and DPD **136**.

**Say**

> This is customer HAC-4447 in Ontario. The view contains four linked accounts and six source identity links. There is one open card case, with 314 dollars and 53 cents overdue and 136 days past due. Its status is insolvency hold, so the system must respect that restriction.

## 0:50-1:15 - A numeric answer and its SQL

**Actions**

1. Switch to **Ask Collections**. Paste Question 1 below and click **Ask**.
2. Show the answer or **Result rows**. Point to **1-30: 33,639**.
3. Expand **SQL or sources used**.

**Say**

> I ask how many collections cases are open by bucket. The results total 96,000, including 33,639 in the one-to-thirty-day bucket. The application calculates these values from the dataset. We can inspect the SQL and result rows instead of relying on an unsupported generated number.

## 1:15-1:40 - The policy for this customer's situation

**Actions**

1. Paste Question 2 and click **Ask**.
2. Show the newest answer. Expand **SQL or sources used**.
3. Point to **POL-COLL-001 v3.0 section 7.3**.

**Say**

> Next, I ask whether we can call someone who filed a consumer proposal. The answer cites the current policy, section 7.3. All collection contact stops from the filing date, and the case moves to insolvency hold. This is the rule relevant to HAC-4447.

## 1:40-1:55 - A refused request

**Actions**

1. Paste Question 3 and click **Ask**.
2. Show the **Not answered** notice and its reason.

**Say**

> A request to rank customers using gender is refused. Protected attributes and their proxies cannot drive collection priority or repayment predictions. The system explains why it will not answer.

## 1:55-2:30 - Actual audio evidence

**Actions**

1. Return to the customer tab and scroll to **Voice evidence**.
2. Show **VS-3510819**, then play about **three seconds** of audio and pause. Stay quiet during playback.
3. Show the machine-generated transcript and **payment difficulty** candidate. Expand **Approximate timestamps** briefly.

**Say**

> This customer has a supplied 53-second recording. Local Whisper transcribes the actual audio, and the result is cached. Here we can inspect the words, approximate timestamps and a payment difficulty candidate. Recognition can be wrong, and speakers are not identified. These candidates require review and do not change the customer's brief or contact restrictions.

## 2:30-3:15 - Generate the customer's brief

**Actions**

1. Switch to **Briefs**, confirm Customer ID **HAC-4447**, and click **Prepare brief**.
2. Show **Summary**: one open case and **CAD 314.53** overdue.
3. Show **Hardship evidence**, **Recommended next step** and **Why this recommendation**.
4. Scroll to **Internal note — do not contact the customer**. Point to the consumer proposal, case ID and section 7.3 citation.

**Say**

> The brief starts pending supervisor review. It reports one open case and 314 dollars and 53 cents overdue. The latest note contains no configured financial cue, but hardship is still recorded on the case. The consumer proposal and insolvency hold take priority. The recommendation is to hold contact and route to a supervisor. This box is an internal note, with the actual restriction and policy citation. It is not a customer message.

## 3:15-4:00 - Edit, save and inspect the audit

**Actions**

1. Click **Go to review queue**. On **Pending**, find the newest HAC-4447 brief with the ID just generated. If needed, click **Refresh**.
2. Select **Edit and approve**. In **Edited internal note**, go to the end of the existing text, add a space, and paste the **Note addition** below. Keep the original restriction and citations.
3. Paste the **Review reason** below into **Reason**, then click **Record decision**.
4. Open **Decided** and show the **Edited** badge and **Edited internal note — do not contact the customer** heading.
5. Refresh the browser, reopen **Decided**, and confirm the text remains. Scroll to **Audit log**, expand it, and show the newest **review_edit** event. Use its **Refresh** button if needed.

**Say**

> I now edit that fresh brief as the supervisor. I add a verification note and record the reason for the decision. The record moves to Edited and remains after refresh. The audit captures the edit, including the previous and final text. Recording this decision does not contact the customer or clear the hold. Contact remains blocked while the recorded restrictions are verified.

## 4:00-4:20 - Quality and teammate verification

**Actions**

1. Switch to **Data quality**. Use browser Find for **dpd_missing** and show **52,734** failed rows for **card_accounts**. Close Find.
2. Switch to the presentation tab already on **slide 8**. Point to the **23 checks** and **1,000 customers, 0 mismatches** rows.

**Say**

> Data quality reports 52,734 card rows with missing days past due. We preserve missing values rather than inventing them. Aryan's checker passes 23 C360 checks. Ved's checker finds zero feature differences across 1,000 customers, while customer-key coverage is checked across the full store.

## 4:20-4:40 - Close on slide 8

**Actions**

1. Keep slide 8 visible. Point to **337 passed**, **12/12** and **50 rows**.
2. Finish speaking, then stop the recorder. Do not add an outro.

**Say**

> All 337 automated tests pass, all 12 numeric development references match, and all 50 benchmark answers are generated. The app runs locally without an API key. These checks support the prototype. Hidden scores, production capacity and broader model accuracy remain unverified. Customer contact and eligibility decisions still require human control.

## Copy-ready inputs

**Question 1**

```text
How many collections cases are open today by current bucket?
```

**Question 2**

```text
Can I call a customer who filed a consumer proposal?
```

**Question 3**

```text
Rank customers for collection priority using gender.
```

**Note addition** - append this to the existing internal note

```text
Supervisor review: keep customer contact blocked while the recorded restrictions are verified.
```

**Review reason**

```text
Reviewed case CS-2026-883987 and POL-COLL-001 section 7.3. Consumer proposal and insolvency hold take priority over hardship. Keep customer contact blocked.
```

## Expected output reference - keep beside the script

| Item | Verified output |
|---|---|
| Customer | HAC-4447, Ontario, English |
| Linked records | 4 accounts, 6 source identity links |
| Open case | CS-2026-883987, card, insolvency_hold, special_handling |
| Current case amounts | 1 open case, CAD 314.53 overdue, 136 DPD, bucket 121-150 |
| Latest note | N-3535576, 18 September 2026; all six note cue flags are 0 |
| Recorded hardship | Present on CS-2026-883987, despite the latest note having no configured cue |
| Contact restriction | Consumer proposal on customer record and insolvency hold on the open case |
| Recording | VS-3510819, 53 seconds, historical call dated 24 July 2026 |
| Speech evidence | Cached transcript, 14 approximate segments, payment difficulty candidate, human review required |
| New brief | pending, contact_hold=true; hold recommendation overrides hardship |
| Supervisor edit | Edited badge; contact_hold remains true; audit action review_edit |
| Original build's feature check | Website Feature registry shows 100 customers and 0 mismatches |
| Independent checker | Slide 8 / Ved's report shows 1,000 customers, 15 columns, 0 mismatches |
| C360 checks | 23 passed on 1,014,631 rows |
| Application tests | 337 passed |
| Numeric references / benchmarks | 12/12 matched; 50 answers, 9 refusals, no unresolved answers |

The open-case answer has seven rows: 1-30 = 33,639; 31-60 = 25,389; 61-90 = 16,312; 91-120 = 10,251; 121-150 = 6,184; 151-180 = 4,045; 180+ = 180. The website sorts bucket labels alphabetically, so the displayed order differs from numeric order.

The brief's exact generated internal note is:

> Internal review only. Do not contact this customer. Recorded restrictions: insolvency hold on case CS-2026-883987; consumer proposal on the customer record. All collection contact stops from the filing date (POL-COLL-001 v3.0 §7.3). If a Licensed Insolvency Trustee represents the customer, all contact goes through that representative (POL-COLL-001 v3.0 §5.4).

Do not read a 26.55% score from the screen: that review score exists in the API response but the brief's model card does not display it. Do not quote an amount from the speech transcript as the current balance. Use CAD 314.53 from the case record. Historical recording dates do not establish when the proposal was filed. Global data-quality counts are not issues all affecting HAC-4447.

## Finish and upload

Watch the exported video once. Confirm the words and audio are audible, values are readable, and the duration is at most five minutes. Upload to Drive or similar with **Anyone with the link** access and test the link in a signed-out window. The presentation PDF is the slide attachment for submission. This script is a recording aid, not the presentation attachment. Use the latest code ZIP matching the final pushed revision.
