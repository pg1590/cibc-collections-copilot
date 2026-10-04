# Feature parity validation

Owner: Ved Maurya. Files: `scripts/check_feature_parity.py`, `tests/test_feature_parity.py`, this document.

## Purpose

The Feature Store keeps one versioned definition, `app.features.feature_sql`, for both the stored offline table (`gold.features`, built by `scripts/train_model.py`) and the live path (`POST /api/briefs` calls `feature_sql(True)` for one customer). If the stored rows ever drift from what the serving definition returns, an agent would see different features from the ones the model and reports were checked on. The checker detects that drift, then fails loudly.

The checker is read-only. It opens DuckDB with `read_only=True`. It does not change feature definitions, the feature version, the trained model or any stored row.

## Model inputs versus customer context

The hardship classifier uses **six financial text cues** only. Each is a binary flag taken from the latest agent note:
`income_loss`, `income_reduction`, `income_delay`, `payment_difficulty`, `hardship_request`, `expense_pressure`.

The structured features `open_cases`, `total_overdue`, `max_dpd`, `resolved_promises`, `broken_promises`, `broken_promise_ratio` and `contacts_7d` are **not** classifier inputs. They are versioned in the same Feature Store definition to give additional customer context. The brief's displayed overdue and days-past-due facts come from `gold.customer_summary`. The parity check covers both feature groups plus the `note_id` and `note_ts` lineage, because all of them come from the same serving query. Protected or vulnerability fields are not part of either group.

## What the checker does

1. **Reproducible sample.** It orders distinct `customer_id` values by `md5(seed || customer_id)`, takes the first N, and breaks ties by ID. The same seed and the same stored keys always give the same sample. Defaults are N = 100 and seed = 1590.
2. **Recompute.** For each sampled customer, it runs the serving definition `feature_sql(True)`, the same query the live brief endpoint uses.
3. **Compare** each stored row with the recomputed row, column by column:
   - NULL matches only NULL. For example, `max_dpd` is NULL when a customer has no open case, and `broken_promise_ratio` is NULL when a customer has no resolved promise. A NULL turning into 0, or a value turning into NULL, is a mismatch.
   - NaN matches only NaN.
   - Floats use a tolerance of 1e-9. Integers, strings and timestamps must be exactly equal.
   - It also reports schema drift (missing or extra columns), missing or duplicate rows for a sampled customer, and version drift (`data/features-report.json` version differs from the code `VERSION`).
4. **Report** the feature version, snapshot, seed, sample size, stored row count, compared columns, NULL counts in the sample and every mismatch. The mismatch report names the customer, column, stored value and recomputed value.

| Exit status | Meaning |
|---|---|
| 0 | Every sampled row matches |
| 1 | At least one mismatch |
| 2 | The check could not run (no database, no `gold.features`, empty table) |

```bash
.venv/bin/python scripts/check_feature_parity.py                       # 100 customers, seed 1590
.venv/bin/python scripts/check_feature_parity.py --sample-size 1000 --seed 42 --output data/feature-parity.json
```

## Tests

`tests/test_feature_parity.py` builds a five-customer synthetic DuckDB fixture, then stores `gold.features` with the real `feature_sql()`. The fixture includes open and closed cases, kept, broken and open promises, `system` and `channel_v2` contacts, and English and French notes. The 13 tests check that:

- Identical rows pass, including customers with NULL `max_dpd` and `broken_promise_ratio`.
- A deliberately changed fixture value (`total_overdue + 0.01`) fails with exit status 1 and an exact mismatch record.
- NULL → 0, value → NULL, a flipped text cue and a changed contact count each fail on the right column.
- A source note edited after the store was built is detected as stale (`hardship_request`).
- Duplicate rows, an extra stored column and feature-version drift each fail.
- The sample is reproducible for a seed and changes with different seeds.
- The database bytes are unchanged after a check (read-only).
- A missing database or table exits with status 2.
- Null-aware comparison works directly on edge values.

Mutation check: making the comparator always return "match" causes 7 of the 13 tests to fail, so the tests depend on the comparison logic.

## Real-data result (recorded 4 October 2026)

Data: the public main release `maple_collections_release.zip`, Hugging Face revision `40f13317`, SHA-256 `450703a5…a932db`, verified against the publisher checksum. The database was built locally with `scripts/build_data.py`, then `scripts/train_model.py`. The local retrain reproduced the committed held-out metrics exactly (precision 0.8929, recall 0.6579, confusion matrix [[85,3],[13,25]]). The feature version is still `c360-financial-v1`.

| Run | Sample | Columns | Mismatches | Exit | Time |
|---|---|---|---|---|---|
| seed 1590 (default) | 100 of 1,014,631 | 15 | 0 | 0 | 2.3 s |
| seed 1590 | 1,000 of 1,014,631 | 15 | 0 | 0 | 33 s |
| seed 42 | 100 of 1,014,631 | 15 | 0 | 0 | — |
| Copy of the database with `total_overdue + 1` for customer `JUP-4506` | 100 | 15 | 1 (`total_overdue`, stored 1.0 vs recomputed 0.0) | 1 | — |

NULLs in the 1,000-customer sample: `max_dpd` 901, `broken_promise_ratio` 879, `note_id` and `note_ts` 808. Most customers have no open case, no resolved promise or no note before the snapshot. All of these compared as NULL = NULL. The failure demonstration ran on a temporary copy, which was then deleted. The real database was never modified.

## Limitations

- This is a sample, not a full-table comparison: 1,000 of about 1.01 million customers. A clean result means no drift was found in that sample. It does not prove every row matches.
- Both sides read the same DuckDB snapshot. Parity shows that the stored rows match the serving definition. It does not show that the definitions are correct business rules; that is covered by the metric and model reviews.
- The recomputation runs the serving query once per customer, which is about 30 ms per customer on this machine. Large samples take longer.
- The local environment used Python 3.14 with `requirements.txt`, because the pinned `numpy` in `requirements-lock.txt` has no Python 3.14 wheel.
