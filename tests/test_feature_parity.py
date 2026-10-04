"""The parity checker must pass on identical rows and fail on any deliberately changed value."""
import importlib.util
import json
import math
from pathlib import Path

import duckdb
import pytest

from app.features import VERSION, feature_sql

spec = importlib.util.spec_from_file_location('check_feature_parity', Path(__file__).resolve().parents[1] / 'scripts/check_feature_parity.py')
parity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parity)

CUSTOMERS = ['C1', 'C2', 'C3', 'C4', 'C5']


@pytest.fixture
def db(tmp_path):
    """Tiny synthetic source tables, then gold.features stored with the same serving definition."""
    path = tmp_path / 'fixture.duckdb'
    with duckdb.connect(str(path)) as c:
        c.execute('CREATE SCHEMA gold; CREATE SCHEMA curated')
        c.execute('CREATE TABLE gold.customers(customer_id VARCHAR)')
        c.execute('CREATE TABLE gold.crm_identity(crm_customer_id VARCHAR, customer_id VARCHAR)')
        c.execute('CREATE TABLE gold.cases(customer_id VARCHAR, outcome VARCHAR, total_overdue DOUBLE, current_dpd INTEGER, case_open_date DATE)')
        c.execute('CREATE TABLE curated.promises_to_pay(crm_customer_id VARCHAR, ptp_status VARCHAR, status_ts TIMESTAMP)')
        c.execute('CREATE TABLE curated.contact_history(crm_customer_id VARCHAR, direction VARCHAR, channel VARCHAR, channel_v2 VARCHAR, contact_ts_utc TIMESTAMP)')
        c.execute('CREATE TABLE gold.latest_notes(customer_id VARCHAR, note_id VARCHAR, note_ts TIMESTAMP, note_text VARCHAR)')
        for cid in CUSTOMERS:
            c.execute('INSERT INTO gold.customers VALUES(?)', [cid])
            c.execute('INSERT INTO gold.crm_identity VALUES(?,?)', ['CRM-' + cid, cid])
        c.execute("""INSERT INTO gold.cases VALUES
          ('C1',NULL,1250.75,45,DATE '2026-08-01'),('C1','paid',99.0,0,DATE '2025-01-01'),
          ('C2',NULL,310.10,12,DATE '2026-09-01'),('C3','settled',500.0,0,DATE '2026-02-01')""")
        c.execute("""INSERT INTO curated.promises_to_pay VALUES
          ('CRM-C1','kept',TIMESTAMP '2026-09-01 10:00'),('CRM-C1','broken',TIMESTAMP '2026-09-10 10:00'),
          ('CRM-C1','broken',TIMESTAMP '2026-09-20 10:00'),('CRM-C2','open',TIMESTAMP '2026-09-25 10:00')""")
        c.execute("""INSERT INTO curated.contact_history VALUES
          ('CRM-C1','outbound','phone',NULL,TIMESTAMP '2026-09-23 09:00'),
          ('CRM-C1','outbound',NULL,'sms',TIMESTAMP '2026-09-27 09:00'),
          ('CRM-C1','outbound','system',NULL,TIMESTAMP '2026-09-24 09:00'),
          ('CRM-C2','inbound','phone',NULL,TIMESTAMP '2026-09-24 09:00')""")
        c.execute("""INSERT INTO gold.latest_notes VALUES
          ('C1','N1',TIMESTAMP '2026-09-20 12:00','Customer lost his job and cannot pay this month.'),
          ('C2','N2',TIMESTAMP '2026-09-21 12:00','Mes heures sont réduites, salaire en retard.'),
          ('C4','N4',TIMESTAMP '2026-09-22 12:00','Account reviewed; no issues raised.')""")
        c.execute('CREATE TABLE gold.features AS ' + feature_sql())
    (tmp_path / 'features-report.json').write_text(json.dumps({'version': VERSION}))
    return path


def change(db, sql, params=()):
    with duckdb.connect(str(db)) as c:
        c.execute(sql, list(params))


