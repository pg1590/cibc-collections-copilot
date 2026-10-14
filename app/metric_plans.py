"""Validated metric plans compiled into reviewed SQL, never model-written SQL.

Definitions follow the release metric_definitions.csv. Identifiers below are
constant application code; dates and an optional province become bound parameters.
"""
from dataclasses import dataclass
from datetime import date, timedelta
import re

from app.settings import SNAPSHOT


class PlanError(ValueError):
    """A plan needs clarification or requests an unsupported calculation."""


class PlanRefusal(PlanError):
    """A structurally valid provider refusal uses a fixed application message."""


@dataclass
class CompiledPlan:
    sql: str
    params: list
    note: str
    metadata: dict


ASOF = date.fromisoformat(SNAPSHOT)
CHANNEL = "coalesce(h.channel_v2,h.channel)"
RESOLVED = "('kept','partially_kept','broken')"


PROVINCES = frozenset("AB BC MB NB NL NS NT NU ON PE QC SK YT".split())
PROVINCE_FILTER = 'Optional single filter {"province": "<two-letter code>"} on the collections case province; records without a linked case are excluded.'
NO_FILTER = "No custom filters supported."


def _entry(description, groupings, time_basis, denominator, filters=PROVINCE_FILTER, **extra):
    return dict(description=description, groupings=groupings,
                time_basis=time_basis, denominator=denominator,
                filters=filters, **extra)


CATALOG = {
    "promise_kept_rate": _entry("Kept promises / resolved promises, by due date.", ["none", "queue", "product", "site", "channel", "province", "month"], "promise due date", "kept, partially_kept and broken promises"),
    "broken_promise_rate": _entry("Broken promises / resolved promises, by due date.", ["none", "queue", "product", "site", "channel", "prior_broken", "province", "month"], "promise due date", "kept, partially_kept and broken promises"),
    "rpc_rate": _entry("Right-party contacts / outbound call attempts.", ["none", "hour", "channel", "agent_site", "province", "month"], "contact date", "outbound calls"),
    "ptp_rate": _entry("Promises recorded per right-party contact.", ["none", "channel", "agent_site", "province", "month"], "contact date", "right-party non-system contacts"),
    "cost_per_contact": _entry("Contact costs / non-system contact records.", ["none", "channel", "agent_site", "province", "month"], "contact date", "non-system contact records"),
    "cost_per_rpc": _entry("All non-system contact costs / right-party contacts.", ["none", "channel", "agent_site", "province", "month"], "contact date", "right-party non-system contacts"),
    "hardship_rate": _entry("Share of cases with hardship recorded; not a reviewed determination.", ["none", "province", "product", "queue", "month"], "case open date", "cases opened within period"),
    "cure_rate": _entry("Cases open at period start that cure during the period.", ["none", "product", "province", "queue", "month"], "calendar period", "cases open at start, excluding insolvency/deceased holds"),
    "average_dpd": _entry("Mean recorded DPD among currently open cases.", ["none", "queue", "bucket", "product", "province"], "snapshot", "open cases with nonmissing current DPD", snapshot_only=True),
    "contact_attempts_per_case": _entry("Period outbound attempts / distinct cases receiving those attempts.", ["none", "bucket", "queue", "product", "province", "month"], "contact date", "distinct case IDs with outbound contacts in period"),
    "delinquency_rate": _entry("Card accounts 1+ DPD / active or blocked cards with known DPD.", ["none", "product", "bucket"], "snapshot", "active/blocked card accounts with nonmissing DPD", filters=NO_FILTER, snapshot_only=True, scope="cards only; lending has no authoritative active-status field"),
    "write_off_rate": _entry("Accounts charged off in period / accounts in the extract register.", ["none", "product"], "charge-off date", "all extracted card and loan account records; not period-start balances", filters=NO_FILTER),
    "open_cases": _entry("Currently open cases (no recorded outcome).", ["none", "queue", "bucket", "product", "province"], "snapshot", "source-wide collections cases", snapshot_only=True, extension=True),
    "open_overdue_amount": _entry("Total recorded overdue CAD on currently open cases.", ["none", "queue", "product", "province"], "snapshot", "open cases with recorded total_overdue", snapshot_only=True, extension=True),
    "open_hardship_cases": _entry("Count currently open cases with a recorded hardship flag.", ["none", "queue", "product", "province"], "snapshot", "open cases with hardship_flag=true; not reviewed eligibility", snapshot_only=True, extension=True),
    "open_insolvency_cases": _entry("Count and overdue CAD on currently open cases with insolvency hold.", ["none", "queue", "product", "province"], "snapshot", "open cases with insolvency_hold_flag=true", snapshot_only=True, extension=True),
    "average_days_to_cure": _entry("Mean recorded days from case opening to cure among cases curing in period.", ["none", "queue", "product", "province", "month"], "cure date", "cure_flag=true and cure_date in period; average excludes missing days_to_cure", extension=True),
    "sms_payment_link_click_share": _entry("Clicked payment-link SMS send events / outbound SMS send events with a payment_link_id.", ["none", "month"], "SMS send contact date", "outbound SMS contact rows with non-null payment_link_id; repeated sends count separately", filters=NO_FILTER, extension=True),
}

