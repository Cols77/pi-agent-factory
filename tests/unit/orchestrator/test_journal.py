from __future__ import annotations

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


def test_checkpoint_round_trip_is_atomic(tmp_path):
    journal = RunJournal(tmp_path)
    journal.checkpoint(checkpoint())
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