def test_identical_rows_pass_with_nulls(db):
    result = parity.check(db, sample_size=10, seed=7)
    assert result['status'] == 'pass' and result['mismatch_count'] == 0
    assert result['sample_size'] == len(CUSTOMERS) and result['stored_rows'] == len(CUSTOMERS)
    assert result['feature_version'] == VERSION and result['snapshot'] == '2026-09-28'
    # C3-C5 have no open case; C2-C5 have no resolved promise. NULL matches only NULL.
    assert result['sample_null_counts']['max_dpd'] == 3
    assert result['sample_null_counts']['broken_promise_ratio'] == 4
    assert parity.main(['--db', str(db), '--sample-size', '10']) == 0


def test_deliberately_changed_value_fails(db, tmp_path):
    change(db, "UPDATE gold.features SET total_overdue=total_overdue+0.01 WHERE customer_id='C1'")
    out = tmp_path / 'parity.json'
    assert parity.main(['--db', str(db), '--sample-size', '10', '--output', str(out)]) == 1
    report = json.loads(out.read_text())
    assert report['status'] == 'fail'
    [mismatch] = report['mismatches']
    assert (mismatch['kind'], mismatch['customer_id'], mismatch['column']) == ('value', 'C1', 'total_overdue')
    assert mismatch['stored'] == pytest.approx(1250.76) and mismatch['recomputed'] == pytest.approx(1250.75)


@pytest.mark.parametrize('sql,column', [
    ("UPDATE gold.features SET max_dpd=0 WHERE customer_id='C3'", 'max_dpd'),               # NULL -> 0
    ("UPDATE gold.features SET broken_promise_ratio=NULL WHERE customer_id='C1'", 'broken_promise_ratio'),  # value -> NULL
    ("UPDATE gold.features SET income_loss=0 WHERE customer_id='C1'", 'income_loss'),     # text cue flipped
    ("UPDATE gold.features SET contacts_7d=3 WHERE customer_id='C1'", 'contacts_7d'),
])
def test_null_and_cue_changes_fail(db, sql, column):
    change(db, sql)
    result = parity.check(db, sample_size=10)
    assert result['status'] == 'fail'
    assert [m['column'] for m in result['mismatches']] == [column]


def test_source_change_after_store_is_detected(db):
    # Stored rows are stale once a source row changes; the serving recomputation must disagree.
    change(db, "UPDATE gold.latest_notes SET note_text='Customer asked for payment relief.' WHERE customer_id='C4'")
    result = parity.check(db, sample_size=10)
    assert {(m['customer_id'], m['column']) for m in result['mismatches']} == {('C4', 'hardship_request')}


def test_missing_or_duplicate_rows_and_schema_drift_fail(db):
    change(db, "INSERT INTO gold.features SELECT * FROM gold.features WHERE customer_id='C2'")
    change(db, 'ALTER TABLE gold.features ADD COLUMN unexpected INTEGER')
    kinds = {(m['kind'], m.get('customer_id') or m.get('column') or m.get('rule')) for m in parity.check(db, sample_size=10)['mismatches']}
    assert kinds == {('row_count', 'C2'), ('schema', 'unexpected'), ('key_coverage', 'duplicate_customer_rows')}


def test_feature_version_drift_fails(db):
    (db.parent / 'features-report.json').write_text(json.dumps({'version': 'c360-financial-v0'}))
    result = parity.check(db, sample_size=10)
    assert [m['kind'] for m in result['mismatches']] == ['version']


def test_sample_is_reproducible_and_seeded(db):
    first = parity.check(db, sample_size=3, seed=11)
    with duckdb.connect(str(db), read_only=True) as c:
        assert parity.sample_ids(c, 3, 11) == parity.sample_ids(c, 3, 11)
        assert len(parity.sample_ids(c, 3, 11)) == first['sample_size'] == 3
        assert len({tuple(parity.sample_ids(c, 5, s)) for s in range(10)}) > 1
        assert len({frozenset(parity.sample_ids(c, 2, s)) for s in range(10)}) > 1


def test_checker_is_read_only(db):
    before = db.read_bytes()
    parity.check(db, sample_size=10)
    assert db.read_bytes() == before


def test_missing_database_or_table_exits_2(db, tmp_path):
    assert parity.main(['--db', str(tmp_path / 'absent.duckdb')]) == 2
    change(db, 'DROP TABLE gold.features')
    assert parity.main(['--db', str(db)]) == 2


