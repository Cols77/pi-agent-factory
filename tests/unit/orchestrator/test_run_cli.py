from __future__ import annotations

import json

import pytest

from factory.orchestrator.git_ops import FakeGitOps
from factory.orchestrator.journal import RunCheckpoint, RunJournal
from factory.orchestrator.run_cli import load_current_checkpoint, main

pytestmark = pytest.mark.unit


def checkpoint(run_id: str = "run-1", **changes) -> RunCheckpoint:
    values = {
        "schema_version": 1,
        "run_id": run_id,
        "task_id": "T-001",
        "node": "validation",
        "attempt": 1,
        "remaining": {},
        "start_commit": "a" * 40,
        "head_commit": "a" * 40,
        "worktree_fingerprint": "f" * 64,
        "patch_path": None,
        "completed": [],
        "agent_sessions": {},
        "pending_human_round": None,
        "artifacts": [],
        "interruption": "process_exit",
    }
    values.update(changes)
    return RunCheckpoint(**values)


def write(repo, cp):
    RunJournal(repo / "sessions" / ".factory-runs" / "by-session" / cp.run_id).checkpoint(cp)


def test_current_returns_newest_noncomplete_checkpoint(tmp_path, capsys):
    write(tmp_path, checkpoint("run-a"))
    write(tmp_path, checkpoint("run-b", node="closed"))
    assert load_current_checkpoint(tmp_path).run_id == "run-a"
    assert main(["current", "--repo", str(tmp_path), "--json"], git_ops=FakeGitOps(head="a" * 40)) == 0
    assert json.loads(capsys.readouterr().out)["checkpoint"]["run_id"] == "run-a"


def test_current_is_empty_after_reasoned_abandonment(tmp_path, capsys):
    write(tmp_path, checkpoint())
    assert main(
        ["abandon", "run-1", "--reason", "superseded", "--repo", str(tmp_path), "--json"],
        git_ops=FakeGitOps(head="a" * 40),
    ) == 0
    capsys.readouterr()
    assert load_current_checkpoint(tmp_path) is None


def test_inspect_is_read_only_and_structured(tmp_path, capsys):
    write(tmp_path, checkpoint())
    assert main(["inspect", "run-1", "--repo", str(tmp_path), "--json"], git_ops=FakeGitOps(head="a" * 40)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["assessment"]["state"] == "resumable"
    assert not (tmp_path / "sessions" / ".factory-runs" / "by-session" / "run-1" / "abandoned.json").exists()


def test_resume_invokes_callback_only_when_resumable(tmp_path, capsys):
    write(tmp_path, checkpoint())
    resumed = []
    assert main(
        ["resume", "run-1", "--repo", str(tmp_path), "--json"],
        git_ops=FakeGitOps(head="a" * 40),
        resume_callback=lambda cp: resumed.append(cp.run_id),
    ) == 0
    assert resumed == ["run-1"]
    assert json.loads(capsys.readouterr().out)["resumed"] is True


def test_resume_conflict_and_inspect_only_exit_codes(tmp_path, capsys):
    write(tmp_path, checkpoint(head_commit="b" * 40))
    assert main(
        ["resume", "run-1", "--repo", str(tmp_path), "--json"],
        git_ops=FakeGitOps(head="a" * 40),
    ) == 3
    capsys.readouterr()
    write(tmp_path, checkpoint(start_commit="missing"))
    assert main(
        ["resume", "run-1", "--repo", str(tmp_path), "--json"],
        git_ops=FakeGitOps(head="a" * 40),
    ) == 4


def test_missing_and_invalid_run_ids_are_operational_errors(tmp_path, capsys):
    assert main(["inspect", "../escape", "--repo", str(tmp_path), "--json"]) == 2
    assert "invalid run id" in json.loads(capsys.readouterr().out)["error"]
    assert main(["inspect", "gone", "--repo", str(tmp_path), "--json"]) == 2
