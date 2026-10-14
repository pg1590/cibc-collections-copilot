# Extra-question implementation and review

The organizer's supplied `benchmark_questions_extra.csv` is preserved in `submission/`. All answers are generated through `app.runtime.answer`, the same question engine used by the API. No benchmark IDs select answers and no output cells are manually edited.

## Added support

- Source-wide overdue totals on open cases, recorded hardship-flag counts and insolvency-hold counts/balances. Open means no recorded outcome; these descriptive flags do not determine eligibility or authorize contact.
- Average recorded `days_to_cure` for cases curing during the requested period, with non-null duration counts. Opening-date and maximum-duration cohorts require clarification.
- Clicked outbound payment-link SMS send events divided by all outbound SMS send events carrying a payment-link ID. Periods use send timestamps; repeated sends count separately and click flags reflect the extract snapshot.
- Promise-kept/broken rates grouped by `ptp_channel`, the channel where the promise was taken. Due-date ranges preserve both requested calendar days, with an exclusive end internally.
- Current fraud, complaint escalation, income-evidence and permitted-calling-hour policy sections; exact timestamped latest-call statements remain supported.
- Refusals for bulk identifiers, religious attendance proxies and vulnerability-based deprioritization. Additional protected decision wording and French equivalents are covered.

The five added catalog metrics are reviewed application extensions grounded in source fields, not newly certified bank metric definitions. All 18 catalog metrics and 62 supported metric/grouping combinations pass actual-database SQL EXPLAIN checks.

## Actual Claude review

Claude Code was invoked as `claude-opus-5-5` with high effort and tools disabled. Successful response metadata confirms that model. Only relevant private source/test diffs were sent; keys and raw customer datasets were excluded. Raw review prompts/results remain local and ignored.

Claude identified dropped question filters, grouping/date ranges, provider refusals replaced by policy retrieval, ambiguous relative periods, broad SMS/cure intent matches and unsupported insolvency subtypes. Shared local/provider cohort checks, requested-period/grouping checks, refusal precedence and explicit clarification now cover these gaps. Sensitive hardship/insolvency summary rows remain local. Unsupported rolling periods require explicit dates; a trailing month window requires its ending day. Year-to-date and named calendar-day ranges are supported.

## Verified result

- 210 automated tests pass, including new source/denominator/date/refusal and provider-plan regression checks.
- 12 of 12 original numeric development references still match their tolerance.
- Final `submission/benchmark_answers.csv`: 50 unique question IDs, exact template header, nine refusals and zero unresolved results.
- Final format/coverage checks require the actual 15 extra inputs. The generated answers are not an organizer score, and hidden-reference accuracy remains unverified.

The original note classifier, C360 summary schema and customer contact/eligibility rules are unchanged. Voice evidence is a separate review-only extension documented in `docs/voice-verification.md`.
