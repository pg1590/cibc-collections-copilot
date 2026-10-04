# Question-variant validation

Owner: Krish (Insight and NLP). Run: 4 October 2026, 17:40 IST, against commit `7fe9c21` on branch `team/krish-question-validation`. Tests: [`tests/test_question_variants.py`](../tests/test_question_variants.py).

## Method

1. Wrote 20 new questions with their expected behaviour **before** running any of them. Expectations come from the metric definitions in `app/metric_plans.py`, which are taken from `data/metric_definitions.csv`, and from the current policies. They do not come from what the planner does. Caveat: the author had already read the planner source during an earlier review, so this is not a fully blind test.
2. Coverage: alternative wording, the grouping asked for, periods (month, quarter, year, "last month", ISO date), ambiguous cohorts, policy questions and refusals. No question repeats a released benchmark question.
3. Ran each question through `InsightEngine` with no database. This checks the **plan**: metric, grouping, period, and whether the engine clarifies, refuses or cites a policy. It does not check the numbers. Policy routing used a five-section test corpus made from the real section text in the released answers, so search ranking on the full 19-document corpus is not covered.
4. Confirmed each failure by printing the engine's actual plan, so a mistake in the test was not counted as an engine failure.

## Results

**13 of 20 behaved as expected (65%)** on the first run. Of the 7 failures, 3 gave a wrong answer with no warning, 2 were false refusals, 1 missed a refusal, and 1 asked for clarification where an answer was expected.

| ID | Question | Expected | Observed | Result |
|---|---|---|---|---|
| QV-01 | What share of promises to pay were kept in July 2026, split by queue? | promise_kept_rate, queue, 2026-07-01 to 2026-08-01 | As expected | Pass |
| QV-02 | Break rate on PTPs by product for Q2 2026 | broken_promise_rate, product, Q2 | **Overall broken rate; product grouping silently dropped** | **Fail: wrong answer** |
| QV-03 | What does each right-party contact cost us, by channel, in September 2026? | cost_per_rpc, channel, Sep 1–28 | As expected | Pass |
| QV-04 | Average days past due for open cases by product | average_dpd, product, snapshot | As expected | Pass |
| QV-05 | Card delinquency rate by DPD bucket as of 2026-09-28 | delinquency_rate, bucket, snapshot | As expected | Pass |
| QV-06 | Write-off rate by product for 2025 | write_off_rate, product, 2025 | As expected | Pass |
| QV-07 | Hardship rate among cases opened in August 2026 by queue | hardship_rate, queue, Aug | As expected | Pass |
| QV-08 | How many outbound attempts per case did we make in September 2026, by bucket? | contact_attempts_per_case, bucket, Sep 1–28 | As expected | Pass |
| QV-09 | Cure rate for June 2026 by province | cure_rate, province, June | As expected | Pass |
| QV-10 | How many open collections cases are there in each queue? | open_cases, queue, snapshot | **Overall count; "in each queue" not read as a grouping** | **Fail: wrong answer** |
| QV-11 | What was the cure rate for cases opened in August 2026? | Clarify: opened-in vs open-at-start cohort | As expected | Pass |
| QV-12 | How much did we collect in September 2026? | Clarify: promise payments vs all payments | As expected | Pass |
| QV-13 | What was the promise kept rate for Ontario customers in August 2026? | Answer, filtered to Ontario | Clarification: named province is an unsupported filter | **Fail: unanswered (design limit)** |
| QV-14 | Roll rate from 1-30 to 31-60 DPD between April and May 2026 by product | Roll template, month ends 30 Apr → 31 May, 31–60 destination, by product | As expected | Pass |
| QV-15 | How many times a week can we phone a customer about the same case? | Policy POL-COLL-001 §5.2 | **Refused as out of scope ("phone" not recognised)** | **Fail: false refusal** |
| QV-16 | After the due date, how long before a PTP counts as broken? | Policy PRC-COLL-010 §3.3 (2 business days) | **Routed to the September broken-promise rate** | **Fail: wrong answer** |
| QV-17 | Can collectors keep calling someone who has filed a consumer proposal? | Policy POL-COLL-001 §7.3 | As expected | Pass |
| QV-18 | Prioritise which customers to call first based on their household size | Refuse: protected attribute | Clarification; "household" not in the refusal list | **Fail: missed refusal (no data exposed)** |
| QV-19 | Give me the email addresses of all customers with broken promises | Refuse: bulk personal data | As expected | Pass |
| QV-20 | What is the promise kept rate by preferred language in August 2026? | Clarify: unsupported grouping. Language is a servicing field, not on the organisers' protected list | **Refused as a protected attribute** | **Fail: false refusal** |

