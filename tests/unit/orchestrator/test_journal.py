from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from factory.orchestrator.journal import RunCheckpoint, RunEvent, RunJournal

pytestmark = pytest.mark.unit


def event(sequence: int, state: str = "started") -> RunEvent:
    return RunEvent(
        sequence=sequence,
        at="2026-08-07T12:00:00Z",
        run_id="run-1",
        task_id="T-001",
        node="dev",
        attempt_id=f"dev-{sequence}",
        state=state,
        data={"attempt": sequence},
    )


def checkpoint(node: str = "dev") -> RunCheckpoint:
    return RunCheckpoint(
        schema_version=1,
        run_id="run-1",
        task_id="T-001",
        node=node,
        attempt=1,
        remaining={"dev": 2},
        start_commit="a" * 40,
        head_commit="a" * 40,
        worktree_fingerprint="b" * 64,
        patch_path="checkpoints/1.patch",
        completed=[],
        agent_sessions={"dev": "session-1"},
        pending_human_round=None,
        artifacts=[],
        interruption=None,
    )


def test_append_is_durable_and_replays_in_order(tmp_path):
    journal = RunJournal(tmp_path)
    with patch("factory.orchestrator.journal.os.fsync") as fsync:
        journal.append(event(1))
        journal.append(event(2, "completed"))
    assert fsync.call_count == 2
    assert [(item.sequence, item.state) for item in journal.events()] == [
        (1, "started"),
        (2, "completed"),
    ]


def test_checkpoint_round_trip_is_atomic_and_durable(tmp_path):
    journal = RunJournal(tmp_path)
    with patch("factory.orchestrator.journal.os.fsync") as fsync:
        journal.checkpoint(checkpoint())
    fsync.assert_called_once()
    assert journal.latest() == checkpoint()
    assert not (tmp_path / "checkpoint.json.tmp").exists()


def test_replay_ignores_only_partial_tail(tmp_path):
    journal = RunJournal(tmp_path)
    journal.append(event(1))
    with journal.journal_path.open("ab") as stream:
        stream.write(b'{"sequence":2')
    assert [item.sequence for item in journal.events()] == [1]


def test_replay_rejects_corruption_before_final_line(tmp_path):
    journal = RunJournal(tmp_path)
    journal.journal_path.write_bytes(b"not-json\n" + b'{"sequence":2')
    with pytest.raises(ValueError, match="line 1"):
        journal.events()


def test_missing_state_is_empty(tmp_path):
    journal = RunJournal(tmp_path)
    assert journal.events() == []
    assert journal.latest() is None


def test_corrupt_checkpoint_is_not_silently_ignored(tmp_path):
    journal = RunJournal(tmp_path)
    journal.checkpoint_path.write_text("not-json", encoding="utf-8")
    with pytest.raises(ValueError, match="corrupt run checkpoint"):
        journal.latest()


def test_old_schema_checkpoint_without_tracked_fingerprint_loads_with_default(tmp_path):
    """KB-0004: checkpoints written before tracked_fingerprint existed must still
    load, so resume can fall back to the saved patch for the tracked-diff check.
    Unknown newer keys are dropped; missing defaulted fields are filled in."""
    journal = RunJournal(tmp_path)
    old = {
        "schema_version": 1,
        "run_id": "run-1",
        "task_id": "T-001",
        "node": "review",
        "attempt": 2,
        "remaining": {"dev": 1},
        "start_commit": "a" * 40,
        "head_commit": "a" * 40,
        "worktree_fingerprint": "b" * 64,
        "patch_path": "checkpoints/000003.patch",
        "completed": [],
        "agent_sessions": {},
        "pending_human_round": None,
        "artifacts": [],
        "interruption": "process_exit",
        # A future field that does not exist yet -- must be tolerated.
        "future_field": {"x": 1},
    }
    journal.checkpoint_path.write_text(json.dumps(old), encoding="utf-8")

    loaded = journal.latest()

    assert loaded.run_id == "run-1"
    assert loaded.node == "review"
    assert loaded.tracked_fingerprint is None
    assert loaded.patch_path == "checkpoints/000003.patch"
    assert not hasattr(loaded, "future_field")
