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


def test_oversized_payload_is_externalised_to_a_blob_reference(tmp_path):
    """KB-0004: a context-gather manifest embedded whole into RunEvent.data and
    completed[].data produced 106MB checkpoint/journal files and a MemoryError.
    Oversized payloads must be stored as a file referenced by path."""
    from factory.orchestrator.execution import MAX_INLINE_PAYLOAD_BYTES

    git = FakeGitOps(head="a" * 40)
    execution = RunExecution.create(tmp_path, "run-1", "T-001", "a" * 40, git)
    big = {"manifest": "x" * (MAX_INLINE_PAYLOAD_BYTES + 1)}

    checkpoint = execution.record(
        node="context-gather",
        state="completed",
        attempt=1,
        next_node="dev",
        remaining={"dev": 3},
        data=big,
    )

    run_dir = tmp_path / "sessions" / ".factory-runs" / "by-session" / "run-1"
    inline = checkpoint.completed[0]["data"]
    assert "payload_ref" in inline
    blob = run_dir / inline["payload_ref"]
    assert blob.exists()
    assert blob.stat().st_size > MAX_INLINE_PAYLOAD_BYTES

    # The journal line must stay small too.
    assert execution.journal.journal_path.stat().st_size < MAX_INLINE_PAYLOAD_BYTES
    assert execution.journal.checkpoint_path.stat().st_size < MAX_INLINE_PAYLOAD_BYTES

    # And a fresh execution resolves the reference back to the real payload.
    replay = RunExecution.create(tmp_path, "run-1", "T-001", "a" * 40, git)
    assert replay.resolve_data(inline)["manifest"] == big["manifest"]


def test_small_payload_stays_inline(tmp_path):
    git = FakeGitOps(head="a" * 40)
    execution = RunExecution.create(tmp_path, "run-1", "T-001", "a" * 40, git)
    checkpoint = execution.record(
        node="dev",
        state="completed",
        attempt=1,
        next_node="validation",
        remaining={"dev": 2},
        data={"outcome": "pass"},
    )
    assert checkpoint.completed[0]["data"] == {"outcome": "pass"}
    assert "payload_ref" not in checkpoint.completed[0]["data"]


def test_resolve_data_degrades_gracefully_on_missing_or_bad_blob(tmp_path):
    git = FakeGitOps(head="a" * 40)
    execution = RunExecution.create(tmp_path, "run-1", "T-001", "a" * 40, git)
    assert execution.resolve_data({"payload_ref": "missing.json"}) == {"payload_ref": "missing.json"}
    assert execution.resolve_data({"outcome": "pass"}) == {"outcome": "pass"}


def test_checkpoint_records_tracked_fingerprint_and_schema_v2(tmp_path):
    git = FakeGitOps(head="a" * 40)
    execution = RunExecution.create(tmp_path, "run-1", "T-001", "a" * 40, git)
    checkpoint = execution.record(
        node="dev", state="completed", attempt=1, next_node="validation", remaining={},
    )
    assert checkpoint.schema_version == 2
    assert checkpoint.tracked_fingerprint == git.tracked_fp
