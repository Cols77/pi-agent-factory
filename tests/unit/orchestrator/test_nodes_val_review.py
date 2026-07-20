import pytest
from pathlib import Path
from factory.orchestrator.types import AgentRole, AgentResult, NodeOutcome
from factory.orchestrator.ledger import Task
from factory.orchestrator.backends import FakeAgentBackend, FakeGateRunner
from factory.orchestrator.nodes import run_validation, run_review
from factory.orchestrator.status import FakeStatusReporter

pytestmark = pytest.mark.unit


def _task():
    return Task("T-001", "t", "todo", ["c"], "body", Path("t"))


def test_validation_pass_and_fail():
    assert run_validation(FakeGateRunner({"sim": [0]}))[0] == NodeOutcome.PASS
    assert run_validation(FakeGateRunner({"sim": [1]}))[0] == NodeOutcome.FAIL


def test_review_pass_requires_green_gate_and_dod_and_no_findings():
    b = FakeAgentBackend({AgentRole.REVIEW: [AgentResult(True, {"dod_met": True, "findings": []})]})
    outcome, ev, findings = run_review(b, FakeGateRunner({"full": [0]}), _task())
    assert outcome == NodeOutcome.PASS and findings == []


def test_review_changes_when_findings_present():
    b = FakeAgentBackend({AgentRole.REVIEW: [AgentResult(True, {"dod_met": True, "findings": ["DRY: dup"]})]})
    outcome, ev, findings = run_review(b, FakeGateRunner({"full": [0]}), _task())
    assert outcome == NodeOutcome.CHANGES and findings == ["DRY: dup"]


def test_review_changes_when_gate_red_even_if_dod_claimed():
    b = FakeAgentBackend({AgentRole.REVIEW: [AgentResult(True, {"dod_met": True, "findings": []})]})
    outcome, ev, findings = run_review(b, FakeGateRunner({"full": [1]}), _task())
    assert outcome == NodeOutcome.CHANGES  # cannot self-certify past a red gate


def test_review_notes_backend_failure():
    b = FakeAgentBackend({AgentRole.REVIEW: [AgentResult(False, {}, "simulated backend failure")]})
    outcome, ev, findings = run_review(b, FakeGateRunner({"full": [0]}), _task())
    assert outcome == NodeOutcome.CHANGES
    assert ev.extra["backend_ok"] is False
    assert ev.extra["backend_raw"] == "simulated backend failure"


def test_review_does_not_note_backend_failure_when_ok():
    b = FakeAgentBackend({AgentRole.REVIEW: [AgentResult(True, {"dod_met": True, "findings": []})]})
    outcome, ev, findings = run_review(b, FakeGateRunner({"full": [0]}), _task())
    assert outcome == NodeOutcome.PASS
    assert "backend_ok" not in ev.extra


def test_validation_reports_running():
    status = FakeStatusReporter()
    run_validation(FakeGateRunner({"sim": [0]}), "T-001", status=status)
    assert status.calls[0]["node"] == "validation"
    assert status.calls[0]["node_state"] == "running"
    assert status.calls[0]["task_id"] == "T-001"


def test_review_reports_running():
    status = FakeStatusReporter()
    b = FakeAgentBackend({AgentRole.REVIEW: [AgentResult(True, {"dod_met": True, "findings": []})]})
    run_review(b, FakeGateRunner({"full": [0]}), _task(), status=status)
    assert status.calls[0]["node"] == "review"
    assert status.calls[0]["node_state"] == "running"