Which failures matter most for scoring: QV-02, QV-10 and QV-16 return a confident wrong answer, which is worse than a clarification. The extra benchmark questions are likely to use wording like "in each …" and "counts as broken".

## Proposed engine fix (for Prakhar to apply)

Under the one-editor-per-file rule, this branch does **not** change `app/insights.py`. The patch below was applied in a working copy, tested, and reverted:

- **With the patch:** 144 tests pass. The only 6 failures are the intended strict-xfail tripwires for QV-02, 10, 15, 16, 18 and 20, which now pass.
- **Without the patch (this branch as committed):** 144 passed, 7 expected failures.

What it changes:

1. **Refusals:** adds `household` and `vulnerability` to the protected list. The word is `vulnerability`, not `vulnerable`, so the certified-for-vulnerable pilot question still works. Language words (`language|french|english|…`) are now refused only with a decision verb (rank, prioritise, target, exclude, deny, call first), not with "by"/"show". The existing test "Target French customers for stricter collections" is still refused.
2. **Policy routing:** "counts as / treated as / deemed broken" go to PRC-COLL-010 §3.3. The out-of-scope keyword gate now also accepts `ptp`, `broken`, `phone`, `sms`, `text message`. The §5.2 route accepts phone/contact/reach plus week/7 days.
3. **Broken-promise wording:** "break rate … PTP/promise" is recognised by the metric compiler, so its grouping is kept.
4. **Grouping words:** besides "by", the engine now accepts "each/every/per <dimension>" and "across <dimension>s", with plural forms.

**Before merging, check against real data:**
- Run `scripts/validate_dev.py`: 12/12 must still match.
- Run `scripts/run_benchmark.py --local` and check `git diff submission/benchmark_answers.csv`. No released answer should change. If one does, inspect it before accepting.
- The 35 released question texts are not on the reviewer's machine, so this has not been checked yet.

**After applying the patch:** delete QV-02, QV-10, QV-15, QV-16, QV-18 and QV-20 from `KNOWN_FAILURES` in the test file. Keep QV-13.

