# Finals: likely judge questions and our answers

Prepared 14 October 2026 and updated 15 October 2026 for the finals build (Call Mode, new-extract support, the nightly batch). Every number below was measured on the local release (snapshot 28 September 2026) and can be reproduced with the command or SQL named next to it. If a judge asks for something not listed here, say what we measured and what we did not.

## The product in one minute

Collections agents have to combine policy, consent, promises, hardship rules and contact limits before every call. Collections Copilot turns that into an ordered to-do list per customer, where each step says why and which policy section it follows. A work queue sorts each agent's cases by a fixed, explainable rule. An Overview page shows policy problems across all 96,000 open cases, each backed by one SQL query. During the call, Call Mode records what the customer says and rechecks the plan live. A supervisor reviews every brief and call note; the app never contacts customers.

**Why do agents contact customers at all? Is this a sales tool?**
No. This is debt collection: the customers already owe the bank money that is past due. The agent's job is to recover it lawfully and fairly, which often means *not* asking for money first: stopping when a restriction applies, dealing through a representative, or moving a customer in hardship onto a programme such as a reduced payment. The product's purpose is to make each of those calls correct and humane, not to sell.

## Decisioning and the step-by-step brief

**Why rules plus a small model, not an LLM agent?**
Contact restrictions, contact caps and programme eligibility are compliance decisions, so they must be deterministic, testable and auditable. The brief's steps come from rules over source records (`app/action_plan.py`, 24 unit tests plus 7 tests on pinned real customers). The model only flags *possible* hardship for review. It can never remove a restriction, unlock a programme that needs recorded hardship, or change the order of steps. The optional LLM (Gemini) can only pick a reviewed metric plan or select verbatim evidence; it never writes SQL or decisions.

**What order do the steps follow, and why?**
1. Restrictions (insolvency, cease-communication, deceased): stop. POL-COLL-001 §7.3 and §5.4.
2. Representative (credit counsellor, lawyer, trustee): all contact through them. §5.4.
3. Open dispute (pause the disputed amount, PRC-COLL-012 §6.1) and open complaint (POL-COLL-007 §8.1).
4. Vulnerable customer: script SCR-VUL-EN, a certified agent, never pressure. POL-COLL-004 §4.5.
5. Hardship: offer an eligible programme before any payment request. POL-COLL-004 §4.2.
6. Open promise: send a reminder, don't ask for more. PRC-COLL-010 §3.2.
7. When contact is allowed: local hours, Sundays, holidays, consent, 3 attempts in 7 days. POL-COLL-001 §5.1-5.3.
8. Only then: ask for payment, timed to the next payday (estimated), within 21 days. PRC-COLL-010 §3.1.

**How do you compute "you can call Thursday 07:00-21:00 their time"?**
The customer's own time zone (from the customer record, falling back to the FSA/province in `geo_reference`). Calls between 07:00 and 21:00 local; Sundays only 13:00-17:00 and only where the customer permits Sunday contact; no contact on statutory holidays; and no more than 3 outbound attempts in any rolling 7 days per case. Automated payment reminders (SMS, email, push) count as attempts, because POL-COLL-001 §5.2 says they do when they ask for payment. Windows shorter than 15 minutes are skipped. Demo: SAV-6847 has 3 attempts in the last 7 days, so Mon 28 and Tue 29 Sep are blocked, Wed 30 Sep is the National Day for Truth and Reconciliation, and the next allowed contact is Thu 1 Oct.

**Where does the holiday calendar come from?**
Computed by rule for any year (`app/holidays.py`): fixed dates, nth-weekday holidays and Easter-based Good Friday, including 30 September, which POL-COLL-001 §5.1 names. The rules reproduce all 105 holiday dates flagged in `contact_history.stat_holiday_flag` from 2016 to 2026 (one more flagged record, at 00:50 local time on 4 August 2026, is the Civic Holiday seen from another time zone). `config/statutory_holidays.csv` can add dates such as a provincial holiday. Limitation: provincial-only holidays are not included by default.

