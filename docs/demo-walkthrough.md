# Finals live demo: script and fallback

About 9 minutes, then Q&A ([finals-judge-qa.md](finals-judge-qa.md)): 2 minutes of slides on how we decided, which the organisers asked every team to cover before the solution, then a 7-minute live demo whose centrepiece is a live call with JEV-1240 (3:00 of the 7). If the slot is shorter, drop the demo rows marked *(optional)*; never drop Part 1. Every customer and value below is pinned by `tests/test_demo_customers.py` and checked in a real browser by `scripts/e2e_finals.mjs`. Run both on the demo laptop the morning of the finals.

Roles: one **driver** clicks (the laptop), one **narrator** speaks; swap at the call so the driver plays the agent. Gemini stays off on stage; note extraction uses the local rules, which give the same result for the note below.

## Before going on stage

1. Start the backend with a clean review store, so Supervisor review shows only today's items:

```bash
COPILOT_STATE=data/finals-demo-reviews.sqlite3 COPILOT_GEMINI_ENABLED=0 .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

2. Start the frontend as a production build (no dev-mode overlay, faster pages):

```bash
cd frontend && npm run build && npm run start
```

3. Make sure `data/plans-report.json` exists (`.venv/bin/python scripts/batch_plans.py`, about 20 seconds), so the Overview shows the next-step chart.
4. Open <http://127.0.0.1:3000>, sign in as `supervisor` / `supervisor-demo`, and open each page once, plus `/call/JEV-1240`, so the first load is warm. Reload `/call/JEV-1240` just before going on, so the call starts empty.
5. Rehearse the Overview scroll: **What's at stake** is a scrolling sequence (one big number at a time, with three dots under it showing which). Scrolling too fast skips the $18.0M figure the opening line depends on; scroll back up if that happens.
6. Keep the call note below in a text file to paste. Keep a second browser profile signed in as `agent` / `agent-demo` for the access question.
7. Fallback: the screenshots in `data/finals-shots/` (desktop and phone, including `call-JEV-1240.png`) and the recorded run. If the live app fails, switch to them without apologising and keep the same narration.

Call note to paste at 4:10:

```
Customer lost his job last month. He can pay $315.86 on October 15. Asked us to call back next week.
```

## Part 1: Why we built it this way (slides, about 2 minutes)

The organisers asked for the backend architecture, the reason for each model and LLM choice, and the decision process before the solution. Say the reason first, then the choice.

| Slide | Say |
|---|---|
| 2. The problem | "Before every call an agent has to check eight things: legal hours in the customer's time zone, holidays, a 3-in-7-days cap, insolvency, representatives, disputes, vulnerability, hardship before payment. Get one wrong and it's a breach." |
| 3. What we found | "We ran those checks over all 96,000 open cases: 760 contacted more than allowed this week, 1,040 contacts outside legal hours, 18,758 customers in hardship with no plan." |
| 4. How we decided | "So before writing code we set five constraints: compliance first, explainable, customer text stays inside the bank, works on the next data release, and every number measured. Then one rule for every job: if policy states the answer, rules; if it's a pattern in text with labelled examples, a small model; if it's language we can check against a source, an LLM that proposes and the app verifies; otherwise a person decides." |
| 5. Backend architecture | "Data is prepared once into DuckDB, a columnar database in one file: a 30-day scan of 2.7 million contacts takes a few milliseconds, and the app only reads it. FastAPI checks the role on every request and calls one of three engines; every answer carries its source record, policy section or SQL. Decisions and the audit log go to a separate SQLite file, hash-chained so tampering shows. Gemini sits behind the API and is optional." |
| 6. Why this model, why this LLM | "We didn't assume an LLM would be better; we measured it. On the same 126 held-out notes, Gemini found the same 38 hardship notes but raised 4 false alarms. Three were notes tagged 'cust vulnerable - financial hardship', which our policy treats as vulnerability, not hardship. It took 1.4 seconds a note instead of under a millisecond, and it would send every note out of the bank. So the small model flags hardship, and the LLM only proposes where a person checks. We use Gemini 3.5 Flash-Lite because it is on our free tier, returns schema-checked JSON in under 2 seconds, and 3.8 Flash was overloaded the day we tested." |

## Part 2: Live demo (about 7 minutes)

| Time | Do | Say |
|---|---|---|
| 0:00 | Overview: scroll down to **What's at stake** and keep scrolling slowly; the big number changes from $69.8M to $18.0M to $338.6K as you go, so pause on each | "This is debt collection: customers who already owe the bank money. $69.8 million is exposed on cases about to be written off, and $18 million is overdue from 18,758 customers in hardship who have no plan." |
| 0:25 | Point at the next-step chart, then scroll to **Problems across all customers**; open **Definition and SQL** on 760 | "Every night we plan every open case: 93,320 customers in 21 seconds. Before every call an agent has to check eight things. When nobody does: 760 cases contacted more than allowed this week, 1,040 calls outside legal hours. Every number is one query, shown here." |
| 1:00 | **Work queue** (agent AG-7514), point at the reason column | "One agent's day, in a fixed order, not a model score. Each row says why it is there and when we may call next." |
| 1:20 | Ctrl+K, type `SAV-6847`, open the customer | "Ctrl+K gets to any customer." |
| 1:30 | Customer page, **History & contact** tab: the calendar | "When can we call her? Monday and Tuesday are blocked: three attempts in seven days. Wednesday is the National Day for Truth and Reconciliation. So Thursday, 7 am to 9 pm her time. Holidays are computed for any year, not typed in." |
| 1:55 | *(optional)* Scroll the timeline | "One history across the source systems: calls, texts, emails, promises, notes, hardship offers and cases. A contact made outside the rules is marked in red; she has one." |
| 2:10 | Ctrl+K, `JEV-1240` → **Call: Jérôme Vallée** | "Now a live call. Jérôme has an auto loan, 86 days past due, and prefers French; the script tells the agent to offer French." |
| 2:25 | **Who answered?** Customer; tick **Recording notice** and **Verify identity** | "Nothing about the debt is shown until the recording notice is read and identity is verified." |
| 2:45 | Tick **Hardship**; point at the **Live plan** and **Hardship options** | "He says he lost his job. The plan changes immediately: offer a hardship programme before any payment request. These are his real numbers: $631.72 a month drops to $315.86 for three months, which the agent can approve. A term extension is $578.71, but needs a hardship specialist. Payment deferral is not offered, and it says why: 86 days is over the 60-day limit." |
| 3:20 | **Choose** on the 3-month reduced payment | "He takes the reduced payment." |
| 3:30 | Income $2,400, expenses $1,900; promise $315.86 on 15 Oct | "Is the promise affordable? $315.86 is 63% of what he has left, so it warns the agent. It is within 21 days, so the date is accepted." |
| 3:55 | *(optional)* Change the date to 30 Nov, show the block, set it back to 15 Oct | "Past 21 days, it is blocked and says the last allowed day." |
| 4:10 | **Call notes**: paste the note, **Extract from notes** | "Agents type fast. Extract proposes outcomes, each with the exact sentence it came from. Nothing changes until the agent accepts. With Gemini on, a proposal whose quote is not in the note is thrown away." |
| 4:35 | Go to wrap-up: the generated **Call note for the record**, outcome codes, follow-ups | "The note is written for the agent with the policy cited, the codes are set, and the one reminder before the 15th is scheduled. It counts toward the weekly cap." |
| 4:55 | **Submit for supervisor review** | "It goes to a supervisor; nothing is sent to the customer." |
| 5:05 | Ctrl+K, `HAC-4447` → Call | "And when the agent must not call: consumer proposal. The call page is blocked and the controls are off. Contact goes through the trustee." |
| 5:25 | **Supervisor review**: open the call note, **Approve** with a reason | "The supervisor sees the call note and outcome codes, and approves, edits or rejects with a reason. Every action is in an append-only audit." |
| 5:55 | *(optional)* **Ask Collections**: "Which province has the highest promise-kept rate in August 2026?" | "Judges' questions: a plain-English answer, then the table and the SQL. If we can't answer correctly, it asks for clarification instead of giving a wrong number." |
| 6:25 | Close on Overview | "It works on the next data release without code changes: dates, holidays, caps and policy versions all come from the data, and we test that with a fake 2027 release. Rules decide, people approve, and every step cites its policy. That is what makes it safe to put in front of agents." |
| 7:00 | End | |

## Expected values (snapshot 28 September 2026)

| Where | Value |
|---|---|
| Overview, What's at stake | $69,768,875.93 exposure (expected-loss estimate $28.8M, overdue $8.1M); $18,032,649.80 overdue, 18,758 customers; $338,605.98 on 348,411 contacts |
| Overview, next steps (batch) | 93,320 customers in 21.1 s: payment ask 39,834; promise 19,517; hardship 18,006; restriction 8,892; representative 5,176; vulnerability 1,895 |
| Overview tiles | 18,758 customers; 760 cases; 1,040 contacts; 4,100 cases; 7,052 promises; 729 cases; 3 cases |
| Queue AG-7514 | 296 open cases: 18 promise due soon, 74 hardship with no plan, 189 standard, 15 on hold |
| SAV-6847 calendar | Mon 28 and Tue 29 Sep: cap (3 of 3); Wed 30 Sep: holiday; Thu 1 Oct 07:00-21:00 America/Toronto |
| JEV-1240 call | HP-LOAN-RED3 $631.72 → $315.86 for 3 months, $947.58 moved to the end, approver agent; HP-LOAN-EXT $578.71 over 74 months, hardship specialist; HP-LOAN-SKIP not eligible (86 days past due, limit 60) |
| JEV-1240 promise | $315.86 on Thu 15 Oct: allowed; 63% of $500 left each month (warning); 30 Nov: blocked, "within 21 days (by Mon 19 Oct)" |
| JEV-1240 extract | Hardship (job loss), promise $315.86 on 2026-10-15, callback; each with its sentence |
| JEV-1240 wrap-up | Codes RPC, HARDSHIP_STATED, PROGRAMME_AGREED, PTP; follow-up: one reminder Tue 29 Sep from 07:00 their time |
| HAC-4447 | "Contact blocked"; consumer proposal filed 2026-09-20; POL-COLL-001 §7.3 |
| Ask, province ranking | Yukon highest at 40.9% (small sample: 22 promises); Nova Scotia highest among provinces with 30+ promises |
