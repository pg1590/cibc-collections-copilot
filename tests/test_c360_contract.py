"""The C360 contract checker must catch invalid data without changing the database."""
import hashlib
import json
import sys
from pathlib import Path

import duckdb
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import check_c360_contract as checker

VALID_ROWS = """INSERT INTO gold.customer_summary VALUES
 ('000123','Alpha Example','ON','en',2,150.5,45,0.99),
 ('C-2','Beta Example','QC','fr',0,0.0,NULL,1.0),
 ('C-3',NULL,NULL,NULL,1,20.0,10,NULL)"""


def build(path, mutation=None, schema=None):
    connection = duckdb.connect(str(path))
    connection.execute('CREATE SCHEMA gold')
    connection.execute(schema or """CREATE TABLE gold.customer_summary(customer_id VARCHAR,name VARCHAR,province VARCHAR,
        preferred_language VARCHAR,open_cases BIGINT,total_overdue DOUBLE,max_dpd INTEGER,identity_confidence DECIMAL(4,3))""")
    connection.execute(VALID_ROWS)
    if mutation:
        connection.execute(mutation)
    connection.close()
    return path


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def failures(result):
    return {(c['rule'], c['column']): c['measured'] for c in result['checks'] if c['result'] == 'fail'}


def test_valid_fixture_satisfies_the_repository_contract(tmp_path):
    result = checker.check(build(tmp_path / 'valid.duckdb'))
    assert result['failed'] == 0 and result['skipped'] == 0
    assert result['rows'] == 3 and result['database_unchanged']
    rules = {(c['rule'], c['column']) for c in result['checks']}
    assert {('unique', 'customer_id'), ('not_null', 'customer_id'), ('minimum', 'open_cases'), ('type', 'total_overdue')} <= rules


@pytest.mark.parametrize('mutation,rule,column,measured', [
    ("INSERT INTO gold.customer_summary VALUES ('C-2','Copy','ON','en',1,1.0,1,1.0)", 'unique', 'customer_id', '1 duplicate values'),
    ("INSERT INTO gold.customer_summary VALUES (NULL,'No ID','ON','en',1,1.0,1,1.0)", 'not_null', 'customer_id', '1 null rows'),
    ("UPDATE gold.customer_summary SET open_cases=-1 WHERE customer_id='C-3'", 'minimum', 'open_cases', '1 rows below 0'),
    ("UPDATE gold.customer_summary SET total_overdue=NULL WHERE customer_id='C-2'", 'not_null', 'total_overdue', '1 null rows'),
    ('ALTER TABLE gold.customer_summary DROP COLUMN max_dpd', 'column_present', 'max_dpd', 'missing'),
    ('ALTER TABLE gold.customer_summary ADD COLUMN gender_code VARCHAR', 'undeclared_column', 'gender_code', 'present (VARCHAR)'),
])
def test_deliberately_invalid_data_is_reported_with_measured_counts(tmp_path, mutation, rule, column, measured):
    result = checker.check(build(tmp_path / 'invalid.duckdb', mutation))
    assert failures(result) == {(rule, column): measured}


def test_incompatible_type_fails_and_dependent_rule_is_not_guessed(tmp_path):
    schema = """CREATE TABLE gold.customer_summary(customer_id VARCHAR,name VARCHAR,province VARCHAR,
        preferred_language VARCHAR,open_cases VARCHAR,total_overdue DOUBLE,max_dpd DOUBLE,identity_confidence DECIMAL(4,3))"""
    result = checker.check(build(tmp_path / 'types.duckdb', schema=schema))
    assert failures(result) == {('type', 'open_cases'): 'VARCHAR', ('type', 'max_dpd'): 'DOUBLE'}
    skipped = [c for c in result['checks'] if c['result'] == 'skipped']
    assert [(c['rule'], c['column']) for c in skipped] == [('minimum', 'open_cases')]


def test_missing_product_table_fails_without_crashing(tmp_path):
    path = tmp_path / 'empty.duckdb'
    duckdb.connect(str(path)).close()
    result = checker.check(path)
    assert failures(result) == {('product_exists', None): 'missing'} and result['rows'] is None


def test_unsupported_contract_type_and_primary_key_are_enforced(tmp_path):
    contract = tmp_path / 'contract.yaml'
    contract.write_text("""contract_id: TEST
version: 0.1
product: gold.customer_summary
primary_key: customer_id
columns:
  customer_id: {type: uuid}
""")
    path = build(tmp_path / 'pk.duckdb', "INSERT INTO gold.customer_summary VALUES ('C-2','Copy','ON','en',1,1.0,1,1.0)")
    result = checker.check(path, contract)
    found = failures(result)
    assert found[('type', 'customer_id')] == 'VARCHAR'
    assert found[('unique', 'customer_id')] == '1 duplicate values'
    assert ('undeclared_column', 'open_cases') in found
    assert next(c for c in result['checks'] if c['rule'] == 'type')['expected'] == 'uuid (unsupported contract type)'


def test_checker_never_modifies_the_database(tmp_path):
    path = build(tmp_path / 'readonly.duckdb', "UPDATE gold.customer_summary SET open_cases=-5")
    before = digest(path)
    result = checker.check(path)
    assert digest(path) == before and result['database_unchanged']
    assert not Path(str(path) + '.wal').exists()


def test_report_shows_measured_results_and_unchecked_contract_items(tmp_path):
    path = build(tmp_path / 'report.duckdb', "INSERT INTO gold.customer_summary VALUES ('C-2','Copy','ON','en',1,1.0,1,1.0)")
    report = tmp_path / 'report.md'
    checker.write_report(checker.check(path), report, path, checker.CONTRACT)
    text = report.read_text()
    assert '| unique | customer_id | 0 duplicate values | 1 duplicate values | fail |' in text
    assert '## Contract items this script does not check' in text
    for item in ['identity', 'quality', 'access', 'protected_fields', 'refresh', 'columns.total_overdue.unit']:
        assert f'| {item} |' in text
    assert str(tmp_path) not in text


def test_every_top_level_contract_item_is_either_checked_or_listed():
    import yaml
    contract = yaml.safe_load(checker.CONTRACT.read_text())
    listed = {u['item'] for u in checker.unchecked_items(contract)}
    assert set(contract) <= checker.CHECKED_SECTIONS | listed
    assert all(spec['type'] in checker.COMPATIBLE for spec in contract['columns'].values())


def test_cli_exit_codes_and_outputs(tmp_path):
    outputs = ['--report', str(tmp_path / 'r.md'), '--json', str(tmp_path / 'r.json')]
    assert checker.main(['--db', str(build(tmp_path / 'ok.duckdb')), *outputs]) == 0
    assert json.loads((tmp_path / 'r.json').read_text())['failed'] == 0
    bad = build(tmp_path / 'bad.duckdb', 'UPDATE gold.customer_summary SET open_cases=-1')
    assert checker.main(['--db', str(bad), *outputs]) == 1
    assert checker.main(['--db', str(tmp_path / 'absent.duckdb'), *outputs]) == 2
