# Review of the teammate's improvement plan

Reviewed 4 October 2026 against HEAD `c56b9fe`. Input: the workspace's `improvement-plan.md`, written against `efc21f4`. The user requested Codex and Claude assessments before discussing implementation. No application, dataset, model, benchmark or submission artifact was changed by this review.

Claude Code completed a separate read-only review using **claude-opus-5-5, high effort**. Response metadata confirms success and this model only; raw prompt/response remain local and ignored. Claude inspected code and reports without running checks. Codex independently inspected the implementation, official requirements and synthetic policies, then ran read-only aggregate data checks. No implementation is approved by this review.

## Combined assessment

The plan is useful and identifies important correctness gaps. Its proposed 30-hour work allocation and some deliverable statuses are outdated. Recommend a small correctness release before the 19:00 extra-question round, rather than implementing the whole plan before the 21:00 deadline.

| Suggestion | Assessment | Recommended scope |
|---|---|---|
| Recorded hardship and reasons in briefs | Highest priority; confirmed by code and aggregate checks | Query open `gold.cases` directly for recorded hardship and specific holds. Keep holds first, recorded hardship second, then possible financial cues. Cite case/note IDs and explain the rule that fired. No classifier change is needed. |
| Question grouping, dates and metric meaning | High priority; confirmed | Honor supported groupings and periods; explicitly clarify unsupported ones. Fix substring collisions and fixed roll-rate endpoints. Use certified definitions and preserve source-wide denominators. |
| Pilot cure result BQ-014 | High priority diagnostic; timing mismatch supported by data | Establish the intended treatment anchor, maturity window, exclusions and denominator before changing the query. Do not optimize for a desired answer or direction. |
| Direct policy answers and call summaries | Useful | Repair the missing HPT-2026 document citation first. Short source-backed policy answers and structured extractive summaries can follow if core checks pass with time to spare. |
| README, contract and diagram | Useful, mostly small | Make design changes explicit, distinguish business owner from technical steward, use testable quality rules, and clearly label the model and review point. Describe actual implementation only. |
| Windows encoding and reusable engine | Sound robustness ideas | Use explicit UTF-8 and BOM-tolerant question CSV input; document the tested Python 3.10 environment. Cache immutable policy retrieval at startup if verified, without sharing a mutable DuckDB connection. |
| Broad C360 expansion, programme eligibility and model changes | Worth considering after core fixes | Add only fields required by the chosen workflow. Programme checks must expose unknown inputs. New text cues need fresh evaluation and shared training/serving definitions. |
| LLM fallback | Optional, separate decision | Not required by build instructions. Retain the no-paid-runtime-call choice. If approved later, prefer a validated metric/grouping/period plan compiled into reviewed SQL over model-written arbitrary SQL. |

## Independently checked evidence

### Recorded hardship

`app/main.py:150` reads contact/insolvency/deceased holds but does not use case `hardship_flag` in the brief branch. The deployed path tests model score >= 0.5 or extracted note spans.

Read-only queries over open linked cases, stored features and customer restriction flags found:

- 33,895 customers with recorded hardship on an open case.
- 20,764 of those with no financial cue in the latest note.
- 18,322 with no cue and no case/profile hold that takes priority in the current brief logic.
- The saved model's zero-cue score is 0.2655, below the decision threshold.

Together with the code, this supports that these 18,322 customers can receive the generic branch despite a recorded hardship flag. No briefs were generated or changed to obtain these counts. They are customers, not source rows or independently confirmed hardship diagnoses.

### Question semantics

Read-only plan inspection reproduced these issues:

- "Promise-kept rate this month by queue" produces an aggregate result.
- "PTP rate by agent site" produces a channel breakdown.
- "How much did we collect in September?" has no metric plan.
- "Roll rate from March to May 2026 by product" binds June 30 as its end date.

Claude independently found substring collisions (`mar` in "summarise", for example) and the verb "may" being interpreted as a month. HPT-2026 is indexed as section `document`, while the preferred policy mapping requests section `§1`, dropping that citation.

### Pilot timing

For the first randomised-pilot assignment with hardship recorded at assignment, the current case-opening-based calculation finds **zero** 30-day cures among 2,226 non-certified-agent cases and 1,964 certified-agent cases. Yet these groups have 56 and 72 recorded cures overall. This is not evidence of a type-parsing failure.

A diagnostic anchored to assignment date, restricting assignments to dates with 30 observed days by the snapshot, finds 33 cures among 1,537 non-certified-agent cases and 47 among 1,348 certified-agent cases. These are exploratory counts, not approved replacement benchmark answers: the appropriate exclusions and definition still need reconciliation. Do not claim causality or choose the query because its direction looks better.

## Corrections to the teammate's proposed approach

1. **An LLM fallback would not repair existing wrong answers.** It only activates when the current planner finds no plan; wrong grouping and date branches already return plans. Semantic fixes come first. SQL parsing or EXPLAIN alone cannot validate business meaning, access scope or query cost.
2. **Do not substitute golden tables for every metric.** Golden views exclude unresolved identities; official portfolio metrics use source-wide denominators. Use C360 for linked customer assistance and retain the documented populations for aggregate metrics.
3. **Recorded hardship is not reviewed hardship.** Keep recorded source flags, AI-suggested possible hardship, human review status and programme eligibility distinct. Protected attributes must not become features or decision inputs.
4. **The existing contact count does not enforce the policy.** It combines non-system outbound channels across a customer over a fixed UTC period. POL-COLL-001 section 5.2 limits outbound call attempts per case in a rolling seven days, including payment-requesting reminders. A dedicated policy calculation is required.
5. **Explain the deployed branch, not just coefficients.** Briefs use a score-or-evidence rule, so classifier recall alone does not measure the full workflow. Coefficients are not individual causal explanations; cite source facts and the rule that actually triggered the recommendation.
6. **Do not tune against the saved heldout split.** Inspecting its errors and changing cues makes it development data. Use training-only validation for selection and fresh untouched evaluation for new performance claims.
7. **A structured field does not inherently require retraining.** If classifier inputs are unchanged, adding recorded hardship as a separate rule needs no new model. Rebuild only affected views/features if needed; avoid rerunning `train_model.py` merely to refresh metadata.
8. **Do not invent programme eligibility or customer DQ status.** Unsupported programme history, income evidence and reviewed hardship level must stay unknown. Dataset-wide issue counts do not automatically provide per-customer quality status.

## Already prepared and release checks

The counted quality report already has handling and identity outcomes. The nine-slide presentation and 4:40 walkthrough are prepared. README already explains several design deviations in prose, but an explicit design/build table would improve visibility. The architecture already mentions the classifier and supervisor review; clearer visual labels would improve it. Numeric development references are CSV tables, so do not unconditionally prepend prose that may break automatic parsing.

For any approved core changes: test recorded-hardship and hold priority, unsupported grouping/period clarification, refusal boundaries and evidence citations. Require all 12 numeric public references and existing tests to remain passing, regenerate benchmark answers through the engine, and refresh the deck/ZIP after the final run. Hidden-answer correctness remains unverified. The saved model report must remain unchanged unless a separately approved model change is evaluated.

Recommended discussion: approve recorded-hardship/reason fixes, narrow planner corrections, the pilot diagnostic/definition correction, and small documentation/CSV robustness fixes first. Defer LLM integration, broad schema expansion and recall tuning. Rehearse the final UI before recording, reserve 19:00 onward for extra questions, and verify the manual `cibchack26` invitation by 17:00.
