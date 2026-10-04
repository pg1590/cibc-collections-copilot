"""Read-only feature parity check: recompute a reproducible customer sample with the
serving definition (app.features.feature_sql) and compare it with stored gold.features.

Exit status: 0 = all sampled rows match, 1 = mismatches found, 2 = check could not run.
Feature definitions and stored rows are never changed; the trained model is not read.
"""
import argparse
import json
import math
import sys
import tempfile
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
    if type(stored) is not type(recomputed):
        return False
    if isinstance(stored, float):
        a, b = stored, recomputed
        if math.isnan(a) or math.isnan(b):
            return math.isnan(a) and math.isnan(b)
        return math.isclose(a, b, rel_tol=FLOAT_TOLERANCE, abs_tol=FLOAT_TOLERANCE)
    return stored == recomputed


def jsonable(value):
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return str(value) if not math.isfinite(value) else value
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
        report = json.loads(Path(report_path).read_text())
    except (OSError, ValueError) as error:
        raise CheckError('Stored feature-version metadata is missing or unreadable.') from error
    if not isinstance(report, dict) or not isinstance(report.get('version'), str) or not report['version']:
        raise CheckError('Stored feature-version metadata must contain a nonempty version string.')
    return report['version']


def check(db=DB, sample_size=DEFAULT_SAMPLE, seed=DEFAULT_SEED, feature_report=None):
    db = Path(db)
    if not db.exists():
        raise CheckError(f'Database not found: {db}. Run scripts/build_data.py and scripts/train_model.py first.')
    if sample_size < 1:
        raise CheckError('Sample size must be at least 1.')
    feature_report = Path(feature_report) if feature_report else db.parent / 'features-report.json'
    recorded_version = stored_version(feature_report)
    conn = duckdb.connect(str(db), read_only=True)
    try:
        conn.execute('SET enable_external_access=false')
        exists = conn.execute("SELECT count(*) FROM information_schema.tables "
                              "WHERE table_schema='gold' AND table_name='features'").fetchone()[0]
        if not exists:
            raise CheckError('Stored feature table gold.features is missing. Run scripts/train_model.py first.')
        stored_rows = conn.execute('SELECT count(*) FROM gold.features').fetchone()[0]
        ids = sample_ids(conn, sample_size, seed)
        if not ids:
            raise CheckError('gold.features has no customer rows to sample.')
        stored_columns, _ = fetch(conn, 'SELECT * FROM gold.features LIMIT 0', [])
        stored_types = {d[0]: str(d[1]) for d in conn.description}
        serving_sql = feature_sql(True)
        serving_columns, _ = fetch(conn, serving_sql, [None])
        serving_types = {d[0]: str(d[1]) for d in conn.description}
        mismatches = []
        null_keys, duplicate_rows = conn.execute(
            'SELECT count(*) FILTER(WHERE customer_id IS NULL), '
            'count(customer_id)-count(DISTINCT customer_id) FROM gold.features').fetchone()
        serving_keys = f'SELECT DISTINCT customer_id FROM ({feature_sql()}) serving'
        missing_keys = conn.execute(f'SELECT count(*) FROM ({serving_keys}) g WHERE NOT EXISTS '
            '(SELECT 1 FROM gold.features f WHERE f.customer_id=g.customer_id)').fetchone()[0]
        extra_keys = conn.execute(f'SELECT count(DISTINCT f.customer_id) FROM gold.features f WHERE f.customer_id IS NOT NULL AND NOT EXISTS '
            f'(SELECT 1 FROM ({serving_keys}) g WHERE g.customer_id=f.customer_id)').fetchone()[0]
        key_coverage = dict(null_customer_ids=null_keys, duplicate_customer_rows=duplicate_rows,
                            missing_stored_customers=missing_keys, extra_stored_customers=extra_keys)
        for rule, count in key_coverage.items():
            if count:
                mismatches.append({'kind': 'key_coverage', 'rule': rule, 'count': count})
        schema = {'missing_in_stored': [c for c in serving_columns if c not in stored_columns],
                  'extra_in_stored': [c for c in stored_columns if c not in serving_columns],
                  'type_drift': [c for c in serving_columns if c in stored_types and stored_types[c] != serving_types[c]]}
        for column in schema['missing_in_stored']:
            mismatches.append({'kind': 'schema', 'column': column, 'detail': 'serving column missing from stored table'})
        for column in schema['extra_in_stored']:
            mismatches.append({'kind': 'schema', 'column': column, 'detail': 'stored column not produced by serving definition'})
        for column in schema['type_drift']:
            mismatches.append({'kind': 'schema_type', 'column': column,
                               'stored': stored_types[column], 'recomputed': serving_types[column]})
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
    if recorded_version != VERSION:
        mismatches.append({'kind': 'version', 'detail': f'stored report {recorded_version} != code {VERSION}'})
    return {
        'checked_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'database': str(db), 'feature_version': VERSION, 'stored_report_version': recorded_version,
        'snapshot': SNAPSHOT, 'seed': seed, 'requested_sample_size': sample_size,
        'sample_size': len(ids), 'stored_rows': stored_rows,
        'columns_compared': compared, 'schema': schema, 'key_coverage': key_coverage,
        'sample_null_counts': {c: n for c, n in nulls.items() if n},
        'float_tolerance': FLOAT_TOLERANCE,
        'mismatch_count': len(mismatches), 'mismatched_customers': len({m[KEY] for m in mismatches if KEY in m}),
        'mismatches': mismatches, 'status': 'fail' if mismatches else 'pass',
    }


def summary(result, limit=20):
    lines = [f"Feature parity: {result['status'].upper()}",
             f"  version {result['feature_version']} (stored report: {result['stored_report_version'] or 'not found'}), snapshot {result['snapshot']}",
             f"  sample {result['sample_size']} of {result['stored_rows']} stored rows, seed {result['seed']}, {len(result['columns_compared'])} columns compared",
             f"  full-table key coverage: {result['key_coverage']}",
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
        feature_report = args.feature_report or args.db.parent / 'features-report.json'
        if args.output:
            for source in [args.db, feature_report]:
                if args.output.resolve() == source.resolve() or (args.output.exists() and source.exists() and args.output.samefile(source)):
                    raise CheckError('Output must not overwrite the database or stored feature report.')
        result = check(args.db, args.sample_size, args.seed, args.feature_report)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=args.output.parent,
                                                 prefix='.feature-parity-', suffix='.tmp', delete=False) as stream:
                    temporary = Path(stream.name)
                    stream.write(json.dumps(result, indent=2, default=jsonable, allow_nan=False))
                temporary.replace(args.output)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
    except (CheckError, duckdb.Error, OSError, ValueError) as error:
        print(f'Feature parity check could not run: {error}', file=sys.stderr)
        return 2
    print(summary(result))
    return 1 if result['mismatches'] else 0


if __name__ == '__main__':
    sys.exit(main())
