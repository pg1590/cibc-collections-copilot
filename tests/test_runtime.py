"""External evidence selection cannot replace local facts or disclose identifiers."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from app import runtime
from app.gemini import ProviderUnavailable


class FakeProvider:
    configured = True

    def __init__(self, fail_summary=False):
        self.fail_summary = fail_summary
        self.calls = []
        self.begin_trace()

    def begin_trace(self):
        self.stages = {"plan": "local", "summary": "local"}

    def mark(self, stage, status):
        self.stages[stage] = status

    def trace_metadata(self):
        stages = dict(self.stages)
        status = "generated" if "generated" in stages.values() else "fallback" if "fallback" in stages.values() else "local"
        return {"provider": "gemini" if status == "generated" else "local", "status": status, "stages": stages}

    def summarise(self, kind, sources, question=""):
        self.calls.append({"kind": kind, "sources": deepcopy(sources), "question": question})
        if self.fail_summary:
            raise ProviderUnavailable("Simulated provider failure")
        self.mark("summary", "generated")
        return {"text": "Verified evidence selection", "source_ids": list(sources)}


def result(**changes):
    value = {"answer": "open_cases\n42", "rows": [{"open_cases": 42}], "sources": ["collections_cases"], "sql_or_sources": "SELECT count(*) open_cases FROM curated.collections_cases", "refused": False, "reason": None}
    value.update(changes)
    return value


def install(monkeypatch, value, planned=False, fail_summary=False):
    client = FakeProvider(fail_summary)
    def local_answer(question, role):
        if planned:
            client.mark("plan", "generated")
        return deepcopy(value)
    instance = SimpleNamespace(answer=local_answer, sections=[])
    monkeypatch.setattr(runtime, "provider", lambda: client)
    monkeypatch.setattr(runtime, "engine", lambda *args: instance)
    monkeypatch.delenv("COPILOT_GEMINI_TEXT_EVIDENCE", raising=False)
    return client


@pytest.mark.parametrize("changes,expected", [
    ({"plan": {"metric_id": "open_cases"}}, "generated"),
    ({}, "fallback"),
    ({"reason": "clarification_required", "rows": []}, "fallback"),
    ({"plan": {"metric_id": "open_cases"}, "reason": "execution_error"}, "fallback"),
])
def test_plan_stage_reports_semantic_acceptance(monkeypatch, changes, expected):
    client = install(monkeypatch, result(**changes), planned=True)
    observed = runtime.answer("How many open cases?")
    assert observed["generation"]["stages"]["plan"] == expected
    if not changes.get("reason"):
        # A successful summary must not conceal a rejected planning stage.
        assert observed["generation"]["stages"]["summary"] == "generated"
        assert client.calls


@pytest.mark.parametrize("changes", [
    {"refused": True, "reason": "protected_attribute"},
    {"reason": "execution_error"}, {"reason": "clarification_required"},
])
def test_refusals_and_failed_queries_skip_external_summaries(monkeypatch, changes):
    client = install(monkeypatch, result(**changes))
    observed = runtime.answer("Question")
    assert client.calls == []
    assert "explanation" not in observed
    assert observed["generation"]["stages"]["summary"] == "local"


def test_verified_summary_does_not_change_numeric_answer_or_rows(monkeypatch):
    source = result()
    client = install(monkeypatch, source)
    observed = runtime.answer("How many open cases?")
    assert observed["answer"] == source["answer"]
    assert observed["rows"] == source["rows"]
    assert observed["sql_or_sources"] == source["sql_or_sources"]
    assert observed["explanation"] == "Verified evidence selection"
    assert observed["explanation_sources"] == ["sql-result:1"]
    assert client.calls[0]["sources"] == {"sql-result:1": "open cases: 42"}


@pytest.mark.parametrize("column", ["customer_id", "customer_name", "name", "case_id", "note_id", "current_balance", "phone"])
def test_aggregate_allowlist_blocks_any_individual_column(monkeypatch, column):
    source = result(rows=[{"open_cases": 42}, {"open_cases": 1, column: "private-value"}])
    client = install(monkeypatch, source)
    observed = runtime.answer("Question")
    assert client.calls == []
    assert "explanation" not in observed
    assert observed["rows"] == source["rows"]


def test_large_results_are_kept_local(monkeypatch):
    client = install(monkeypatch, result(rows=[{"open_cases": i} for i in range(11)]))
    runtime.answer("Question")
    assert client.calls == []


def test_provider_failure_preserves_local_result_and_marks_fallback(monkeypatch):
    source = result()
    install(monkeypatch, source, fail_summary=True)
    observed = runtime.answer("Question")
    assert observed["answer"] == source["answer"]
    assert observed["rows"] == source["rows"]
    assert observed["generation"]["stages"]["summary"] == "fallback"
    assert "explanation" not in observed


def brief():
    return {"summary": "Open cases: 2; overdue CAD 300. Financial evidence: Customer cannot pay. NOTE-001 contains sensitive narrative.", "recommendation_reason": "Hardship recorded on CS-2026-001. Note NOTE-001 and legacy-ref-2 require review.", "recommendation": "Review recorded hardship", "draft": "Please discuss options with a specialist.", "recorded_hardship_cases": ["CS-2026-001"], "features": {"note_id": "legacy-ref-2"}}


def test_brief_default_redacts_identifiers_excludes_note_text_and_preserves_decision(monkeypatch):
    source = brief()
    original = deepcopy(source)
    client = install(monkeypatch, result())
    observed = runtime.enrich_brief(source)
    assert len(client.calls) == 1
    outbound = str(client.calls[0]["sources"])
    for text in ("CS-2026-001", "NOTE-001", "legacy-ref-2", "Customer cannot pay", "Financial evidence:"):
        assert text not in outbound
    for key in ("recommendation", "recommendation_reason", "draft", "summary", "features", "recorded_hardship_cases"):
        assert observed[key] == original[key]
    assert observed["summary_evidence"] == "Verified evidence selection"
    assert "review-rule" in observed["summary_sources"]


def test_brief_source_identifiers_in_factual_summary_are_redacted(monkeypatch):
    source = brief()
    source["summary"] = "Open cases: 2; linked case CS-2026-001; source NOTE-001. Financial evidence: sensitive note."
    client = install(monkeypatch, result())
    runtime.enrich_brief(source)
    outbound = str(client.calls[0]["sources"])
    assert "CS-2026-001" not in outbound
    assert "NOTE-001" not in outbound


def test_transcript_text_requires_explicit_opt_in(monkeypatch):
    source = result(rows=[], sources=[{"transcript_id": "TR-001"}], answer="Customer says I cannot afford payment.")
    client = install(monkeypatch, source)
    runtime.answer("Summarize this call")
    assert client.calls == []
