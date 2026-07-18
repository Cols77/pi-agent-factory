import pytest
from factory.orchestrator.types import AgentRole, AgentResult
from factory.orchestrator.ledger import Task
from factory.orchestrator.backends import FakeAgentBackend, FakeGateRunner
from factory.orchestrator.runner import run_task

pytestmark = pytest.mark.unit


def _repo(tmp_path):
    (tmp_path / "tasks").mkdir()
    (tmp_path / "tasks" / "T-001.md").write_text("dod", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "x.py").write_text("x = 1\n", encoding="utf-8")
    return tmp_path


def _manifest():
    return {
        "task_id": "T-001", "generated_by": "context-gatherer",
        "generated_at": "2026-07-16T14:32:10Z",
        "coherence": {"proven": True, "checks": [{"name": "x", "pass": True}]},
        "context": {"task": "tasks/T-001.md", "source_files": ["src/x.py"], "skills": []},
        "reject": None,
    }


def _scripts():
    # review: changes once, then pass -> exercises the dev<->review loop
    return {
        AgentRole.CONTEXT_GATHERER: [AgentResult(True, _manifest())],
        AgentRole.DEV: [AgentResult(True, {}), AgentResult(True, {})],
        AgentRole.REVIEW: [
            AgentResult(True, {"dod_met": False, "findings": ["fix"]}),
            AgentResult(True, {"dod_met": True, "findings": []}),
        ],
    }


def test_full_pipeline_completes_and_is_deterministic(tmp_path):
    repo = _repo(tmp_path)
    task = Task("T-001", "t", "todo", ["c"], "body", repo / "tasks" / "T-001.md")

    def run():
        return run_task(task, FakeAgentBackend(_scripts()), FakeGateRunner(), repo,
                        max_review_cycles=3)

    r1 = run()
    r2 = run()
    assert r1.outcome == "completed" and r1.dod_met is True
    assert r1.iterations == 2
    seq1 = [(e.node, e.result) for e in r1.events]
    seq2 = [(e.node, e.result) for e in r2.events]
    assert seq1 == seq2  # deterministic routing
    assert ("review", "pass") in seq1


def test_context_reject_short_circuits(tmp_path):
    repo = _repo(tmp_path)
    task = Task("T-001", "t", "todo", ["c"], "body", repo / "tasks" / "T-001.md")
    scripts = {AgentRole.CONTEXT_GATHERER: [AgentResult(True, {**_manifest(), "reject": {"reason": "x"},
                                                              "coherence": {"proven": False, "checks": []}})]}
    r = run_task(task, FakeAgentBackend(scripts), FakeGateRunner(), repo)
    assert r.outcome == "rejected"