def test_values_match_is_null_aware():
    assert parity.values_match(None, None)
    assert not parity.values_match(None, 0) and not parity.values_match(0, None)
    assert parity.values_match(math.nan, math.nan) and not parity.values_match(math.nan, 0.0)
    assert parity.values_match(0.1 + 0.2, 0.3) and not parity.values_match(1.0, 1.001)
    assert parity.values_match(1, 1) and not parity.values_match(1, 0) and parity.values_match('N1', 'N1')


@pytest.mark.parametrize('mutation,rule', [
    ("DELETE FROM gold.features WHERE customer_id='C1'", 'missing_stored_customers'),
    ("INSERT INTO gold.features SELECT * REPLACE('EXTRA' AS customer_id) FROM gold.features WHERE customer_id='C1'", 'extra_stored_customers'),
    ("INSERT INTO gold.features SELECT * REPLACE(NULL AS customer_id) FROM gold.features WHERE customer_id='C1'", 'null_customer_ids'),
    ("INSERT INTO gold.features SELECT * FROM gold.features WHERE customer_id='C1'", 'duplicate_customer_rows'),
])
def test_key_coverage_detects_drift_beyond_the_sample(db, mutation, rule):
    change(db, mutation)
    result = parity.check(db, sample_size=1)
    assert result['status'] == 'fail'
    assert result['key_coverage'][rule] == 1
    assert {'kind': 'key_coverage', 'rule': rule, 'count': 1} in result['mismatches']


def test_type_drift_fails_even_when_values_compare_equal(db):
    change(db, 'ALTER TABLE gold.features ALTER COLUMN contacts_7d TYPE DOUBLE')
    result = parity.check(db, sample_size=10)
    assert result['status'] == 'fail' and result['schema']['type_drift'] == ['contacts_7d']
    assert {m['kind'] for m in result['mismatches']} == {'schema_type', 'value'}
    assert {m['column'] for m in result['mismatches']} == {'contacts_7d'}


@pytest.mark.parametrize('metadata', [None, 'not JSON', '[]', '{}', '{"version":null}', '{"version":3}', '{"version":""}'])
def test_unverifiable_version_cannot_pass(db, metadata):
    report = db.parent / 'features-report.json'
    if metadata is None:
        report.unlink()
    else:
        report.write_text(metadata)
    with pytest.raises(parity.CheckError):
        parity.check(db, sample_size=10)
    assert parity.main(['--db', str(db)]) == 2


@pytest.mark.parametrize('alias', ['direct', 'symlink', 'hardlink'])
def test_output_cannot_overwrite_database_or_version_report(db, tmp_path, alias):
    import os
    for source in [db, db.parent / 'features-report.json']:
        before = source.read_bytes()
        output = source
        if alias != 'direct':
            output = tmp_path / ('alias-' + source.name)
            if alias == 'symlink':
                output.symlink_to(source)
            else:
                os.link(source, output)
        assert parity.main(['--db', str(db), '--output', str(output)]) == 2
        assert source.read_bytes() == before


def test_output_write_failure_returns_controlled_error(db, tmp_path):
    assert parity.main(['--db', str(db), '--output', str(tmp_path)]) == 2


@pytest.mark.parametrize('value', [math.nan, math.inf, -math.inf])
def test_nonfinite_mismatch_values_remain_distinct_from_null_in_valid_json(value):
    stored = parity.jsonable(value)
    assert stored is not None and isinstance(stored, str)
    assert json.loads(json.dumps({'stored': stored}, allow_nan=False))['stored'] == stored


@pytest.mark.parametrize('stored,recomputed', [('1.0', 1.0), (True, 1), (1, 1.0)])
def test_comparison_requires_matching_types(stored, recomputed):
    assert not parity.values_match(stored, recomputed)


def test_empty_store_returns_cannot_run(db):
    change(db, 'DELETE FROM gold.features')
    assert parity.main(['--db', str(db)]) == 2


def test_failed_atomic_output_preserves_existing_report(db, tmp_path, monkeypatch):
    output = tmp_path / 'previous.json'
    output.write_text('previous report')
    def fail_replace(*args, **kwargs):
        raise OSError('simulated replace failure')
    monkeypatch.setattr(Path, 'replace', fail_replace)
    assert parity.main(['--db', str(db), '--output', str(output)]) == 2
    assert output.read_text() == 'previous report'
    assert not list(tmp_path.glob('.feature-parity-*.tmp'))
