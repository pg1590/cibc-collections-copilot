# Finals live demo: script and fallback

About 6 minutes, then Q&A ([finals-judge-qa.md](finals-judge-qa.md)). Every customer and value below is pinned by `tests/test_demo_customers.py` and checked in a real browser by `scripts/e2e_finals.mjs`. Run both on the demo laptop the morning of the finals.

## Before going on stage

1. Start the backend with a clean review store, so the review queue shows only today's briefs:

```bash
COPILOT_STATE=data/finals-demo-reviews.sqlite3 COPILOT_GEMINI_ENABLED=0 .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

2. Start the frontend as a production build (no dev-mode overlay, faster pages):

```bash
cd frontend && npm run build && npm run start
```

3. Open <http://127.0.0.1:3000>, sign in as `supervisor` / `supervisor-demo`, and open each page once so the first load is warm.
4. Keep a second browser profile signed in as `agent` / `agent-demo` for step 6.
5. Fallback: the screenshots in `data/finals-shots/` (desktop and phone) and the recorded run. If the live app fails, switch to them without apologising and keep the same narration.

## Script

| Time | Do | Say |
|---|---|---|
| 0:00 | Overview, scroll to **Problems across all customers** | "Before every call an agent has to check eight things. Here is what happens when nobody checks them across 96,000 open cases." |
| 0:30 | Point at 18,758, 760 and 1,040; open **Definition and SQL** on 760 | "18,758 customers in hardship with no plan. 760 cases already contacted more than three times this week. 1,040 calls outside legal hours last month. Every number is one query: here it is." |
| 1:10 | **Work queue** (supervisor sees agent AG-7514) | "This is one agent's day, sorted by a fixed rule, not a model score. Each row says why it is there and when we are next allowed to call." |
| 1:40 | Point at row 3, Philippe Charron | "His promise is due today, but he was already contacted three times: no reminder is allowed, so the queue says check for payment instead." |
| 2:00 | **Agent brief** → `SAV-6847` → Prepare brief | "The brief is a to-do list in order." |
| 2:20 | Step 4 (contact window) | "Monday and Tuesday are blocked: three attempts in seven days, and reminders count. Wednesday is the National Day for Truth and Reconciliation. So: Thursday, 7 am to 9 pm her time." |
| 2:50 | Step 2 (vulnerable) and step 5 | "She is flagged vulnerable, a safeguard only. The payment step repeats: offer hardship options first, never pressure." |
| 3:10 | **Agent brief** → `JEV-1240` | "Hardship is recorded. Before any payment request, here are the programmes that pass the recorded rules, with the approver. A term extension needs income evidence; it says so." |
| 3:40 | **Agent brief** → `HAC-4447` | "Consumer proposal: the plan stops at step 1. Don't contact; route through the trustee." |
| 4:00 | **Ask Collections**: "Which province has the highest promise-kept rate in August 2026?" | "Judges' questions: the first line is the answer in plain English, then the table and the SQL." |
| 4:30 | "Which agent collected the most money?" | "If we can't answer correctly, it says so and offers questions it can answer, rather than a wrong number." |
| 4:50 | "Give me the phone numbers of customers with hardship" | "And it refuses what it must not do." |
| 5:10 | **Supervisor review**: open a brief, Edit with a reason | "Nothing goes to a customer. A supervisor approves, edits or rejects, with a reason, in an append-only audit." |
| 5:40 | Switch to the agent profile, open **Work queue** | "Agents only ever see their own cases; that is enforced by the server." |
| 6:00 | Close | "Every step cites the policy and the record. The model only flags possible hardship for a human. That is what makes it safe to use." |

## Expected values (snapshot 28 September 2026)

| Where | Value |
|---|---|
| Overview tiles | 18,758 customers; 760 cases; 1,040 contacts; 4,100 cases; 7,052 promises; 729 cases; 3 cases |
| Queue AG-7514 | 296 open cases: 18 promise due soon, 74 hardship with no plan, 189 standard, 15 on hold |
| SAV-6847 | Next action "Ask for the payment, timed to their payday (Thu 1 Oct, 07:00-21:00 their time)" |
| JEV-1240 | Likely eligible: HP-LOAN-RED3 (agent), HP-LOAN-EXT (hardship specialist, needs income evidence) |
| HAC-4447 | "Don't contact this customer"; consumer proposal; trustee routing |
| Ask, province ranking | Yukon highest at 40.9% (small sample: 22 promises); Nova Scotia highest among provinces with 30+ promises |