_ALLOWED = {"metric_id", "grouping", "start_date", "end_date", "filters", "clarification", "refuse", "refuse_reason"}
_UNSUPPORTED = {
    "collected_amount": "Please specify payments against promises, or all payments on collection-case accounts. The available promise payment sum does not establish the full certified collected_amount definition.",
    "roll_rate": "Please specify supported snapshot endpoints, start bucket, destination bucket and exclusions; the generic planner does not compile roll-rate cohorts.",
    "payroll_delay_share": "Please use the supported open-case payroll question; the generic planner does not select an identity-linked payroll cohort.",
}


def _iso(value, name):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise PlanError(f"{name} must be an ISO date (YYYY-MM-DD).")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise PlanError(f"{name} is not a valid calendar date.") from exc


def _validate(spec):
    if not isinstance(spec, dict) or set(spec) - _ALLOWED:
        raise PlanError("The metric plan contains unsupported fields.")
    filters = spec.get("filters", {})
    if not isinstance(filters, dict) or set(filters) - {"province"}:
        raise PlanError("Custom filters other than a single province are unsupported; please clarify the required cohort.")
    province = filters.get("province")
    if "province" in filters and (not isinstance(province, str) or province not in PROVINCES):
        raise PlanError("The province filter must be a two-letter Canadian province or territory code.")
    if type(spec.get("refuse", False)) is not bool:
        raise PlanError("refuse must be a boolean.")
    for key in ("clarification", "refuse_reason"):
        if spec.get(key) is not None and not isinstance(spec[key], str):
            raise PlanError(f"{key} must be text or null.")
    if spec.get("refuse"):
        raise PlanRefusal("This request cannot be answered within permitted collections metrics and access rules.")
    if spec.get("clarification"):
        raise PlanError(spec["clarification"][:500])
    metric = spec.get("metric_id")
    if not isinstance(metric, str):
        raise PlanError("Please specify a supported metric_id.")
    if metric in _UNSUPPORTED:
        raise PlanError(_UNSUPPORTED[metric])
    if metric not in CATALOG:
        raise PlanError("Unknown metric; please choose a supported metric from the catalog.")
    grouping = spec.get("grouping", "none")
    if not isinstance(grouping, str) or grouping not in CATALOG[metric]["groupings"]:
        raise PlanError(f"Unsupported grouping for {metric}; supported groupings: {', '.join(CATALOG[metric]['groupings'])}.")
    start = _iso(spec.get("start_date"), "start_date")
    end = _iso(spec.get("end_date"), "end_date")
    if start >= end or end > ASOF + timedelta(days=1):
        raise PlanError(f"Use a nonempty, end-exclusive period ending no later than {ASOF + timedelta(days=1)}.")
    if CATALOG[metric].get("snapshot_only"):
        if start != ASOF or end != ASOF + timedelta(days=1):
            raise PlanError(f"This metric supports only the {SNAPSHOT} snapshot, not historical reconstruction.")
    elif start < date(2016, 10, 3):
        raise PlanError("The requested period begins before supported extract coverage (2016-10-03).")
    if metric == "cure_rate" and (start.day != 1 or (end.day != 1 and end != ASOF + timedelta(days=1))):
        raise PlanError("Cure rate uses calendar-month cohorts; specify whole months or the current month to the snapshot.")
    if province and CATALOG[metric]["filters"] == NO_FILTER:
        raise PlanError(f"{metric} has no reviewed province source; request it without a province filter or by a supported grouping.")
    return metric, grouping, start, end, province


def _select(group, metric_expr, counts, table, where):
    """group is a constant (expression, output alias) selected by application code."""
    prefix = f"{group[0]} AS {group[1]}, " if group else ""
    count_expr = f", {counts}" if counts else ""
    return f"SELECT {prefix}{metric_expr}{count_expr} FROM {table} WHERE {where}" + (" GROUP BY 1 ORDER BY 1" if group else "")


