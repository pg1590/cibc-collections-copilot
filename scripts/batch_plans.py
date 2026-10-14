"""Nightly batch: build the action plan for every open case, in parallel, and store a
compact result for portfolio views. Reads the main database read-only; writes a separate
file so serving is never locked.

  .venv/bin/python scripts/batch_plans.py [--workers 8] [--limit N] [--output data/plans.duckdb]
"""
import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import duckdb

from app import action_plan
from app.settings import AS_OF, DB, ROOT, SNAPSHOT


def _work(customer_ids):
    out = []
    with duckdb.connect(str(DB), read_only=True) as c:
        c.execute('SET threads=1')
        contexts = action_plan.load_many(c, customer_ids)  # a fixed number of set-based queries per chunk
    for cid, ctx in contexts.items():
        try:
            status = 'recorded' if ctx['case'].get('hardship_flag') else 'not_established'
            plan = action_plan.build(ctx, status)
            first = next((s for s in plan['steps'] if s['status'] in ('stop', 'action', 'wait') and s['key'] != 'contact_window'), plan['steps'][0])
            window = plan['contact_window'] or {}
            out.append((plan['case_id'], cid, first['key'], first['status'], plan['next_action'], window.get('date'),
                        len([p for p in plan['programmes'] if p['status'] == 'likely_eligible']), json.dumps(plan['steps'], default=str)))
        except Exception as exc:  # one bad record must not stop the batch
            out.append((None, cid, 'error', 'error', f'{type(exc).__name__}: {exc}'[:300], None, 0, '[]'))
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workers', type=int, default=max(1, (os.cpu_count() or 2) - 1))
    parser.add_argument('--limit', type=int, default=None)
    parser.add_argument('--chunk', type=int, default=2000)
    parser.add_argument('--output', type=Path, default=ROOT / 'data/plans.duckdb')
    args = parser.parse_args()
    with duckdb.connect(str(DB), read_only=True) as c:
        ids = [r[0] for r in c.execute('SELECT DISTINCT customer_id FROM gold.cases WHERE outcome IS NULL ORDER BY 1' + (f' LIMIT {int(args.limit)}' if args.limit else '')).fetchall()]
    chunks = [ids[i:i + args.chunk] for i in range(0, len(ids), args.chunk)]
    started = time.perf_counter()
    rows = []
    with ProcessPoolExecutor(args.workers) as pool:
        for part in pool.map(_work, chunks):
            rows += part
    seconds = time.perf_counter() - started
    tmp = args.output.with_suffix('.tmp.duckdb')
    tmp.unlink(missing_ok=True)
    with duckdb.connect(str(tmp)) as out:
        out.execute('''CREATE TABLE plans(case_id VARCHAR, customer_id VARCHAR, next_key VARCHAR, next_status VARCHAR, next_action VARCHAR,
                       next_contact_date DATE, eligible_programmes INTEGER, steps JSON)''')
        out.executemany('INSERT INTO plans VALUES (?,?,?,?,?,?,?,?)', rows)
        summary = out.execute('SELECT next_key, count(*) FROM plans GROUP BY 1 ORDER BY 2 DESC').fetchall()
        errors = out.execute("SELECT count(*) FROM plans WHERE next_key='error'").fetchone()[0]
        meta = {'snapshot_date': SNAPSHOT, 'as_of_utc': AS_OF.isoformat(), 'customers': len(ids), 'plans': len(rows) - errors, 'errors': errors,
                'seconds': round(seconds, 1), 'plans_per_second': round(len(rows) / seconds, 1), 'workers': args.workers,
                'next_step_counts': dict(summary)}
        out.execute('CREATE TABLE meta AS SELECT ? AS json', [json.dumps(meta)])
    tmp.replace(args.output)
    (ROOT / 'data/plans-report.json').write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=2))


if __name__ == '__main__':
    main()
