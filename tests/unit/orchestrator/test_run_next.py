import json
import subprocess
import pytest
from factory.orchestrator.types import AgentRole, AgentResult
from factory.orchestrator.backends import FakeAgentBackend, FakeGateRunner
from factory.orchestrator.git_ops import FakeGitOps
from factory.orchestrator.ledger import TaskNotFoundError, TaskNotTodoError, load_tasks
from factory.orchestrator.runner import run_next
from factory.orchestrator.status import FakeStatusReporter
from ._repo_fixtures import copy_repo_seed, write_repo_template

def _repo(tmp_path):
    return write_repo_template(tmp_path, "run_next")


def _git_repo(tmp_path):
    return copy_repo_seed(tmp_path, "run_next")


def _scripts(task_id="T-001"):
    manifest = {
        "task_id": task_id, "generated_by": "context-gatherer",
        "generated_at": "2026-07-16T14:32:10Z",
        "coherence": {"checks": [{"name": "c", "kind": "files_exist", "args": {"paths": ["src/x.py"]}}]},
        "context": {"task": f"tasks/{task_id}.md", "source_files": ["src/x.py"], "skills": []},
        "reject": None,
    }
    return {
        AgentRole.CONTEXT_GATHERER: [AgentResult(True, manifest)],
        AgentRole.DEV: [AgentResult(True, {})],
        AgentRole.REVIEW: [AgentResult(True, {"dod_met": True, "findings": []})],
        AgentRole.SESSION_REVIEW: [AgentResult(True, {})],
    }


@pytest.mark.unit
def test_run_next_writes_session_and_marks_done(tmp_path):
    repo = _repo(tmp_path)
    path = run_next(repo, FakeAgentBackend(_scripts()), FakeGateRunner(),
                    session_id="s1", git_info={"branch": "main"}, git_ops=FakeGitOps())
    assert path and path.exists()
    assert json.loads(path.read_text(encoding="utf-8"))["tasks"][0]["outcome"] == "completed"
    assert load_tasks(repo / "tasks")[0].status == "done"


@pytest.mark.unit
def test_run_next_none_when_no_todo(tmp_path):
    (tmp_path / "tasks").mkdir()
    assert run_next(
        tmp_path, FakeAgentBackend({}), FakeGateRunner(), session_id="s1", git_ops=FakeGitOps()
    ) is None


@pytest.mark.unit
def test_run_next_passes_status_through_to_run_task(tmp_path):
    repo = _repo(tmp_path)
    status = FakeStatusReporter()
    run_next(repo, FakeAgentBackend(_scripts()), FakeGateRunner(),
              session_id="s1", git_info={"branch": "main"}, status=status, git_ops=FakeGitOps())
    assert len(status.calls) > 0


@pytest.mark.unit
def test_run_next_targets_specific_task_id(tmp_path):
    repo = _repo(tmp_path)
    (repo / "tasks" / "T-002.md").write_text(
        "---\nid: T-002\ntitle: second\nstatus: todo\ndod:\n  - c\n---\nbody\n", encoding="utf-8")
    path = run_next(repo, FakeAgentBackend(_scripts(task_id="T-002")), FakeGateRunner(),
                    session_id="s1", git_info={"branch": "main"}, task_id="T-002",
                    git_ops=FakeGitOps())
    assert path and path.exists()
    tasks = {t.id: t.status for t in load_tasks(repo / "tasks")}
    assert tasks["T-002"] == "done"
    assert tasks["T-001"] == "todo"  # untouched -- T-002 was targeted, not T-001


@pytest.mark.unit
def test_run_next_raises_for_unknown_task_id(tmp_path):
    repo = _repo(tmp_path)
    with pytest.raises(TaskNotFoundError):
        run_next(
            repo, FakeAgentBackend({}), FakeGateRunner(), session_id="s1", task_id="T-999",
            git_ops=FakeGitOps(),
        )


@pytest.mark.unit
def test_run_next_raises_for_non_todo_task_id(tmp_path):
    repo = _repo(tmp_path)
    (repo / "tasks" / "T-001.md").write_text(
        "---\nid: T-001\ntitle: t\nstatus: done\ndod:\n  - c\n---\nbody\n", encoding="utf-8")
    with pytest.raises(TaskNotTodoError):
        run_next(
            repo, FakeAgentBackend({}), FakeGateRunner(), session_id="s1", task_id="T-001",
            git_ops=FakeGitOps(),
        )


@pytest.mark.unit
def test_run_next_force_reruns_a_non_todo_task(tmp_path):
    # After manual intervention a task can be left `done`/`in-progress`; force
    # lets the pipeline be re-triggered on it instead of dead-ending with
    # TaskNotTodoError (RC3).
    repo = _repo(tmp_path)
    (repo / "tasks" / "T-001.md").write_text(
        "---\nid: T-001\ntitle: t\nstatus: done\ndod:\n  - c\n---\nbody\n", encoding="utf-8")
    path = run_next(repo, FakeAgentBackend(_scripts()), FakeGateRunner(),
                    session_id="s1", git_info={"branch": "main"}, task_id="T-001", force=True,
                    git_ops=FakeGitOps())
    assert path and path.exists()
    assert load_tasks(repo / "tasks")[0].status == "done"


@pytest.mark.integration
def test_review_kb_entries_selected_from_actual_changed_files_not_manifest(tmp_path):
    repo = _git_repo(tmp_path)

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
        "coherence": {"checks": [{"name": "c", "kind": "files_exist", "args": {"paths": ["src/x.py"]}}]},
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


@pytest.mark.unit
def test_auto_pick_selects_todo_task_even_if_deliverables_exist(tmp_path):
    # A todo task whose Create: deliverable already exists on disk must still be
    # auto-picked and run -- file presence alone doesn't prove the task is done
    # (e.g. it may have stopped at dev-fail with files already committed).
    # Genuinely-done work is instead handled at run time by the context-
    # gatherer's already-done routing.
    repo = _repo(tmp_path)
    # T-001's body declares Create: src/x.py, which _repo already created on disk.
    (repo / "tasks" / "T-001.md").write_text(
        "---\nid: T-001\ntitle: t\nstatus: todo\ndod:\n  - c\n---\n- Create: `src/x.py`\n",
        encoding="utf-8")
    backend = FakeAgentBackend(_scripts())
    result = run_next(repo, backend, FakeGateRunner(), session_id="s1", git_ops=FakeGitOps())
    # It must run the task (not return None / "no todo tasks") despite src/x.py existing.
    assert result is not None
