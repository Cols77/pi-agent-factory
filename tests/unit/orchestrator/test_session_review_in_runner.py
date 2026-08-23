from __future__ import annotations

import json
import subprocess
import pytest
from factory.orchestrator.backends import FakeAgentBackend, FakeGateRunner
from factory.orchestrator.nodes import run_session_review
from factory.orchestrator.ledger import Task
from factory.orchestrator.runner import run_next
from factory.orchestrator.types import AgentRole, AgentResult, NodeEvent
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
        "coherence": {"checks": [{"name": "c", "kind": "files_exist", "args": {"paths": ["src/x.py"]}}]},
        "context": {"task": "tasks/T-001.md", "source_files": ["src/x.py"], "skills": []},
        "reject": None,
    }
    return {
        AgentRole.CONTEXT_GATHERER: [AgentResult(True, manifest)],
        AgentRole.DEV: [AgentResult(True, {})],
        AgentRole.REVIEW: [AgentResult(True, {"dod_met": True, "findings": []})],
    }


class CapturingBackend:
    """Scripted backend that also records the prompt sent for each role, so
    tests can assert on session-review's composed prompt content rather than
    just the absence of a FakeAgentBackend assertion error."""

    def __init__(self, scripts: dict) -> None:
        self._scripts = {k: list(v) for k, v in scripts.items()}
        self.prompts: dict = {}

    def run(self, role, prompt, on_snippet=None, on_session_id=None):
        self.prompts[role] = prompt
        queue = self._scripts.get(role)
        assert queue, f"CapturingBackend: no scripted result for {role}"
        return queue.pop(0)


def test_session_review_invoked_at_end_of_run_next_with_events_and_kb_titles(tmp_path):
    repo = _repo(tmp_path)
    scripts = _scripts()
    scripts[AgentRole.SESSION_REVIEW] = [AgentResult(True, {})]
    backend = CapturingBackend(scripts)

    run_next(repo, backend, FakeGateRunner(), session_id="s1", git_info={"branch": "main"})

    # FakeAgentBackend-style assertion failure would already have fired if
    # SESSION_REVIEW's scripted queue were never consumed -- but the prompt
    # capture gives a stronger, positive assertion of both invocation and
    # the expected content compose_prompt's events/existing_kb_titles wiring
    # produces.
    assert AgentRole.SESSION_REVIEW in backend.prompts
    assert "## What happened this run" in backend.prompts[AgentRole.SESSION_REVIEW]
    assert "Final outcome: completed" in backend.prompts[AgentRole.SESSION_REVIEW]


def test_run_session_review_persists_structured_outcome_artifact(tmp_path):
    task = Task("T-001", "Session review", "todo", ["tests green"], "body", tmp_path / "task.md")
    outcome = {
        "suggestions": [
            {
                "target": "gate",
                "summary": "gate uses wrong interpreter",
                "proposed": "replace {python} with uv run python",
                "evidence": "collection-stage ModuleNotFoundError",
            }
        ],
        "kb_added": ["kb/kb-0004-x.md"],
    }
    backend = FakeAgentBackend(
        {AgentRole.SESSION_REVIEW: [AgentResult(True, outcome, session_id="sr-1")]}
    )
    run_session_review(
        backend,
        task,
        tmp_path,
        final_outcome="completed",
        events=[NodeEvent("context-gather", "pass")],
        run_id="0",
    )
    artifact = tmp_path / "sessions" / ".factory-runs" / "by-session" / "0" / "session-review.json"
    assert artifact.exists()
    data = json.loads(artifact.read_text(encoding="utf-8"))
    assert data["run_id"] == "0"
    assert data["task_id"] == "T-001"
    assert data["final_outcome"] == "completed"
    assert data["agent_session_id"] == "sr-1"
    assert data["ok"] is True
    assert data["suggestions"][0]["target"] == "gate"
    assert data["kb_added"] == ["kb/kb-0004-x.md"]
    assert data["summary_path"] == "sessions/0.session.json"


def test_run_session_review_without_run_id_skips_artifact(tmp_path):
    task = Task("T-001", "Session review", "todo", ["tests green"], "body", tmp_path / "task.md")
    backend = FakeAgentBackend(
        {AgentRole.SESSION_REVIEW: [AgentResult(True, {"suggestions": []})]}
    )
    run_session_review(
        backend,
        task,
        tmp_path,
        final_outcome="completed",
        events=[NodeEvent("context-gather", "pass")],
    )
    artifact = tmp_path / "sessions" / ".factory-runs" / "by-session"
    assert not (artifact / "session-review.json").exists()
