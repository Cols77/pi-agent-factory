import pytest
from pathlib import Path
from factory.orchestrator.types import AgentRole, AgentResult, NodeOutcome
from factory.orchestrator.ledger import Task
from factory.orchestrator.backends import FakeAgentBackend, FakeGateRunner
from factory.orchestrator.nodes import run_validation, run_review, _summarize_review
from factory.orchestrator.status import FakeStatusReporter
from ._skill_fixtures import write_skill_stubs

pytestmark = pytest.mark.unit


def _task():
    return Task("T-001", "t", "todo", ["c"], "body", Path("t"))


def test_validation_pass_and_fail():
    assert run_validation(FakeGateRunner({"sim": [0]}))[0] == NodeOutcome.PASS
    assert run_validation(FakeGateRunner({"sim": [1]}))[0] == NodeOutcome.FAIL


def test_review_pass_requires_green_gate_and_dod_and_no_findings(tmp_path):
    write_skill_stubs(tmp_path)
    b = FakeAgentBackend({AgentRole.REVIEW: [AgentResult(True, {"dod_met": True, "findings": []})]})
    outcome, ev, findings = run_review(b, FakeGateRunner({"full": [0]}), _task(), [], tmp_path)
    assert outcome == NodeOutcome.PASS and findings == []


def test_review_changes_when_findings_present(tmp_path):
    write_skill_stubs(tmp_path)
    b = FakeAgentBackend({AgentRole.REVIEW: [AgentResult(True, {"dod_met": True, "findings": ["DRY: dup"]})]})
    outcome, ev, findings = run_review(b, FakeGateRunner({"full": [0]}), _task(), [], tmp_path)
    assert outcome == NodeOutcome.CHANGES and findings == ["DRY: dup"]


def test_review_changes_when_gate_red_even_if_dod_claimed(tmp_path):
    write_skill_stubs(tmp_path)
    b = FakeAgentBackend({AgentRole.REVIEW: [AgentResult(True, {"dod_met": True, "findings": []})]})
    outcome, ev, findings = run_review(b, FakeGateRunner({"full": [1]}), _task(), [], tmp_path)
    assert outcome == NodeOutcome.CHANGES  # cannot self-certify past a red gate


def test_review_notes_backend_failure(tmp_path):
    write_skill_stubs(tmp_path)
    b = FakeAgentBackend({AgentRole.REVIEW: [AgentResult(False, {}, "simulated backend failure")]})
    outcome, ev, findings = run_review(b, FakeGateRunner({"full": [0]}), _task(), [], tmp_path)
    assert outcome == NodeOutcome.CHANGES
    assert ev.extra["backend_ok"] is False
    assert ev.extra["backend_raw"] == "simulated backend failure"


def test_review_does_not_note_backend_failure_when_ok(tmp_path):
    write_skill_stubs(tmp_path)
    b = FakeAgentBackend({AgentRole.REVIEW: [AgentResult(True, {"dod_met": True, "findings": []})]})
    outcome, ev, findings = run_review(b, FakeGateRunner({"full": [0]}), _task(), [], tmp_path)
    assert outcome == NodeOutcome.PASS
    assert "backend_ok" not in ev.extra


def test_validation_reports_running():
    status = FakeStatusReporter()
    run_validation(FakeGateRunner({"sim": [0]}), "T-001", status=status)
    assert status.calls[0]["node"] == "validation"
    assert status.calls[0]["node_state"] == "running"
    assert status.calls[0]["task_id"] == "T-001"


def test_review_reports_running(tmp_path):
    write_skill_stubs(tmp_path)
    status = FakeStatusReporter()
    b = FakeAgentBackend({AgentRole.REVIEW: [AgentResult(True, {"dod_met": True, "findings": []})]})
    run_review(b, FakeGateRunner({"full": [0]}), _task(), [], tmp_path, status=status)
    assert status.calls[0]["node"] == "review"
    assert status.calls[0]["node_state"] == "running"


def test_run_review_no_longer_accepts_manifest():
    import inspect

    sig = inspect.signature(run_review)
    assert "manifest" not in sig.parameters
    assert "kb_entries" in sig.parameters


