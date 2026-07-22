import pytest
from pathlib import Path
from factory.orchestrator.types import AgentRole, AgentResult, NodeOutcome
from factory.orchestrator.ledger import Task
from factory.orchestrator.backends import FakeAgentBackend, FakeGateRunner
from factory.orchestrator.nodes import run_context_gatherer, run_dev
from factory.orchestrator.status import FakeStatusReporter
from ._skill_fixtures import write_skill_stubs

pytestmark = pytest.mark.unit


def _task():
    return Task("T-001", "t", "todo", ["c"], "body", Path("t"))


def _manifest(tmp_path, proven=True, reject=None):
    (tmp_path / "tasks").mkdir(exist_ok=True)
    (tmp_path / "tasks" / "T-001.md").write_text("dod", encoding="utf-8")
    return {
        "task_id": "T-001", "generated_by": "context-gatherer",
        "generated_at": "2026-07-16T14:32:10Z",
        "coherence": {"proven": proven, "checks": [{"name": "x", "pass": proven}]},
        "context": {"task": "tasks/T-001.md", "source_files": [], "skills": []},
        "reject": reject,
    }


def test_context_gatherer_pass(tmp_path):
    write_skill_stubs(tmp_path)
    b = FakeAgentBackend({AgentRole.CONTEXT_GATHERER: [AgentResult(True, _manifest(tmp_path))]})
    outcome, manifest, ev = run_context_gatherer(b, _task(), tmp_path)
    assert outcome == NodeOutcome.PASS and manifest is not None and ev.result == "pass"


def test_context_gatherer_reject_on_reject_field(tmp_path):
    write_skill_stubs(tmp_path)
    m = _manifest(tmp_path, proven=False, reject={"reason": "DoD unclear"})
    b = FakeAgentBackend({AgentRole.CONTEXT_GATHERER: [AgentResult(True, m)]})
    outcome, manifest, ev = run_context_gatherer(b, _task(), tmp_path)
    assert outcome == NodeOutcome.REJECT and manifest is None


def test_dev_passes_when_unit_green(tmp_path):
    write_skill_stubs(tmp_path)
    b = FakeAgentBackend({AgentRole.DEV: [AgentResult(True, {})]})
    g = FakeGateRunner({"unit": [0]})
    outcome, ev = run_dev(b, g, _task(), {}, [], tmp_path)
    assert outcome == NodeOutcome.PASS


def test_dev_escalates_when_unit_never_green(tmp_path):
    write_skill_stubs(tmp_path)
    b = FakeAgentBackend({AgentRole.DEV: [AgentResult(True, {}) for _ in range(3)]})
    g = FakeGateRunner({"unit": [1, 1, 1]})
    outcome, ev = run_dev(b, g, _task(), {}, [], tmp_path, max_iters=3)
    assert outcome == NodeOutcome.ESCALATE and ev.attempts == 3


def test_context_gatherer_notes_backend_failure(tmp_path):
    write_skill_stubs(tmp_path)
    b = FakeAgentBackend({AgentRole.CONTEXT_GATHERER: [
        AgentResult(False, {}, "simulated backend failure"),
        AgentResult(False, {}, "simulated backend failure"),
    ]})
    outcome, manifest, ev = run_context_gatherer(b, _task(), tmp_path)
    assert outcome == NodeOutcome.REJECT and manifest is None
    assert ev.extra["backend_ok"] is False
    assert ev.extra["backend_raw"] == "simulated backend failure"


def test_dev_notes_backend_failure_on_escalate(tmp_path):
    write_skill_stubs(tmp_path)
    b = FakeAgentBackend({AgentRole.DEV: [
        AgentResult(False, {}, "simulated backend failure") for _ in range(3)
    ]})
    g = FakeGateRunner({"unit": [1, 1, 1]})
    outcome, ev = run_dev(b, g, _task(), {}, [], tmp_path, max_iters=3)
    assert outcome == NodeOutcome.ESCALATE
    assert ev.extra["backend_ok"] is False
    assert ev.extra["backend_raw"] == "simulated backend failure"


def test_dev_does_not_note_backend_failure_when_ok(tmp_path):
    write_skill_stubs(tmp_path)
    b = FakeAgentBackend({AgentRole.DEV: [AgentResult(True, {})]})
    g = FakeGateRunner({"unit": [0]})
    outcome, ev = run_dev(b, g, _task(), {}, [], tmp_path)
    assert outcome == NodeOutcome.PASS
    assert "backend_ok" not in ev.extra


def test_context_gatherer_reports_running_each_attempt(tmp_path):
    write_skill_stubs(tmp_path)
    status = FakeStatusReporter()
    b = FakeAgentBackend({AgentRole.CONTEXT_GATHERER: [AgentResult(True, _manifest(tmp_path))]})
    run_context_gatherer(b, _task(), tmp_path, status=status)
    assert status.calls[0]["node"] == "context-gather"
    assert status.calls[0]["node_state"] == "running"
    assert status.calls[0]["attempt"] == 1
    assert status.calls[0]["max_attempts"] == 2


def test_dev_reports_running_each_attempt_and_passes_on_snippet(tmp_path):
    write_skill_stubs(tmp_path)
    status = FakeStatusReporter()

    class SnippetCapturingBackend:
        def run(self, role, prompt, on_snippet=None):
            if on_snippet is not None:
                on_snippet("partial output")
            return AgentResult(True, {})

    b = SnippetCapturingBackend()
    g = FakeGateRunner({"unit": [0]})
    run_dev(b, g, _task(), {}, [], tmp_path, status=status)
    assert status.calls[0]["node"] == "dev"
    assert status.calls[0]["node_state"] == "running"
    snippets = [c["snippet"] for c in status.calls if c["snippet"]]
    assert snippets == ["partial output"]


def test_run_context_gatherer_writes_transcript_when_dir_given(tmp_path):
    write_skill_stubs(tmp_path)
    b = FakeAgentBackend({
        AgentRole.CONTEXT_GATHERER: [AgentResult(True, _manifest(tmp_path), "raw gather output")]
    })
    transcript_dir = tmp_path / "transcripts"
    run_context_gatherer(b, _task(), tmp_path, transcript_dir=transcript_dir)
    assert (transcript_dir / "context-gather-attempt1.log").read_text(encoding="utf-8") == "raw gather output"


def test_run_context_gatherer_no_transcript_when_dir_not_given(tmp_path):
    write_skill_stubs(tmp_path)
    b = FakeAgentBackend({
        AgentRole.CONTEXT_GATHERER: [AgentResult(True, _manifest(tmp_path), "raw gather output")]
    })
    run_context_gatherer(b, _task(), tmp_path)
    assert not (tmp_path / "transcripts").exists()
    assert not list(tmp_path.rglob("*-attempt*.log"))


def test_run_dev_writes_one_transcript_per_attempt(tmp_path):
    write_skill_stubs(tmp_path)
    b = FakeAgentBackend({AgentRole.DEV: [
        AgentResult(True, {}, "dev attempt 1 raw"),
        AgentResult(True, {}, "dev attempt 2 raw"),
    ]})
    g = FakeGateRunner({"unit": [1, 0]})
    transcript_dir = tmp_path / "transcripts"
    outcome, ev = run_dev(b, g, _task(), {}, [], tmp_path, transcript_dir=transcript_dir)
    assert outcome == NodeOutcome.PASS
    assert ev.attempts == 2
    assert (transcript_dir / "dev-attempt1.log").read_text(encoding="utf-8") == "dev attempt 1 raw"
    assert (transcript_dir / "dev-attempt2.log").read_text(encoding="utf-8") == "dev attempt 2 raw"