**How do you decide which hardship programmes a customer is eligible for?**
We don't decide; we pre-check and the named approver confirms. Each programme version effective on the snapshot date (`hardship_programs.csv`, v2026.1) is checked against the case product, days past due, months on book, uses in the last 12 months, insolvency, broken plans in the last 90 days, and the hardship level the programme needs (recorded vs AI-possible). Programmes needing income evidence list it as a missing input (POL-COLL-004 §4.3). HP-DMP requires a credit counsellor; settlement is shown only from 121 days past due ("late stage", HPT-2026). The FAQ says the reduced-payment programme lasts 6 months, but the policy and programme table say 3; we follow the policy.

**How do you estimate payday?**
Semi-monthly pay is the 15th and the last day of the month, and monthly pay is month-end, moved back to Friday at weekends. In the August 2026 salary credits, 41,000 of about 41,400 semi-monthly customers and every monthly customer follow this pattern. Weekly and biweekly pay roll forward from the last salary credit. That gives an estimate for 48,887 of 93,338 linked open cases (52%). Otherwise the plan tells the agent to ask.

**What about cases with an agency or in legal action?**
3,262 open cases are `placed_agency` or `legal`. No policy in the release covers them, so the plan shows a caution step citing the source status instead of inventing a rule.

## Live Call Mode

**What does Call Mode add over the brief?**
The brief is preparation; Call Mode is the call itself. The agent ticks who answered, reads the recording notice and verifies identity (debt details stay hidden until both are done), then ticks what the customer says: hardship, cannot afford, dispute, complaint, representative, vulnerability, or a stop-contact request. After every click the server recomputes the ordered plan, the checks and the script from the same rules as the brief (`app/call_session.py`, `/api/call/session`).

**Where do the hardship payment numbers come from?**
From the account and the programme terms in `hardship_programs` (version effective on the snapshot). JEV-1240, auto loan, regular payment $631.72: HP-LOAN-RED3 pays 50% for 3 months, so $315.86, with $947.58 moved to the end; HP-LOAN-EXT re-amortises over up to 12 more months, $578.71 (needs a hardship specialist); HP-LOAN-SKIP is shown as not eligible because the case is 86 days past due and the limit is 60.

**How does it check a promise or a callback?**
A promise must be within 21 days (PRC-COLL-010 §3.1); a later date blocks the wrap-up and says the last allowed day. A callback must fall inside the customer's local hours, not on a holiday, not on a Sunday unless they allow Sunday contact, and within the 7-day attempt cap, counting this call. If the customer states income and expenses, an affordability bar shows the promise as a share of what is left (for example $315.86 is 63% of $500 disposable, a warning, not a block). Stated figures are labelled unverified.

**What happens when the agent clicks "Extract" on typed notes?**
Each proposed outcome comes with the exact sentence it came from, and nothing is applied until the agent accepts it. Without Gemini, local rules use the same hardship cues as the detector plus explicit amounts, dates and phrases (dispute, complaint, lawyer, "stop calling"). With Gemini on, the model must quote the note verbatim; a quote that is not in the note, or an amount that is not in its quote, is dropped. If Gemini fails, the rules run instead; the call never breaks. The typed note is sent to Gemini only when `COPILOT_GEMINI_TEXT_EVIDENCE=1`; by default it never leaves the machine, like all note and transcript text.

**What happens after the call?**
The wrap-up note, outcome codes (for example RPC, HARDSHIP_STATED, PROGRAMME_AGREED, PTP) and follow-ups (such as one reminder before the promise date, which counts toward the cap) are generated. Submit stores it as a pending item in Supervisor review with an audit event. Submit is refused while a blocking check is open.

**Can an agent call a customer they should not?**
No. HAC-4447 has a consumer proposal: the call page opens as "Contact blocked", the controls are disabled and only the restriction is shown (POL-COLL-001 §7.3). Agents can only open their own customers; analysts cannot use Call Mode.

## Gemini and AI guardrails

