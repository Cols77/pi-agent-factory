from __future__ import annotations

import subprocess

import pytest

from factory.evidence.artifacts import LocalArtifactStore
from factory.evidence.manifests import load_run_manifest
from factory.orchestrator.backends import FakeAgentBackend, FakeGateRunner
from factory.orchestrator.runner import run_next
from factory.orchestrator.types import AgentResult, AgentRole, NodeEvent, TaskResult

pytestmark = pytest.mark.unit


def _repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    (repo / "tasks").mkdir()
    (repo / "tasks" / "T-001-example.md").write_text(
        "---\nid: T-001\ntitle: Example\nstatus: todo\ndod:\n  - works\n---\nbody\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=repo, check=True)
    return repo


def _head(repo):
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()


def test_run_next_writes_manifest_and_separate_exact_path_evidence_commit(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    code_commit = _head(repo)
    transcript = repo / "sessions" / ".factory-transcripts" / "run-1"
    transcript.mkdir(parents=True)
    backend = FakeAgentBackend(
        {AgentRole.SESSION_REVIEW: [AgentResult(True, {}, raw="session complete")]}
    )

    def fake_run_task(*args, **kwargs):
        return TaskResult(
            "T-001", "Example", "completed", 1, [NodeEvent("dev", "pass")], True
        )

    monkeypatch.setattr("factory.orchestrator.runner.run_task", fake_run_task)
    monkeypatch.setattr("factory.orchestrator.runner.compose_prompt", lambda *a, **k: "prompt")

    session_path = run_next(
        repo,
        backend,
        FakeGateRunner(),
        session_id="run-1",
        task_id="T-001",
        transcript_dir=transcript,
        artifact_store=LocalArtifactStore(repo / ".factory" / "artifacts" / "objects"),
        evidence_dir=repo / "evidence",
    )

    assert session_path is not None
    manifest = load_run_manifest(repo / "evidence" / "runs" / "run-1.json")
    assert manifest["start_commit"] == code_commit
    assert manifest["result_commit"] == code_commit
    assert manifest["outcome"] == "completed"
    assert _head(repo) != code_commit
    committed = subprocess.run(
        ["git", "show", "--name-only", "--format=", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    assert committed == ["evidence/runs/run-1.json", "tasks/T-001-example.md"]


def test_run_next_requires_store_and_evidence_dir_together(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    backend = FakeAgentBackend({})
    monkeypatch.setattr(
        "factory.orchestrator.runner.run_task",
        lambda *a, **k: TaskResult("T-001", "Example", "completed", 1, [], True),
    )

    with pytest.raises(ValueError, match="configured together"):
        run_next(
            repo,
            backend,
            FakeGateRunner(),
            session_id="run-1",
            task_id="T-001",
            artifact_store=LocalArtifactStore(repo / ".factory" / "artifacts" / "objects"),
        )
