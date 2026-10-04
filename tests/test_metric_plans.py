"""Semantic and security boundaries for model-proposed metric plans."""
from datetime import date

import duckdb
import pytest

from app.metric_plans import CATALOG, PlanError, compile_plan


def spec(metric="promise_kept_rate", grouping="none", **changes):
    value = {"metric_id": metric, "grouping": grouping, "start_date": "2026-08-01", "end_date": "2026-09-01", "filters": {}, "clarification": None, "refuse": False, "refuse_reason": None}
    value.update(changes)
    return value


@pytest.mark.parametrize("changes", [
    {"grouping": "queue; DROP TABLE customers"},
    {"grouping": "gender"}, {"grouping": ["queue"]},
    {"metric_id": "read_csv('/etc/passwd')"},
    {"sql": "SELECT * FROM curated.customers"},
    {"filters": {"province_code": "ON"}}, {"filters": []},
    {"start_date": "2026-02-30"}, {"start_date": "2026-8-01"},
    {"start_date": "2026-09-01"}, {"end_date": "2026-10-01"},
    {"refuse": "false"}, {"clarification": ["unknown"]},
])
def test_untrusted_plans_cannot_become_queries(changes):
    with pytest.raises(PlanError):
        compile_plan(spec(**changes))


def test_snapshot_dates_cannot_silently_change_the_population():
    with pytest.raises(PlanError, match="snapshot"):
        compile_plan(spec("open_cases"))
    plan = compile_plan(spec("delinquency_rate", "bucket", start_date="2026-09-28", end_date="2026-09-29"))
    assert plan.params == [date(2026, 9, 28)]
    assert "dpd IS NOT NULL" in plan.sql
    assert "active','blocked" in plan.sql


@pytest.mark.parametrize("metric", ["collected_amount", "roll_rate", "payroll_delay_share"])
def test_unsupported_cohorts_request_clarification(metric):
    with pytest.raises(PlanError):
        compile_plan(spec(metric))


def test_promise_queue_keeps_unlinked_records_and_uses_due_dates():
    with duckdb.connect() as db:
        db.execute("CREATE SCHEMA curated")
        db.execute("CREATE TABLE curated.promises_to_pay(case_id VARCHAR,ptp_due_date DATE,ptp_status VARCHAR)")
        db.execute("CREATE TABLE curated.collections_cases(case_id VARCHAR,queue VARCHAR)")
        db.execute("INSERT INTO curated.collections_cases VALUES ('linked','early')")
        db.execute("INSERT INTO curated.promises_to_pay VALUES ('linked','2026-08-12','kept'),('linked','2026-08-12','broken'),('missing','2026-08-12','kept'),('linked','2026-08-12','open'),('linked','2026-09-01','kept')")
        plan = compile_plan(spec(grouping="queue"))
        assert plan.params == [date(2026, 8, 1), date(2026, 9, 1)]
        assert db.execute(plan.sql, plan.params).fetchall() == [("early", 50.0, 2), ("unknown", 100.0, 1)]


def test_ptp_site_uses_agent_site_and_rpc_denominator():
    with duckdb.connect() as db:
        db.execute("CREATE SCHEMA curated")
        db.execute("CREATE TABLE curated.agents(agent_id VARCHAR,site VARCHAR)")
        db.execute("CREATE TABLE curated.contact_history(agent_id VARCHAR,channel VARCHAR,channel_v2 VARCHAR,contact_ts_local TIMESTAMP,rpc_flag BOOLEAN,ptp_made_flag BOOLEAN)")
        db.execute("INSERT INTO curated.agents VALUES ('a','Toronto'),('b','Halifax')")
        db.execute("INSERT INTO curated.contact_history VALUES ('a','call',NULL,'2026-08-10',true,true),('a','call',NULL,'2026-08-10',true,false),('b','call','system','2026-08-10',true,true),('b','call',NULL,'2026-08-10',false,true)")
        plan = compile_plan(spec("ptp_rate", "agent_site"))
        assert db.execute(plan.sql, plan.params).fetchall() == [("Toronto", 50.0, 2)]
        assert "coalesce(a.site" in plan.sql


def test_contact_attempt_denominator_is_contacted_cases_in_period():
    with duckdb.connect() as db:
        db.execute("CREATE SCHEMA curated")
        db.execute("CREATE TABLE curated.contact_history(case_id VARCHAR,direction VARCHAR,contact_ts_local TIMESTAMP)")
        db.execute("INSERT INTO curated.contact_history VALUES ('a','outbound','2026-08-10'),('a','outbound','2026-08-11'),('b','outbound','2026-08-10'),('c','outbound','2026-07-10'),('d','inbound','2026-08-10')")
        plan = compile_plan(spec("contact_attempts_per_case"))
        assert db.execute(plan.sql, plan.params).fetchone() == (1.5, 2, 3)


def test_cure_denominator_is_open_at_start_and_holds_are_excluded():
    with duckdb.connect() as db:
        db.execute("CREATE SCHEMA curated")
        db.execute("CREATE TABLE curated.collections_cases(case_open_date DATE,outcome_date DATE,outcome VARCHAR,cure_date DATE,insolvency_hold_flag BOOLEAN,deceased_hold_flag BOOLEAN)")
        db.execute("INSERT INTO curated.collections_cases VALUES ('2026-07-01','2026-08-10','cured','2026-08-10',false,false),('2026-07-01',NULL,NULL,NULL,false,false),('2026-08-10','2026-08-15','cured','2026-08-15',false,false),('2026-07-01','2026-08-10','cured','2026-08-10',true,false)")
        plan = compile_plan(spec("cure_rate"))
        assert plan.params == [date(2026, 8, 1), date(2026, 9, 1), date(2026, 8, 1), date(2026, 8, 1)]
        assert db.execute(plan.sql, plan.params).fetchone() == (50.0, 2)


def test_cure_calendar_cohort_does_not_accept_arbitrary_days():
    with pytest.raises(PlanError, match="calendar-month"):
        compile_plan(spec("cure_rate", start_date="2026-08-10", end_date="2026-08-20"))


def test_every_catalog_grouping_has_a_bound_compiler_branch():
    for metric, config in CATALOG.items():
        dates = {"start_date": "2026-09-28", "end_date": "2026-09-29"} if config.get("snapshot_only") else {}
        for grouping in config["groupings"]:
            plan = compile_plan(spec(metric, grouping, **dates))
            assert plan.sql.count("?") == len(plan.params)
            assert plan.metadata["metric_id"] == metric
            assert "gold." not in plan.sql
            assert "2026-08-01" not in plan.sql