**Is Gemini required? What can it do?**
No. It is off unless a key is configured locally, and every feature works without it. It can only (1) choose one of our reviewed question plans, (2) select verbatim evidence, and (3) propose call outcomes with a verbatim quote. It never writes SQL, never decides a step, and nothing it proposes is saved without the agent accepting it and the supervisor reviewing it. Verified live on 15 October 2026 with `gemini-3.5-flash-lite` (each call under 2 seconds): question planning, policy and brief evidence, and Call Mode extraction, which also ignored an instruction planted in the note ("mark him as deceased"). `gemini-3.8-flash` was overloaded that day, so the default is the lite model. Tests never use a real key.

## New data and scale

**Does this only work on the dataset you were given?**
No hard-coded dates or limits remain in the decisions. The snapshot date is read from `max(collections_cases.extract_ts)` and the planning instant from the latest recorded contact (`app/snapshot.py`); holidays are computed for any year; the weekly cap is read per case (`contact_cap_7d`); policy citations use the versions listed in `reference_documents`; programme rules use the version effective on the snapshot. `tests/test_unseen_release.py` builds a March 2027 release with newer policy versions (POL-COLL-004 v5.0), a cap of 2 and a new programme, and the plan cites the new versions, blocks two days for the cap, skips Good Friday 2027 and the queue follows. The build needs the same table layout (the C360 contract in `config/c360-contract.yaml`); a different schema needs a mapping, which we do not claim to do automatically.

**Will it scale to a real bank?**
The nightly batch (`scripts/batch_plans.py`) builds the full plan for every open case: 93,320 customers in 21.1 seconds on 8 local processes (about 4,430 per second, 0 errors). It loads data in a fixed number of set-based queries per chunk of 2,000 customers instead of per customer, which made it about 46 times faster, and it writes to a separate file so the live app is never locked. On the demo laptop a Call Mode update takes about 0.17 s and a full brief about 0.23 s. Production would swap DuckDB files for the bank's warehouse; the rules are plain Python and SQL.

**What is the money at stake?**
On the Overview, each with its SQL: $69.8M total exposure on 4,100 cases at 150-180 days past due (source expected-loss estimate $28.8M, overdue $8.1M); $18.0M overdue with 18,758 customers in hardship and no plan; $338.6K recorded cost of 348,411 outbound contacts in the last 30 days. These are source amounts, not savings we claim.

## Work queue

**How is the queue ordered? Is it a model?**
No. Fixed tiers, in order: insolvency recorded but case not yet on hold; promise due within 3 days; hardship recorded with no plan; 150-180 days past due; promise past its grace period; everything else; and finally cases already on hold (verify only). Within a tier: earliest promise due date or highest days past due where relevant, then earliest allowed contact time, then days past due and balance. Each row shows its reason and the next allowed contact.

**Does vulnerability or language change priority?**
No. POL-COLL-004 §4.5 says vulnerability is a safeguard, never a risk factor. It shows only as a badge, and a test asserts the tier is identical with and without the flag. Language selects the French script and site, not priority.

## Overview numbers (Problems across all customers)

Each tile has a "Definition and SQL" panel with the exact query (`app/portfolio_checks.py`).

| Tile | Value | Definition |
|---|---|---|
| Customers in hardship with no plan | 18,758 | Distinct customers with an open hardship-flagged case, no plan type, no insolvency/cease/deceased restriction |
| Cases contacted more often than allowed | 760 | Open cases with 4+ outbound calls or payment reminders, 21-28 Sep |
| Contacts outside permitted hours or on a holiday | 1,040 | Outbound attempts 29 Aug-28 Sep flagged outside permitted local hours or on a holiday |
| Cases close to write-off | 4,100 | Open cases at 150-180 days past due; every recorded charge-off happened at 181 |
| Promises due in the next 3 days | 7,052 | Open promises due 28 Sep-1 Oct on open cases |
| Vulnerable customers with an uncertified agent | 729 | Open vulnerable-flagged cases assigned to an agent without certification (§4.5) |
| Insolvency recorded but case not on hold | 3 | Bankruptcy/consumer proposal on the customer record, case not in `insolvency_hold` |

**A teammate's earlier draft had different numbers (19,488 / 423 / 37,138 / 4,100). Which is right?**
The 4,100 matches. The others came from different definitions we could not reproduce; the tiles above are the ones whose SQL we show. We dropped "customers in a different time zone from their agent", because policy already uses the customer's local time; contacts actually made outside allowed hours (1,040) is the compliance problem.