def test_run_review_prompt_includes_kb_entries_not_manifest(tmp_path):
    write_skill_stubs(tmp_path)
    captured = {}

    class PromptCapturingBackend:
        def run(self, role, prompt, on_snippet=None, on_session_id=None):
            captured["prompt"] = prompt
            return AgentResult(True, {"dod_met": True, "findings": []})

    kb_entries = [{"id": "KB-001", "title": "Known flaky gate"}]
    run_review(PromptCapturingBackend(), FakeGateRunner({"full": [0]}), _task(), kb_entries, tmp_path)
    assert "KB-001" in captured["prompt"]
    assert "Known flaky gate" in captured["prompt"]
    assert "## Context (from manifest)" not in captured["prompt"]


def test_run_review_writes_transcript_when_dir_given(tmp_path):
    write_skill_stubs(tmp_path)
    b = FakeAgentBackend({
        AgentRole.REVIEW: [AgentResult(True, {"dod_met": True, "findings": []}, "review raw output")]
    })
    transcript_dir = tmp_path / "transcripts"
    run_review(b, FakeGateRunner({"full": [0]}), _task(), [], tmp_path, transcript_dir=transcript_dir)
    assert (transcript_dir / "review-attempt1.log").read_text(encoding="utf-8") == "review raw output"


def test_summarize_review_empty_findings():
    assert _summarize_review([]) == "DoD not met"


def test_summarize_review_lists_findings():
    result = _summarize_review(["fix error handling", "extract magic number"])
    assert "fix error handling" in result
    assert "extract magic number" in result
    assert result.startswith("requested: ")


def test_review_pass_reports_session_id_and_summary(tmp_path):
    write_skill_stubs(tmp_path)
    status = FakeStatusReporter()
    b = FakeAgentBackend({
        AgentRole.REVIEW: [AgentResult(True, {"dod_met": True, "findings": []}, "raw", "sess-rev-1")]
    })
    run_review(b, FakeGateRunner({"full": [0]}), _task(), [], tmp_path, status=status)
    pass_call = status.calls[-1]
    assert pass_call["node_state"] == "pass"
    assert pass_call["session_id"] == "sess-rev-1"
    assert pass_call["summary"] == "DoD met; gates pass"


def test_review_changes_requested_reports_session_id_and_summary(tmp_path):
    write_skill_stubs(tmp_path)
    status = FakeStatusReporter()
    findings = ["fix error handling", "extract magic number"]
    b = FakeAgentBackend({
        AgentRole.REVIEW: [AgentResult(True, {"dod_met": True, "findings": findings}, "raw", "sess-rev-2")]
    })
    run_review(b, FakeGateRunner({"full": [0]}), _task(), [], tmp_path, status=status)
    changes_call = status.calls[-1]
    assert changes_call["node_state"] == "changes-requested"
    assert changes_call["session_id"] == "sess-rev-2"
    assert changes_call["summary"] == _summarize_review(findings)


def test_run_review_carries_confidence_and_verify_in_event(tmp_path):
    write_skill_stubs(tmp_path)
    review_out = {
        "dod_met": True, "findings": [],
        "confidence": "medium -- edges thin",
        "verify": [{"item": "advance past last waypoint", "file": "src/x.py", "line": 44}],
    }
    b = FakeAgentBackend({AgentRole.REVIEW: [AgentResult(True, review_out)]})
    _outcome, ev, _findings = run_review(b, FakeGateRunner({"full": [0]}), _task(), [], tmp_path)
    assert ev.extra["confidence"] == "medium -- edges thin"
    assert ev.extra["verify"] == [{"item": "advance past last waypoint", "file": "src/x.py", "line": 44}]


def test_review_prompt_reports_that_validation_already_ran(tmp_path):
    # run_validation executes the sim/integration gates deterministically BEFORE
    # run_review (runner.py). Without being told, the review agent cannot know the
    # suites are already green and asks the human to run them again.
    from factory.orchestrator.types import NodeEvent

    write_skill_stubs(tmp_path)
    b = FakeAgentBackend({AgentRole.REVIEW: [AgentResult(True, {"dod_met": True, "findings": []})]})
    events = [NodeEvent("dev", "pass"), NodeEvent("validation", "pass")]

    run_review(b, FakeGateRunner({"full": [0]}), _task(), [], tmp_path, events=events)

    prompt = b.prompts[0][1]
    assert "validation: pass" in prompt
