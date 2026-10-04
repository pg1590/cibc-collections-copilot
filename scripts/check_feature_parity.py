"""Read-only feature parity check: recompute a reproducible customer sample with the
serving definition (app.features.feature_sql) and compare it with stored gold.features.

Exit status: 0 = all sampled rows match, 1 = mismatches found, 2 = check could not run.
Feature definitions and the trained model are only read, never changed.
"""
import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import duckdb
from app.features import VERSION, feature_sql
from app.settings import DB, SNAPSHOT

DEFAULT_SAMPLE = 100
DEFAULT_SEED = 1590
FLOAT_TOLERANCE = 1e-9
KEY = 'customer_id'


class CheckError(Exception):
    """The comparison cannot run (missing database, table or sample)."""


def values_match(stored, recomputed):
    """Null-aware equality: NULL equals only NULL, NaN equals only NaN, floats use a tight tolerance."""
    if stored is None or recomputed is None:
        return stored is None and recomputed is None
    if isinstance(stored, float) or isinstance(recomputed, float):
        try:
            a, b = float(stored), float(recomputed)
        except (TypeError, ValueError):
            return False
        if math.isnan(a) or math.isnan(b):
            return math.isnan(a) and math.isnan(b)
        return math.isclose(a, b, rel_tol=FLOAT_TOLERANCE, abs_tol=FLOAT_TOLERANCE)
    return stored == recomputed


def jsonable(value):
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return None if math.isnan(value) else value
    return str(value)


def sample_ids(conn, size, seed):
    """Seeded md5 ordering: the same seed and stored keys always give the same sample."""
    rows = conn.execute(f'SELECT DISTINCT {KEY} FROM gold.features WHERE {KEY} IS NOT NULL '
                        f'ORDER BY md5(? || {KEY}), {KEY} LIMIT ?', [str(seed), size]).fetchall()
    return [r[0] for r in rows]


def fetch(conn, sql, params):
    cursor = conn.execute(sql, params)
    columns = [d[0] for d in cursor.description]
    return columns, [dict(zip(columns, row)) for row in cursor.fetchall()]


def stored_version(report_path):
    try:
        return json.loads(Path(report_path).read_text()).get('version')
    except (OSError, ValueError):
        return None


def check(db=DB, sample_size=DEFAULT_SAMPLE, seed=DEFAULT_SEED, feature_report=None):
    db = Path(db)
    if not db.exists():
        raise CheckError(f'Database not found: {db}. Run scripts/build_data.py and scripts/train_model.py first.')
    if sample_size < 1:
        raise CheckError('Sample size must be at least 1.')
    feature_report = Path(feature_report) if feature_report else db.parent / 'features-report.json'
    conn = duckdb.connect(str(db), read_only=True)
    try:
        exists = conn.execute("SELECT count(*) FROM information_schema.tables "
                              "WHERE table_schema='gold' AND table_name='features'").fetchone()[0]
        if not exists:
            raise CheckError('Stored feature table gold.features is missing. Run scripts/train_model.py first.')
        stored_rows = conn.execute('SELECT count(*) FROM gold.features').fetchone()[0]
        ids = sample_ids(conn, sample_size, seed)
        if not ids:
            raise CheckError('gold.features has no customer rows to sample.')
        stored_columns, _ = fetch(conn, 'SELECT * FROM gold.features LIMIT 0', [])
        serving_sql = feature_sql(True)
        serving_columns, _ = fetch(conn, serving_sql, [None])
        mismatches = []
        schema = {'missing_in_stored': [c for c in serving_columns if c not in stored_columns],
                  'extra_in_stored': [c for c in stored_columns if c not in serving_columns]}
        for column in schema['missing_in_stored']:
            mismatches.append({'kind': 'schema', 'column': column, 'detail': 'serving column missing from stored table'})
        for column in schema['extra_in_stored']:
            mismatches.append({'kind': 'schema', 'column': column, 'detail': 'stored column not produced by serving definition'})
        compared = [c for c in serving_columns if c in stored_columns and c != KEY]
        nulls = {c: 0 for c in compared}
        for cid in ids:
            _, stored = fetch(conn, f'SELECT * FROM gold.features WHERE {KEY}=?', [cid])
            _, served = fetch(conn, serving_sql, [cid])
            if len(stored) != 1 or len(served) != 1:
                mismatches.append({'kind': 'row_count', KEY: cid, 'stored_rows': len(stored), 'recomputed_rows': len(served)})
                continue
            for column in compared:
                a, b = stored[0][column], served[0][column]
                nulls[column] += a is None
                if not values_match(a, b):
                    mismatches.append({'kind': 'value', KEY: cid, 'column': column,
                                       'stored': jsonable(a), 'recomputed': jsonable(b)})
    finally:
        conn.close()
    recorded_version = stored_version(feature_report)
    if recorded_version is not None and recorded_version != VERSION:
        mismatches.append({'kind': 'version', 'detail': f'stored report {recorded_version} != code {VERSION}'})
    return {
        'checked_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'database': str(db), 'feature_version': VERSION, 'stored_report_version': recorded_version,
        'snapshot': SNAPSHOT, 'seed': seed, 'requested_sample_size': sample_size,
        'sample_size': len(ids), 'stored_rows': stored_rows,
        'columns_compared': compared, 'schema': schema,
        'sample_null_counts': {c: n for c, n in nulls.items() if n},
        'float_tolerance': FLOAT_TOLERANCE,
        'mismatch_count': len(mismatches), 'mismatched_customers': len({m[KEY] for m in mismatches if KEY in m}),
        'mismatches': mismatches, 'status': 'fail' if mismatches else 'pass',
    }


def summary(result, limit=20):
    lines = [f"Feature parity: {result['status'].upper()}",
             f"  version {result['feature_version']} (stored report: {result['stored_report_version'] or 'not found'}), snapshot {result['snapshot']}",
             f"  sample {result['sample_size']} of {result['stored_rows']} stored rows, seed {result['seed']}, {len(result['columns_compared'])} columns compared",
             f"  NULL values in sample: {result['sample_null_counts'] or 'none'} (NULL matches only NULL)",
             f"  mismatches: {result['mismatch_count']} across {result['mismatched_customers']} customers"]
    lines += ['  - ' + json.dumps(m, default=str) for m in result['mismatches'][:limit]]
    if result['mismatch_count'] > limit:
        lines.append(f"  ... {result['mismatch_count'] - limit} more in the JSON report")
    return '\n'.join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--db', type=Path, default=DB)
    p.add_argument('--sample-size', type=int, default=DEFAULT_SAMPLE)
    p.add_argument('--seed', type=int, default=DEFAULT_SEED)
    p.add_argument('--feature-report', type=Path, help='Stored features-report.json (default: next to the database).')
    p.add_argument('--output', type=Path, help='Write the full JSON result here, e.g. data/feature-parity.json.')
    args = p.parse_args(argv)
    try:
        result = check(args.db, args.sample_size, args.seed, args.feature_report)
    except (CheckError, duckdb.Error) as error:
        print(f'Feature parity check could not run: {error}', file=sys.stderr)
        return 2
    print(summary(result))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, default=str))
    return 1 if result['mismatches'] else 0


if __name__ == '__main__':
    sys.exit(main())