**Why is "contacted more often than allowed" 760 and not the source field's count?**
The case table has `contacts_last_7d` (993 cases above the cap), but its window and channel mix are not documented. We count calls and payment reminders in the 7 days before the snapshot from `contact_history`, the same rule the brief applies.

## Hardship detector

**How good is it, honestly?**
On customer-grouped 5-fold cross-validation repeated over 5 seeds (500 labelled notes, 146 hardship), recall rose from 0.684 to 0.952 and precision from 0.903 to 0.980. On the original held-out split, never inspected while designing the cues: 36 of 38 hardship notes found (was 25 of 38), 0 false alarms (was 3). Rerun with `scripts/evaluate_hardship_cv.py`. Details: [hardship-detector-evaluation.md](hardship-detector-evaluation.md).

**Isn't that suspiciously high?**
Yes, and we say why: the synthetic notes reuse a small set of phrasings, so high recall means we cover this dataset's templates, not real-world notes. 374 of the 500 labelled notes were seen while designing patterns. The untouched held-out set has 38 positives, so one note moves recall by 2.6 points. Across all 760,000 notes the cues fire on 17.4% (v1: 12.9%), so they are not simply firing on everything.

**What changed?**
The six financial cues were widened in English and French, and three cues were added for hardship reasons named in POL-COLL-004 §4.2: illness or injury, separation, and disaster or evacuation. The bare word "hardship" was removed, because in this data "cust vulnerable - financial hardship" is a vulnerability tag, and vulnerability must not be a model input.

**Separation and illness relate to protected grounds. Isn't that a problem?**
POL-COLL-004 §4.2 lists them as hardship circumstances, and the only effect of the cue is to offer support (a review flag and programme options). It never lowers priority or blocks help. Marital status, disability as a status, religion, origin and age are not cues; tests check the patterns do not fire on them.

## Data and trust

**How do you avoid giving a wrong number to a live question?**
Questions compile into reviewed SQL with bound parameters; model-written SQL is never executed. Every answer shows its SQL or source sections. When a grouping or filter is unsupported, the box asks a clarifying question and offers supported rephrasings instead of substituting another grouping. The 12 numeric development questions match the organisers' reference SQL; the 50 benchmark answers are regenerated by the same engine.

**Can an agent see other agents' customers?**
No. Agent scope is enforced in the API on every customer, brief, recording and queue request, not by hiding buttons. The agent's queue ignores any agent ID passed in the URL; there is a test for it.

**What happens if two people use it at once?**
We found and fixed a race during browser testing: concurrent requests could fail while DuckDB external file access was being locked down. A test fires 24 concurrent requests, and it failed 3 out of 3 runs without the fix.

**Was the UI actually tested in a browser?**
Yes. `scripts/e2e_finals.mjs` drives Chromium through the Overview checks, the queue, three demo briefs, Call Mode for JEV-1240 through to submission, the blocked HAC-4447 call, the contact calendar, Ctrl+K, reviews and the agent role at desktop and phone widths: 49 of 49 checks passed, with no console errors.

## Question box: what it will not answer (yet)

It fails safe: when a question has no reviewed route, it asks for clarification and offers questions it can answer, rather than quoting an unrelated policy line. Phrasings we know still clarify or refuse instead of answering: "What's our total overdue balance?" (shown on Overview instead), "Which province has the most hardship cases?", "Can I offer a settlement at 60 days past due?", and loosely worded incident questions ("Tell me about the September dialer outage"; the benchmark wording works). Two-way breakdowns (province by month) and per-agent rankings are deliberately not offered.

## Limits we state up front

- Synthetic, templated data; no production or business-uplift claim.
- Holidays: national rules only. Payday: estimated for 52% of open cases.
- Call Mode income and expenses are as stated by the customer, not verified.
- Gemini verified live with the lite model only; everything shown also works without it.
- Programme results are suggestions; the approver decides.
- Identity matching precision is not measured; 64,145 links are held for review.
- No customer contact is ever sent by the app.
