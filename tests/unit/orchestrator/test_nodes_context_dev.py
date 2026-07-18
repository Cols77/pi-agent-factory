import pytest
from pathlib import Path
from factory.orchestrator.types import AgentRole, AgentResult, NodeOutcome
from factory.orchestrator.ledger import Task
from factory.orchestrator.backends import FakeAgentBackend, FakeGateRunner
from factory.orchestrator.nodes import run_context_gatherer, run_dev

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
    b = FakeAgentBackend({AgentRole.CONTEXT_GATHERER: [AgentResult(True, _manifest(tmp_path))]})
    outcome, manifest, ev = run_context_gatherer(b, _task(), tmp_path)
    assert outcome == NodeOutcome.PASS and manifest is not None and ev.result == "pass"


def test_context_gatherer_reject_on_reject_field(tmp_path):
    m = _manifest(tmp_path, proven=False, reject={"reason": "DoD unclear"})
    b = FakeAgentBackend({AgentRole.CONTEXT_GATHERER: [AgentResult(True, m)]})
    outcome, manifest, ev = run_context_gatherer(b, _task(), tmp_path)
    assert outcome == NodeOutcome.REJECT and manifest is None


def test_dev_passes_when_unit_green():
    b = FakeAgentBackend({AgentRole.DEV: [AgentResult(True, {})]})
    g = FakeGateRunner({"unit": [0]})
    outcome, ev = run_dev(b, g, _task(), {}, [])
    assert outcome == NodeOutcome.PASS


def test_dev_escalates_when_unit_never_green():
    b = FakeAgentBackend({AgentRole.DEV: [AgentResult(True, {}) for _ in range(3)]})
    g = FakeGateRunner({"unit": [1, 1, 1]})
    outcome, ev = run_dev(b, g, _task(), {}, [], max_iters=3)
    assert outcome == NodeOutcome.ESCALATE and ev.attempts == 3