def compile_plan(spec: dict) -> CompiledPlan:
    metric, grouping, start, end, province = _validate(spec)
    params = [start, end]
    # Province is a whitelisted code bound as a parameter, matched on the linked case.
    region = " AND c.province_code=?" if province else ""
    note = "Dates use an inclusive start and exclusive end. Source-wide curated records are used."
    case_groups = {"none": None, "queue": ("coalesce(c.queue,'unknown')", "queue"), "bucket": ("coalesce(c.current_bucket,'unknown')", "current_bucket"), "product": ("coalesce(c.primary_product,'unknown')", "primary_product"), "province": ("coalesce(c.province_code,'unknown')", "province_code")}
    if metric in ("promise_kept_rate", "broken_promise_rate"):
        groups = {"none": None, "queue": ("coalesce(c.queue,'unknown')", "queue"), "product": ("coalesce(p.product,'unknown')", "product"), "site": ("CASE WHEN p.agent_id IS NULL THEN 'self_serve' ELSE coalesce(a.site,'unknown') END", "site"), "channel": ("coalesce(p.ptp_channel,'unknown')", "ptp_channel"), "prior_broken": ("least(p.prior_broken_ptp_count,3)", "prior_broken"), "province": case_groups["province"], "month": ("strftime(p.ptp_due_date,'%Y-%m')", "month")}
        joins = " LEFT JOIN curated.collections_cases c USING(case_id)" if grouping in ("queue", "province") else " LEFT JOIN curated.agents a USING(agent_id)" if grouping == "site" else ""
        if province and grouping not in ("queue", "province"): joins += " LEFT JOIN curated.collections_cases c ON c.case_id=p.case_id"
        status = "kept" if metric == "promise_kept_rate" else "broken"
        alias = "promise_kept_rate_pct" if status == "kept" else "broken_rate_pct"
        sql = _select(groups[grouping], f"round(100.0*sum(CASE WHEN p.ptp_status='{status}' THEN 1 ELSE 0 END)/nullif(count(*),0),1) {alias}", "count(*) resolved_promises", "curated.promises_to_pay p" + joins, f"p.ptp_due_date>=? AND p.ptp_due_date<? AND p.ptp_status IN {RESOLVED}" + region)
        note += " Open/cancelled promises are excluded; unknown groups retain unlinked source records. Queue/site reflect the extract's reference values."
        if grouping == "prior_broken": note += " prior_broken=3 denotes three or more; null remains unknown."
        if grouping == "channel": note += " Channel is where the promise was taken (ptp_channel), not a joined contact channel."
    elif metric in ("rpc_rate", "ptp_rate", "cost_per_contact", "cost_per_rpc"):
        groups = {"none": None, "hour": ("h.contact_hour_local", "contact_hour_local"), "channel": (CHANNEL, "channel"), "agent_site": ("CASE WHEN h.agent_id IS NULL THEN 'self_serve' ELSE coalesce(a.site,'unknown') END", "agent_site"), "province": case_groups["province"], "month": ("strftime(h.contact_ts_local,'%Y-%m')", "month")}
        joins = " LEFT JOIN curated.agents a USING(agent_id)" if grouping == "agent_site" else ""
        if province or grouping == "province": joins += " LEFT JOIN curated.collections_cases c ON c.case_id=h.case_id"
        where = f"{CHANNEL}!='system' AND h.contact_ts_local>=? AND h.contact_ts_local<?"
        if metric == "rpc_rate":
            where += f" AND {CHANNEL}='call' AND h.direction='outbound'"
            expr, count = "round(100.0*sum(CASE WHEN h.rpc_flag THEN 1 ELSE 0 END)/nullif(count(*),0),1) rpc_rate_pct", "count(*) attempts"
        elif metric == "ptp_rate":
            where += " AND h.rpc_flag"
            expr, count = "round(100.0*sum(CASE WHEN h.ptp_made_flag THEN 1 ELSE 0 END)/nullif(count(*),0),2) ptp_rate_pct", "count(*) right_party_contacts"
        elif metric == "cost_per_contact":
            expr, count = "round(sum(h.contact_cost_cad)/nullif(count(h.contact_id),0),2) cost_per_contact_cad", "count(h.contact_id) contacts"
        else:
            expr, count = "round(sum(h.contact_cost_cad)/nullif(sum(CASE WHEN h.rpc_flag THEN 1 ELSE 0 END),0),2) cost_per_rpc_cad", "sum(CASE WHEN h.rpc_flag THEN 1 ELSE 0 END) right_party_contacts"
        sql = _select(groups[grouping], expr, count, "curated.contact_history h" + joins, where + region)
        note += " Contact periods use recorded local timestamps; channel_v2 takes precedence over legacy channel."
    elif metric in ("hardship_rate", "cure_rate", "average_dpd", "open_cases", "open_overdue_amount", "open_hardship_cases", "open_insolvency_cases", "average_days_to_cure"):
        if metric == "hardship_rate":
            expr, count, where = "round(100.0*sum(CASE WHEN c.hardship_flag THEN 1 ELSE 0 END)/nullif(count(*),0),1) hardship_rate_pct", "count(*) cases", "c.case_open_date>=? AND c.case_open_date<?"
            note += " Recorded hardship flags are not independently reviewed hardship determinations."
        elif metric == "cure_rate":
            expr = "round(100.0*sum(CASE WHEN c.cure_date>=? AND c.cure_date<? THEN 1 ELSE 0 END)/nullif(count(*),0),2) cure_rate_pct"
            count = "count(*) cases_open_at_start"
            where = "c.case_open_date<? AND (c.outcome_date>=? OR c.outcome IS NULL) AND NOT coalesce(c.insolvency_hold_flag,false) AND NOT coalesce(c.deceased_hold_flag,false)"
            params = [start, end, start, start]
            note += " The cohort is open at period start, not cases first opened during the period. Unknown closure dates on closed cases are excluded."
        elif metric == "average_dpd":
            expr, count, where = "round(avg(c.current_dpd),1) avg_dpd", "count(*) cases_with_dpd", "c.outcome IS NULL AND c.current_dpd IS NOT NULL"
            params = []
            note = f"Current source-wide cases at {SNAPSHOT}; missing current DPD is excluded."
        elif metric == "average_days_to_cure":
            expr, count, where = "round(avg(c.days_to_cure),2) average_days_to_cure", "count(*) cured_cases, count(c.days_to_cure) cases_with_days_to_cure", "c.cure_flag AND c.cure_date>=? AND c.cure_date<?"
            note += " The period filters cure_date, not opening or outcome date; days_to_cure is the recorded opening-to-cure duration. This requested cured-case population does not inherit the distinct cure-rate hold exclusions."
        elif metric in ("open_overdue_amount", "open_hardship_cases", "open_insolvency_cases"):
            params = []
            where = "c.outcome IS NULL"
            if metric == "open_hardship_cases":
                expr, count = "count(*) open_hardship_cases", None
                where += " AND c.hardship_flag"
                note = f"Open hardship-flagged cases at {SNAPSHOT}; recorded flags are not reviewed eligibility determinations. Contact/insolvency holds remain included in this descriptive count."
            else:
                expr, count = "round(sum(c.total_overdue),2) overdue_cad", "count(*) open_cases, count(c.total_overdue) cases_with_overdue"
                if metric == "open_insolvency_cases":where += " AND c.insolvency_hold_flag"
                note = f"Open means no recorded outcome at {SNAPSHOT}. Uses recorded total_overdue in CAD; missing amounts are excluded from the sum and reported by the non-null count."
                if metric == "open_insolvency_cases":note += " Includes only cases with insolvency_hold_flag=true; no contact action is authorized."
        else:
            expr, count, where = "count(*) open_cases", None, "c.outcome IS NULL"
            params = []
            note = f"Open means no recorded outcome at {SNAPSHOT}. Source bucket labels are retained; discrepancies are reported in data quality."
        month = {"hardship_rate": "c.case_open_date", "average_days_to_cure": "c.cure_date"}.get(metric)
        sql = _select((f"strftime({month},'%Y-%m')", "month") if grouping == "month" else case_groups[grouping], expr, count, "curated.collections_cases c", where + region)
        if metric == "cure_rate" and grouping == "month":
            # Each month keeps its own open-at-start cohort; the last month ends at the period end.
            sql = ("WITH months AS (SELECT cast(m AS DATE) month_start, least(cast(m + INTERVAL 1 MONTH AS DATE), ?) month_end FROM range(cast(? AS TIMESTAMP), cast(? AS TIMESTAMP), INTERVAL 1 MONTH) t(m)) "
                   "SELECT strftime(m.month_start,'%Y-%m') AS month, round(100.0*sum(CASE WHEN c.cure_date>=m.month_start AND c.cure_date<m.month_end THEN 1 ELSE 0 END)/nullif(count(*),0),2) cure_rate_pct, count(*) cases_open_at_start "
                   "FROM months m JOIN curated.collections_cases c ON c.case_open_date<m.month_start AND (c.outcome_date>=m.month_start OR c.outcome IS NULL) "
                   "WHERE NOT coalesce(c.insolvency_hold_flag,false) AND NOT coalesce(c.deceased_hold_flag,false)" + region + " GROUP BY 1 ORDER BY 1")
            params = [end, start, end]
    elif metric == "sms_payment_link_click_share":
        sql = _select(("strftime(h.contact_ts_local,'%Y-%m')", "month") if grouping == "month" else None, "round(100.0*sum(CASE WHEN h.link_clicked_flag THEN 1 ELSE 0 END)/nullif(count(*),0),2) sms_payment_link_clicked_pct", "count(*) payment_link_sms_sent, sum(CASE WHEN h.link_clicked_flag THEN 1 ELSE 0 END) clicked_sms", "curated.contact_history h", f"{CHANNEL}='sms' AND h.direction='outbound' AND h.payment_link_id IS NOT NULL AND h.contact_ts_local>=? AND h.contact_ts_local<?")
        note += " The cohort is SMS send events with a payment link, not all SMS or distinct link IDs; repeated sends count separately. Missing click flags count as not clicked. Click flags reflect the extract snapshot, rather than clicks occurring only inside the send-date period."
    elif metric == "contact_attempts_per_case":
        joins = " LEFT JOIN curated.collections_cases c USING(case_id)" if grouping not in ("none", "month") else " LEFT JOIN curated.collections_cases c ON c.case_id=h.case_id" if province else ""
        groups = {**case_groups, "month": ("strftime(h.contact_ts_local,'%Y-%m')", "month")}
        sql = _select(groups[grouping], "round(count(*)*1.0/nullif(count(DISTINCT h.case_id),0),2) attempts_per_case", "count(DISTINCT h.case_id) contacted_cases, count(*) outbound_attempts", "curated.contact_history h" + joins, "h.direction='outbound' AND h.contact_ts_local>=? AND h.contact_ts_local<? AND h.case_id IS NOT NULL" + region)
        note += " The denominator contains cases with outbound records in this period, including recorded outbound system events, as the certified metric specifies outbound only. This is not the separate all-open-case lifetime-attempts measure."
    elif metric == "delinquency_rate":
        groups = {"none": None, "product": ("a.product_code", "product_code"), "bucket": ("a.dpd_bucket", "dpd_bucket")}
        sql = _select(groups[grouping], "round(100.0*sum(CASE WHEN a.dpd>=1 THEN 1 ELSE 0 END)/nullif(count(*),0),2) delinquency_rate_pct", "count(*) accounts, sum(CASE WHEN a.dpd>=1 THEN 1 ELSE 0 END) delinquent_accounts", "curated.card_accounts a", "a.snapshot_date=? AND a.account_status IN ('active','blocked') AND a.dpd IS NOT NULL")
        params = [ASOF]
        note = f"Card snapshot at {SNAPSHOT}; active and blocked cards with known DPD only. Missing DPD is excluded and counted in data-quality reporting. Reported source bucket labels are retained; DPD/bucket discrepancies are reported separately. Rates are within each group, not contributions to an overall rate."
    elif metric == "write_off_rate":
        sql = "WITH accounts AS (SELECT 'card' product,chargeoff_date FROM curated.card_accounts UNION ALL SELECT product_type product,chargeoff_date FROM curated.loan_accounts) "
        group = ("coalesce(a.product,'unknown')", "product") if grouping == "product" else None
        sql += _select(group, "round(100.0*sum(CASE WHEN a.chargeoff_date>=? AND a.chargeoff_date<? THEN 1 ELSE 0 END)/nullif(count(*),0),2) write_off_rate_pct", "count(*) accounts", "accounts a", "true")
        note += " Denominator is the full extracted account register, including closed accounts; not a historical period-start account inventory or annualized rate."
    else:  # Catalog additions require an explicit reviewed compiler branch.
        raise PlanError("This catalog metric has no reviewed SQL compiler.")
    if grouping == "month":
        note += " Months (YYYY-MM) follow the metric's own time basis; edge months cover only the part inside the period."
    definition = "schema/schema.json; reviewed application extension" if CATALOG[metric].get("extension") else "data/metric_definitions.csv"
    metadata = {"metric_id": metric, "grouping": grouping, "start_date": start.isoformat(), "end_date": end.isoformat(), "definition_source": definition, "denominator": CATALOG[metric]["denominator"]}
    if province:
        params = [*params, province]
        metadata["filters"] = {"province": province}
        note += f" Filtered to province {province} using the collections case province_code; records without a linked case are excluded."
    return CompiledPlan(sql, params, note, metadata)
