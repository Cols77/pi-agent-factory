import json
import pytest
from factory.orchestrator.types import AgentRole, AgentResult
from factory.orchestrator.backends import FakeAgentBackend, FakeGateRunner
from factory.orchestrator.ledger import load_tasks
from factory.orchestrator.runner import run_next
from factory.orchestrator.status import FakeStatusReporter
from ._skill_fixtures import write_skill_stubs

pytestmark = pytest.mark.unit


def _repo(tmp_path):
    (tmp_path / "tasks").mkdir()
    (tmp_path / "tasks" / "T-001.md").write_text(
        "---\nid: T-001\ntitle: t\nstatus: todo\ndod:\n  - c\n---\nbody\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "x.py").write_text("x = 1\n", encoding="utf-8")
    write_skill_stubs(tmp_path)
    return tmp_path


def _scripts():
    manifest = {
        "task_id": "T-001", "generated_by": "context-gatherer",
        "generated_at": "2026-07-16T14:32:10Z",
        "coherence": {"proven": True, "checks": [{"name": "x", "pass": True}]},
        "context": {"task": "tasks/T-001.md", "source_files": ["src/x.py"], "skills": []},
        "reject": None,
    }
    return {
        AgentRole.CONTEXT_GATHERER: [AgentResult(True, manifest)],
        AgentRole.DEV: [AgentResult(True, {})],
        AgentRole.REVIEW: [AgentResult(True, {"dod_met": True, "findings": []})],
    }


def test_run_next_writes_session_and_marks_done(tmp_path):
    repo = _repo(tmp_path)
    path = run_next(repo, FakeAgentBackend(_scripts()), FakeGateRunner(),
                    session_id="s1", git_info={"branch": "main"})
    assert path and path.exists()
    assert json.loads(path.read_text(encoding="utf-8"))["tasks"][0]["outcome"] == "completed"
    assert load_tasks(repo / "tasks")[0].status == "done"


def test_run_next_none_when_no_todo(tmp_path):
    (tmp_path / "tasks").mkdir()
    assert run_next(tmp_path, FakeAgentBackend({}), FakeGateRunner(), session_id="s1") is None


def test_run_next_passes_status_through_to_run_task(tmp_path):
    repo = _repo(tmp_path)
    status = FakeStatusReporter()
    run_next(repo, FakeAgentBackend(_scripts()), FakeGateRunner(),
              session_id="s1", git_info={"branch": "main"}, status=status)
    assert len(status.calls) > 0
