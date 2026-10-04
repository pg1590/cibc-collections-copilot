# Feature parity validation

Owner: Ved Maurya. Files: `scripts/check_feature_parity.py`, `tests/test_feature_parity.py`, this document.

## Purpose

The Feature Store keeps one versioned definition, `app.features.feature_sql`, for both the stored offline table (`gold.features`, built by `scripts/train_model.py`) and the live path (`POST /api/briefs` calls `feature_sql(True)` for one customer). If the stored rows ever drift from what the serving definition returns, an agent would see different features from the ones the model and reports were checked on. The checker detects that drift, then fails loudly.

The checker is read-only. It opens DuckDB with `read_only=True` and disables external file access. It does not change feature definitions, the feature version, the trained model or any stored row. JSON output cannot overwrite the database or version report, including through symlink or hardlink aliases; it is written atomically.

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
   - Values must have the same type. Floats use relative and absolute tolerances of 1e-9. Integers, strings and timestamps must be exactly equal.
   - It also reports schema drift (missing/extra columns and changed types), missing or duplicate rows for a sampled customer, and version drift (the stored report's version differs from code `VERSION`). Missing or malformed version metadata prevents the check from running.
   - Full-table key checks compare stored customer keys with the shared `feature_sql()` serving definition and count missing, extra, null and duplicate keys, even outside the sample. Feature values remain sampled.
4. **Report** the feature version, snapshot, seed, sample size, stored row count, compared columns, NULL counts in the sample and every mismatch. The mismatch report names the customer, column, stored value and recomputed value.

| Exit status | Meaning |
|---|---|
| 0 | Every sampled row matches |
| 1 | At least one mismatch |
| 2 | The check could not run (missing database/table, empty table, unreadable version metadata or unsafe/unwritable output) |

```bash
.venv/bin/python scripts/check_feature_parity.py                       # 100 customers, seed 1590
.venv/bin/python scripts/check_feature_parity.py --sample-size 1000 --seed 42 --output data/feature-parity.json
```

## Tests

`tests/test_feature_parity.py` builds a five-customer synthetic DuckDB fixture, then stores `gold.features` with the real `feature_sql()`. The fixture includes open and closed cases, kept, broken and open promises, `system` and `channel_v2` contacts, and English and French notes. The 37 tests check that:

- Identical rows pass, including customers with NULL `max_dpd` and `broken_promise_ratio`.
- A deliberately changed fixture value (`total_overdue + 0.01`) fails with exit status 1 and an exact mismatch record.
- NULL → 0, value → NULL, a flipped text cue and a changed contact count each fail on the right column.
- A source note edited after the store was built is detected as stale (`hardship_request`).
- Duplicate rows, an extra stored column and feature-version drift each fail.
- The sample is reproducible for a seed and changes with different seeds.
- The database bytes are unchanged after a check (read-only).
- A missing database or table exits with status 2.
- Null-aware comparison works directly on edge values.
- Key gaps outside the sample, type drift, malformed version metadata, empty stores, unsafe output aliases and write failures are detected.
- Nonfinite mismatch values remain distinct from NULL in valid JSON, and a failed atomic write preserves the previous report.

Integration mutation check: making the comparator always return "match" in a temporary source copy causes 11 of the 37 tests to fail. The production source was not changed by this check.

## Real-data result (recorded 4 October 2026)

Contributor-recorded runs below used the public main release `maple_collections_release.zip`, Hugging Face revision `40f13317`, SHA-256 `450703a5…a932db`, verified against the publisher checksum. Ved built his local database with `scripts/build_data.py`, then `scripts/train_model.py`, and reported reproducing the committed held-out metrics (precision 0.8929, recall 0.6579, confusion matrix [[85,3],[13,25]]). The integration review did not retrain or modify the model. The feature version is still `c360-financial-v1`.

| Run | Sample | Columns | Mismatches | Exit | Time |
|---|---|---|---|---|---|
| seed 1590 (default) | 100 of 1,014,631 | 15 | 0 | 0 | 2.3 s |
| seed 1590 | 1,000 of 1,014,631 | 15 | 0 | 0 | 33 s |
| seed 42 | 100 of 1,014,631 | 15 | 0 | 0 | — |
| Copy of the database with `total_overdue + 1` for customer `JUP-4506` | 100 | 15 | 1 (`total_overdue`, stored 1.0 vs recomputed 0.0) | 1 | — |

NULLs in the 1,000-customer sample: `max_dpd` 901, `broken_promise_ratio` 879, `note_id` and `note_ts` 808. Most customers have no open case, no resolved promise or no note before the snapshot. All of these compared as NULL = NULL. The failure demonstration ran on a temporary copy, which was then deleted. The real database was never modified.

Independent integration verification on the project's Python 3.10.12 environment reproduced zero mismatches across 15 columns for 1,000 customers with seed 1590, including the same NULL counts. A second 100-customer run with seed 42 also passed in 2.492 seconds. Full-table key checks found zero missing, extra, duplicate or null keys across 1,014,631 stored rows. Database size and modification time were unchanged around the second run. The full integrated test suite passed 325 tests; all 50 benchmark answers remained byte-for-byte unchanged and all 12 organizer numeric references matched.

## Limitations

- Feature values are sampled: 1,000 of about 1.01 million customers. A clean result does not prove every feature value matches. Key coverage is checked across the full table.
- Both sides read the same DuckDB snapshot. Parity shows that the stored rows match the serving definition. It does not show that the definitions are correct business rules; that is covered by the metric and model reviews.
- The recomputation runs the serving query once per customer, which is about 30 ms per customer on this machine. Large samples take longer.
- The version check compares code with the sidecar report; the stored table has no version column or build fingerprint. Snapshot metadata comes from application settings.
- Ved's original local environment used Python 3.14 with `requirements.txt`; integration verification used the project's existing Python 3.10.12 environment.
