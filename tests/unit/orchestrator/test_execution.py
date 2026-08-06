from __future__ import annotations

import pytest

from factory.orchestrator.execution import RunExecution
from factory.orchestrator.git_ops import FakeGitOps

pytestmark = pytest.mark.unit


def test_record_journals_then_writes_patch_and_atomic_checkpoint(tmp_path):
    git = FakeGitOps(head="a" * 40)
    execution = RunExecution.create(tmp_path, "run-1", "T-001", "a" * 40, git)
    checkpoint = execution.record(
        node="context-gather",
        state="completed",
        attempt=1,
        next_node="dev",
        remaining={"dev": 3, "review": 2},
        data={"outcome": "pass", "transcript": "sha256:abc"},
        session_id="pi-session",
    )
    assert checkpoint.node == "dev"
    assert checkpoint.completed == [{
        "node": "context-gather", "attempt": 1,
        "data": {"outcome": "pass", "transcript": "sha256:abc"},
    }]
    assert checkpoint.agent_sessions == {"context-gather": "pi-session"}
    assert checkpoint.patch_path == (
        "sessions/.factory-runs/by-session/run-1/checkpoints/000001.patch"
    )
    assert execution.journal.events()[0].state == "completed"
    assert execution.journal.latest() == checkpoint


def test_sequence_continues_from_existing_journal(tmp_path):
    git = FakeGitOps(head="a" * 40)
    first = RunExecution.create(tmp_path, "run-1", "T-001", "a" * 40, git)
    first.record(
        node="dev", state="started", attempt=1, next_node="dev",
        remaining={"dev": 2},
    )
    second = RunExecution.create(tmp_path, "run-1", "T-001", "a" * 40, git)
    second.record(
        node="dev", state="completed", attempt=1, next_node="validation",
        remaining={"dev": 2},
    )
    assert [event.sequence for event in second.journal.events()] == [1, 2]
