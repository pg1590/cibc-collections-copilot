"""Check the built C360 product against config/c360-contract.yaml without changing it.

Run from the repository root after scripts/build_data.py:
    .venv/bin/python scripts/check_c360_contract.py

The database is opened read-only. Checked rules: product table exists, every
contract column is present, no undeclared columns, compatible types, non-null,
unique and minimum-value rules. Every other contract item is listed in the
report as not checked here, with where it is handled instead.
Exit code 0 = all checks passed, 1 = a check failed, 2 = the check could not run.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import duckdb
import yaml
from app.settings import DB, ROOT

CONTRACT = ROOT / 'config/c360-contract.yaml'
REPORT = ROOT / 'docs/c360-contract-validation.md'
RESULTS = ROOT / 'data/c360-contract-validation.json'

INTEGER_TYPES = {'TINYINT', 'SMALLINT', 'INTEGER', 'BIGINT', 'HUGEINT',
                 'UTINYINT', 'USMALLINT', 'UINTEGER', 'UBIGINT', 'UHUGEINT'}
COMPATIBLE = {
    'string': lambda t: t == 'VARCHAR',
    'integer': lambda t: t in INTEGER_TYPES,
    'number': lambda t: t in INTEGER_TYPES or t in {'FLOAT', 'DOUBLE'} or t.startswith('DECIMAL'),
}
CHECKED_COLUMN_KEYS = {'type', 'nullable', 'unique', 'minimum'}
DESCRIPTIVE_COLUMN_KEYS = {'description', 'source', 'unit'}
CHECKED_SECTIONS = {'contract_id', 'version', 'product', 'primary_key', 'columns'}
# Where each unchecked contract section is handled instead. Unknown sections
# fall back to a plain "not checked" entry so new contract items stay visible.
UNCHECKED_SECTIONS = {
    'owner': 'Governance metadata; not a data rule.',
    'owner_status': 'Governance metadata; company approval is outside the build.',
    'technical_steward': 'Governance metadata; not a data rule.',
    'snapshot_date': 'Not checked here. The build records its snapshot and build time in data/quality.json.',
    'refresh': 'Not checked here. Freshness and refresh schedule are not measured.',
    'source_authority': 'Lineage documentation; not compared with the release files here.',
    'identity': 'Matching rules are implemented in scripts/build_data.py. Matched/review/unmatched counts are in docs/data-quality-report.md. Matching precision is not measured.',
    'quality': 'Source-table checks are measured in docs/data-quality-report.md. Feature-store keys are validated with Pandera in app/features.py.',
    'allowed_uses': 'Enforced by API roles and refusal rules (tests/test_api_security.py, tests/test_insights.py); not a data check.',
    'disallowed_uses': 'Enforced by API roles and refusal rules (tests/test_api_security.py, tests/test_insights.py); not a data check.',
    'third_party_processing': 'Provider controls are tested in tests/test_runtime.py and tests/test_gemini.py; not a data check.',
    'access': 'Role scope is tested in tests/test_api_security.py; not a data check.',
    'protected_fields': 'Partly: the undeclared-column check fails if any column outside the contract, such as a protected field, appears in the product. Classifier input exclusion is tested in tests/test_financial_features.py.',
    'lineage': 'Lineage documentation; table derivations are not traced here.',
}


def ident(value):
    return '"' + str(value).replace('"', '""') + '"'


def file_state(path):
    stat = Path(path).stat()
    return stat.st_size, stat.st_mtime_ns


def unchecked_items(contract):
    items = [{'item': key, 'handling': UNCHECKED_SECTIONS.get(key, 'Not checked by this script.')}
             for key in contract if key not in CHECKED_SECTIONS]
    for name, spec in (contract.get('columns') or {}).items():
        for key in spec:
            if key in DESCRIPTIVE_COLUMN_KEYS:
                items.append({'item': f'columns.{name}.{key}', 'handling': 'Descriptive; not verified against data.'})
            elif key not in CHECKED_COLUMN_KEYS:
                items.append({'item': f'columns.{name}.{key}', 'handling': 'Not checked by this script.'})
    return items


def check(db_path=DB, contract_path=CONTRACT):
    contract = yaml.safe_load(Path(contract_path).read_text(encoding='utf-8'))
    columns = contract.get('columns') or {}
    primary_key = contract.get('primary_key')
    schema, table = contract['product'].split('.', 1)
    product = f'{ident(schema)}.{ident(table)}'
    checks = []

    def record(rule, column, expected, measured, passed):
        checks.append({'rule': rule, 'column': column, 'expected': expected, 'measured': measured,
                       'result': 'skipped' if passed is None else 'pass' if passed else 'fail'})

    before = file_state(db_path)
    connection = duckdb.connect(str(db_path), read_only=True)
    try:
        connection.execute('SET enable_external_access=false')
        actual = dict(connection.execute(
            'SELECT column_name, data_type FROM information_schema.columns '
            'WHERE table_schema=? AND table_name=? ORDER BY ordinal_position', [schema, table]).fetchall())
        rows = None
        record('product_exists', None, contract['product'], 'present' if actual else 'missing', bool(actual))
        if actual:
            rows = connection.execute(f'SELECT count(*) FROM {product}').fetchone()[0]
            for name in actual:
                if name not in columns:
                    record('undeclared_column', name, 'only contract columns', f'present ({actual[name]})', False)
            for name, spec in columns.items():
                present = name in actual
                record('column_present', name, 'present', 'present' if present else 'missing', present)
                if not present:
                    continue
                kind = spec.get('type')
                compatible = COMPATIBLE.get(kind, lambda t: False)(actual[name])
                expected = kind if kind in COMPATIBLE else f'{kind} (unsupported contract type)'
                record('type', name, expected, actual[name], compatible)
                column = ident(name)
                if spec.get('nullable') is False or name == primary_key:
                    nulls = connection.execute(f'SELECT count(*) FROM {product} WHERE {column} IS NULL').fetchone()[0]
                    record('not_null', name, '0 null rows', f'{nulls:,} null rows', nulls == 0)
                if spec.get('unique') or name == primary_key:
                    duplicates = connection.execute(f'SELECT count({column}) - count(DISTINCT {column}) FROM {product}').fetchone()[0]
                    record('unique', name, '0 duplicate values', f'{duplicates:,} duplicate values', duplicates == 0)
                if 'minimum' in spec:
                    minimum = spec['minimum']
                    if compatible and kind in ('integer', 'number'):
                        below = connection.execute(f'SELECT count(*) FROM {product} WHERE {column} < ?', [minimum]).fetchone()[0]
                        record('minimum', name, f'0 rows below {minimum}', f'{below:,} rows below {minimum}', below == 0)
                    else:
                        record('minimum', name, f'0 rows below {minimum}', 'not measured: incompatible type', None)
    finally:
        connection.close()
    unchanged = file_state(db_path) == before
    return {
        'contract_id': contract.get('contract_id'), 'contract_version': contract.get('version'),
        'snapshot_date': contract.get('snapshot_date'), 'product': contract['product'],
        'checked_at': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'rows': rows,
        'checks': checks, 'unchecked': unchecked_items(contract), 'database_unchanged': unchanged,
        'passed': sum(c['result'] == 'pass' for c in checks),
        'failed': sum(c['result'] == 'fail' for c in checks),
        'skipped': sum(c['result'] == 'skipped' for c in checks),
    }


def display_path(path):
    path = Path(path).resolve()
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else path.name


def write_report(result, output, db_path, contract_path):
    cell = lambda value: '' if value is None else str(value).replace('|', '\\|')
    status = 'All checks passed.' if not result['failed'] and not result['skipped'] else \
        f"{result['failed']} check(s) failed and {result['skipped']} could not be measured."
    lines = [
        '# C360 contract validation', '',
        'Generated by `scripts/check_c360_contract.py`. Do not edit by hand; rerun the script after rebuilding the data.', '',
        f"Contract: {result['contract_id']} v{result['contract_version']} (`{display_path(contract_path)}`). "
        f"Product: `{result['product']}` in `{display_path(db_path)}`. Snapshot: {result['snapshot_date']}. "
        f"Checked at: {result['checked_at']}.", '',
        f"Rows measured: {result['rows']:,}." if result['rows'] is not None else 'Rows measured: none; the product table is missing.', '',
        f"**Result: {result['passed']} passed, {result['failed']} failed, {result['skipped']} not measured.** {status}", '',
        'The database was opened read-only. Its file size and modification time were '
        + ('identical before and after the check.' if result['database_unchanged'] else '**different** after the check; investigate before relying on this report.'), '',
        '## Checked rules', '',
        '| Rule | Column | Expected | Measured | Result |', '|---|---|---|---|---|',
    ]
    lines += [f"| {c['rule']} | {cell(c['column'])} | {cell(c['expected'])} | {cell(c['measured'])} | {c['result']} |"
              for c in result['checks']]
    lines += ['', '## Contract items this script does not check', '',
              'These items are not verified by this report. The second column says where each is handled, if anywhere.', '',
              '| Contract item | Handling |', '|---|---|']
    lines += [f"| {cell(u['item'])} | {cell(u['handling'])} |" for u in result['unchecked']]
    lines += ['', '## Reproduce', '', '```bash', '.venv/bin/python scripts/check_c360_contract.py', '```', '',
              'Exit code 0 means every checked rule passed, 1 means a rule failed, and 2 means the check could not run. '
              'Measured results are also written to the ignored `data/c360-contract-validation.json`.']
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--db', type=Path, default=DB)
    parser.add_argument('--contract', type=Path, default=CONTRACT)
    parser.add_argument('--report', type=Path, default=REPORT)
    parser.add_argument('--json', type=Path, default=RESULTS)
    args = parser.parse_args(argv)
    if not args.db.is_file():
        print(f'Database not found: {args.db}. Run scripts/build_data.py first.', file=sys.stderr)
        return 2
    try:
        result = check(args.db, args.contract)
    except (OSError, KeyError, ValueError, yaml.YAMLError, duckdb.Error) as exc:
        print(f'Contract check could not run: {exc}', file=sys.stderr)
        return 2
    write_report(result, args.report, args.db, args.contract)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({k: result[k] for k in ['product', 'rows', 'passed', 'failed', 'skipped', 'database_unchanged']}, indent=2))
    for c in result['checks']:
        if c['result'] != 'pass':
            print(f"{c['result'].upper()}: {c['rule']} {c['column'] or ''} expected {c['expected']}, measured {c['measured']}")
    return 0 if not result['failed'] and not result['skipped'] and result['database_unchanged'] else 1


if __name__ == '__main__':
    sys.exit(main())
