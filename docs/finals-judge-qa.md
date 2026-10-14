# Finals: likely judge questions and our answers

Prepared 14 October 2026 for the live demo and Q&A. Every number below was measured on the local release (snapshot 28 September 2026) and can be reproduced with the command or SQL named next to it. If a judge asks for something not listed here, say what we measured and what we did not.

## The product in one minute

Collections agents have to combine policy, consent, promises, hardship rules and contact limits before every call. Collections Copilot turns that into an ordered to-do list per customer, where each step says why and which policy section it follows. A work queue sorts each agent's cases by a fixed, explainable rule. An Overview page shows policy problems across all 96,000 open cases, each backed by one SQL query. A supervisor reviews every brief; the app never contacts customers.

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
`config/statutory_holidays.csv`: 30 September is named in POL-COLL-001 §5.1, and the other dates follow the national holidays flagged in `contact_history.stat_holiday_flag` for 2025-2026. Limitation: provincial-only holidays are not modelled.

**How do you decide which hardship programmes a customer is eligible for?**
We don't decide; we pre-check and the named approver confirms. Each programme version effective on the snapshot date (`hardship_programs.csv`, v2026.1) is checked against the case product, days past due, months on book, uses in the last 12 months, insolvency, broken plans in the last 90 days, and the hardship level the programme needs (recorded vs AI-possible). Programmes needing income evidence list it as a missing input (POL-COLL-004 §4.3). HP-DMP requires a credit counsellor; settlement is shown only from 121 days past due ("late stage", HPT-2026). The FAQ says the reduced-payment programme lasts 6 months, but the policy and programme table say 3; we follow the policy.

**How do you estimate payday?**
Semi-monthly pay is the 15th and the last day of the month, and monthly pay is month-end, moved back to Friday at weekends. In the August 2026 salary credits, 41,000 of about 41,400 semi-monthly customers and every monthly customer follow this pattern. Weekly and biweekly pay roll forward from the last salary credit. That gives an estimate for 48,887 of 93,338 linked open cases (52%). Otherwise the plan tells the agent to ask.

**What about cases with an agency or in legal action?**
3,262 open cases are `placed_agency` or `legal`. No policy in the release covers them, so the plan shows a caution step citing the source status instead of inventing a rule.

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
Yes. `scripts/e2e_finals.mjs` drives Chromium through the Overview checks, the queue, three demo briefs, reviews and the agent role at desktop and phone widths: 27 of 27 checks passed, with no console errors.

## Limits we state up front

- Synthetic, templated data; no production or business-uplift claim.
- Holidays: national list only. Payday: estimated for 52% of open cases.
- Programme results are suggestions; the approver decides.
- Identity matching precision is not measured; 64,145 links are held for review.
- No customer contact is ever sent by the app.
