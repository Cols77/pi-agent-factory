import json
import subprocess
import pytest
from factory.orchestrator.types import AgentRole, AgentResult
from factory.orchestrator.backends import FakeAgentBackend, FakeGateRunner
from factory.orchestrator.ledger import TaskNotFoundError, TaskNotTodoError, load_tasks
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
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
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
        AgentRole.SESSION_REVIEW: [AgentResult(True, {})],
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


def test_run_next_targets_specific_task_id(tmp_path):
    repo = _repo(tmp_path)
    (repo / "tasks" / "T-002.md").write_text(
        "---\nid: T-002\ntitle: second\nstatus: todo\ndod:\n  - c\n---\nbody\n", encoding="utf-8")
    path = run_next(repo, FakeAgentBackend(_scripts()), FakeGateRunner(),
                    session_id="s1", git_info={"branch": "main"}, task_id="T-002")
    assert path and path.exists()
    tasks = {t.id: t.status for t in load_tasks(repo / "tasks")}
    assert tasks["T-002"] == "done"
    assert tasks["T-001"] == "todo"  # untouched -- T-002 was targeted, not T-001


def test_run_next_raises_for_unknown_task_id(tmp_path):
    repo = _repo(tmp_path)
    with pytest.raises(TaskNotFoundError):
        run_next(repo, FakeAgentBackend({}), FakeGateRunner(), session_id="s1", task_id="T-999")


def test_run_next_raises_for_non_todo_task_id(tmp_path):
    repo = _repo(tmp_path)
    (repo / "tasks" / "T-001.md").write_text(
        "---\nid: T-001\ntitle: t\nstatus: done\ndod:\n  - c\n---\nbody\n", encoding="utf-8")
    with pytest.raises(TaskNotTodoError):
        run_next(repo, FakeAgentBackend({}), FakeGateRunner(), session_id="s1", task_id="T-001")


def test_review_kb_entries_selected_from_actual_changed_files_not_manifest(tmp_path):
    repo = _repo(tmp_path)

    # Seed a kb/ entry whose scope.files glob matches a file dev is scripted
    # to "change" -- but that file is NOT in the manifest's predicted
    # source_files (which only lists src/x.py). This is committed before
    # run_next runs, so it's part of the repo's start_commit state.
    (repo / "kb").mkdir()
    (repo / "kb" / "kb-0002-new-thing.md").write_text(
        "---\nid: kb-0002\ntitle: New thing needs a longer timeout\nstatus: active\n"
        "severity: low\ntags: []\nscope:\n  files:\n    - \"src/new_thing.py\"\n---\nbody\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "add kb entry"], cwd=repo, check=True)

    manifest = {
        "task_id": "T-001", "generated_by": "context-gatherer",
        "generated_at": "2026-07-16T14:32:10Z",
        "coherence": {"proven": True, "checks": [{"name": "x", "pass": True}]},
        "context": {"task": "tasks/T-001.md", "source_files": ["src/x.py"], "skills": []},
        "reject": None,
    }
    captured = {}

    class ScriptedBackend:
        def run(self, role, prompt, on_snippet=None, on_session_id=None):
            if on_session_id is not None:
                on_session_id("scripted-session-id")
            if role == AgentRole.CONTEXT_GATHERER:
                return AgentResult(True, manifest)
            if role == AgentRole.DEV:
                # Simulate dev actually changing a file that matches the KB
                # entry's scope glob but is absent from the manifest's
                # predicted source_files -- proving review's KB selection
                # must use the real diff, not the manifest.
                (repo / "src" / "new_thing.py").write_text("y = 2\n", encoding="utf-8")
                subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
                subprocess.run(["git", "commit", "-q", "-m", "dev change"], cwd=repo, check=True)
                return AgentResult(True, {})
            if role == AgentRole.REVIEW:
                captured["prompt"] = prompt
                return AgentResult(True, {"dod_met": True, "findings": []})
            if role == AgentRole.SESSION_REVIEW:
                return AgentResult(True, {})
            raise AssertionError(f"unexpected role {role}")

    run_next(repo, ScriptedBackend(), FakeGateRunner(), session_id="s1", git_info={"branch": "main"})

    assert "kb-0002" in captured["prompt"]
    assert "New thing needs a longer timeout" in captured["prompt"]