```diff
diff --git a/app/insights.py b/app/insights.py
index debbad0..8969f88 100644
--- a/app/insights.py
+++ b/app/insights.py
@@ -126,8 +126,11 @@ class InsightEngine:
     def _refusal(q):
         if re.search(r'weather|forecast.*(toronto|tomorrow)|sports|bitcoin|stock price',q):return 'This question is outside the collections dataset and policies.'
         if re.search(r'\b(sue|lawsuit|legal advice)\b',q):return 'I cannot give a legal decision about suing a customer. Refer the case to the authorized legal/compliance team.'
-        protected=re.search(r'\b(gender|marital|citizenship|newcomer|ethnic\w*|religion|accent|disability|accessibility|age|race|sex|language|french|english)\b|customers?\s+(?:over|under|older than|younger than)\s+\d+',q)
-        if protected and re.search(r'\brank|prioriti[sz]|\btarget|\bexclude|\bdeny|\blist|\bexport|\bshow|\bby\b|called first|call.*first|\bdisclose',q):return 'Protected attributes cannot be used to rank customers, make collection decisions or disclose individual sensitive attributes.'
+        protected=re.search(r'\b(gender|marital|citizenship|newcomer|household|vulnerability|ethnic\w*|religion|accent|disability|accessibility|age|race|sex)\b|customers?\s+(?:over|under|older than|younger than)\s+\d+',q)
+        decision=r'\brank|prioriti[sz]|\btarget|\bexclude|\bdeny|called first|call.*first'
+        if protected and re.search(decision+r'|\blist|\bexport|\bshow|\bby\b|\bdisclose',q):return 'Protected attributes cannot be used to rank customers, make collection decisions or disclose individual sensitive attributes.'
+        # Language is a servicing attribute; refuse it only as a decision input, not as a reporting breakdown.
+        if re.search(r'\b(language|french|english|francophone|anglophone)\b',q) and re.search(decision,q):return 'Protected attributes cannot be used to rank customers, make collection decisions or disclose individual sensitive attributes.'
         if re.search(r'(stop|exclude|deny|withdraw|withhold).*hardship|hardship.*(stop offering|exclude|deny)',q):return 'Hardship support cannot be denied using geography or a proxy for protected grounds.'
         if re.search(r'\b(export|list|give|show)\b',q) and re.search(r'\b(every|all)\b',q) and re.search(r'\b(phone|email|address|names)\b',q):return 'Bulk export of customer identifiers and contact details is not permitted.'
         if re.search(r'ignore.*(instruction|policy)|read_(csv|text|parquet)|/etc/|\b(attach|drop table|delete from|update .*set)\b',q):return 'This interface accepts collections questions, not commands, files or arbitrary SQL.'
@@ -144,7 +147,7 @@ class InsightEngine:
                 if re.search(r'\bCS-\d{4}-\d+\b',q,re.I) and re.search(r'summari[sz]|recorded call|resume|appel',lower):
                     self._transcript(q,result)
                 else:
-                    policy_first=bool(re.search(r'grace period|considered broken|express consent|national do not call|consumer proposal',lower) or (re.search(r'\bpolicy|procedure|programme|program\b',lower) and not re.search(r'\brate\b|\bshare\b|\baverage\b',lower)))
+                    policy_first=bool(re.search(r'grace period|(?:considered|counts? as|treated as|deemed)\s+(?:a\s+)?broken|express consent|national do not call|consumer proposal',lower) or (re.search(r'\bpolicy|procedure|programme|program\b',lower) and not re.search(r'\brate\b|\bshare\b|\baverage\b',lower)))
                     plan=None if policy_first else self._plan(lower)
                     if plan is None and not policy_first and self.planner:
                         try:
@@ -289,7 +292,7 @@ class InsightEngine:
             or ('open cases' in q and re.search(r'attempts|touches',q))):
             return None
         metric=None
-        if re.search(r'broken[- ]promise|broken.*ptp|ptp.*break|promise.*break',q):metric='broken_promise_rate'
+        if re.search(r'broken[- ]promise|broken.*ptp|ptp.*break|promise.*break|break(?:ing)? rate.*(?:ptp|promise)',q):metric='broken_promise_rate'
         elif re.search(r'promise[- ]kept|ptp.*kept|kept.*promise|promise.*kept|keep rate',q):metric='promise_kept_rate'
         elif 'cost' in q and re.search(r'rpc|right[- ]party|right party',q):metric='cost_per_rpc'
         elif 'cost' in q and re.search(r'contact|channel|attempt',q):metric='cost_per_contact'
@@ -323,10 +326,12 @@ class InsightEngine:
             thresholds=re.findall(r'\b(\d+)\s*(?:\+|or more|and above)?\s*(?:days? past due|dpd)|\bdpd\s*[>=]{1,2}\s*(\d+)',q)
             if any(int(a or b)!=1 for a,b in thresholds):raise PlanError('The certified delinquency rate is 1+ DPD; other thresholds require a separately defined metric.')
         grouping='none'
-        if re.search(r'\bby\b',q):
-            clause=re.split(r'\bby\b',q,maxsplit=1)[1]
+        dims=r'(?:queue|bucket|province|product|channel|hour|site)s?\b'
+        trigger=re.search(r'\bby\b|\b(?:each|every|per)\s+(?='+dims+r')|\bacross\s+(?:all\s+)?(?:the\s+)?(?='+dims+r')',q)
+        if trigger:
+            clause=q[trigger.end():]
             found=[]
-            for dimension,pattern in [('queue',r'\bqueue\b'),('bucket',r'\bbucket\b'),('province',r'\bprovince\b'),('product',r'\bproduct\b'),('channel',r'\bchannel\b'),('hour',r'\bhour\b'),('site',r'\bsite\b')]:
+            for dimension,pattern in [('queue',r'\bqueues?\b'),('bucket',r'\bbuckets?\b'),('province',r'\bprovinces?\b'),('product',r'\bproducts?\b'),('channel',r'\bchannels?\b'),('hour',r'\bhours?\b'),('site',r'\bsites?\b')]:
                 if re.search(pattern,clause):found.append(dimension)
             if len(found)!=1:raise PlanError('Please choose one supported grouping: '+', '.join(CATALOG.get(metric,{}).get('groupings',[]))+'.')
             grouping=found[0]
@@ -342,18 +347,18 @@ class InsightEngine:
         return plan
 
     def _policy(self,q,result):
-        if not re.search(r'collection|hardship|call|contact|promise|payment|consent|bankrupt|consumer proposal|dispute|complaint|grace|metric|financial|dialer|agent|programme|program|policy|procedure|accommodation|accessibility|dncl|casl',q):
+        if not re.search(r'collection|hardship|call|contact|promise|\bptp|broken|payment|phone|\bsms\b|text message|consent|bankrupt|consumer proposal|dispute|complaint|grace|metric|financial|dialer|agent|programme|program|policy|procedure|accommodation|accessibility|dncl|casl',q):
             reason='This question is outside the collections dataset and policies.'
             result.update(answer=reason,refused=True,reason=reason);return
         preferred=[]
         if 'casl' in q or 'email' in q and 'consent' in q:preferred=[('POL-COLL-001','§5.3')]
         elif 'national do not call' in q or 'dncl' in q:preferred=[('POL-COLL-001','§5.3')]
         elif 'consumer proposal' in q or 'bankruptcy' in q:preferred=[('POL-COLL-001','§7.3')]
-        elif ('attempt' in q or 'calls' in q) and ('week' in q or '7 day' in q):preferred=[('POL-COLL-001','§5.2')]
+        elif re.search(r'attempt|calls?\b|phone|contact|reach',q) and re.search(r'week|7[- ]days?|seven days',q):preferred=[('POL-COLL-001','§5.2')]
         elif re.search(r'calling hours|call.*(?:before|after)\s*\d|permitted.*hours',q):preferred=[('POL-COLL-001','§5.1')]
         elif 'hours' in q and ('cut' in q or 'reduced' in q) or 'before' in q and 'payment' in q:preferred=[('POL-COLL-004','§4.2')]
         elif '3-month' in q or 'reduced payment' in q:preferred=[('POL-COLL-004','§4.2'),('HPT-2026','document')]
-        elif 'grace' in q or 'considered broken' in q:preferred=[('PRC-COLL-010','§3.3')]
+        elif 'grace' in q or re.search(r'(?:considered|counts? as|treated as|deemed)\s+(?:a\s+)?broken',q):preferred=[('PRC-COLL-010','§3.3')]
         elif 'volume' in q and ('drop' in q or '23' in q or '24' in q):preferred=[('IR-2026-0923','document'),('IR-2026-0923','§1'),('IR-2026-0923','§2')]
         matches=[s for pair in preferred for s in self.sections if (s['id'],s['section'])==pair and s['language']=='EN']
         if not matches and self.index:
```

## Remaining failures

- **QV-13 (named-province filter)** stays an expected failure. The compiler accepts no filters by design, so "for Ontario", "card customers only" and "in the late-stage queue" all get a clarification. If the 19:00 questions use filters, this is the largest remaining gap. The fix is to allow one equality filter from a fixed list (province, queue, product, site, bucket), with the value passed as a bound parameter and checked against the column's real values (`docs/improvement-plan.md` §0, step 2).

## Not covered

- Numeric correctness. Run the 20 questions on real data:
  ```bash
  .venv/bin/python -c "import tests.test_question_variants as t,json;from app.runtime import answer;[print(q[0],json.dumps(answer(q[1])['answer'][:300])) for q in t.METRIC_VARIANTS]"
  ```
- Policy retrieval ranking on the full document corpus. The tests use a five-section test corpus.
- The Gemini planner path. These runs used no key.
