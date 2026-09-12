from __future__ import annotations

import ast
from pathlib import Path

import pytest

from coherence.execution.gate_plan import CANONICAL_EXECUTION_STAGES as CANONICAL_STAGE_IDS
from factory.orchestrator.execution import RunExecution
from factory.orchestrator.git_ops import FakeGitOps

pytestmark = pytest.mark.unit

_RUNNER_PY = Path(__file__).resolve().parents[3] / "src" / "factory" / "orchestrator" / "runner.py"


def legacy_resume_skip_set() -> set[str]:
    """Extract runner.py's ``resume_at in {...}`` literal from the real source.

    Read from disk, not restated here: the regression is about the *on-disk*
    router vocabulary, so the test must fail if runner.py widens that literal
    to a canonical stage id (e.g. ``stage:validation``).
    """
    tree = ast.parse(_RUNNER_PY.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        if not any(isinstance(op, ast.In) for op in node.ops):
            continue
        for comparator in [node.left, *node.comparators]:
            if not isinstance(comparator, ast.Set):
                continue
            values = {
                element.value
                for element in comparator.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            }
            if "validation" in values or "human-review" in values:
                return values
    raise AssertionError(f"legacy resume skip-set literal not found in {_RUNNER_PY}")


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


def test_run_execution_cursor_extension_is_additive_to_record_behavior(tmp_path):
    """SR-049: the governed cursor adds revision/attempt evidence to the journal
    without changing what record() already journals."""
    from factory.orchestrator.execution import RunExecution

    git = FakeGitOps(head="a" * 40)
    execution = RunExecution.create(tmp_path, "run-1", "T-001", "a" * 40, git)

    cursor = execution.begin_revision("dev")
    assert (cursor.stage_id, cursor.revision, cursor.attempt) == ("dev", 1, 1)
    assert cursor.attempt_key == "run-1/T-001/dev/r1/a1/v1"
    assert cursor.parent_event_sha256 is None

    recorded = execution.record_stage(cursor, state="completed", data={"outcome": "pass"})
    assert recorded.parent_event_sha256 is not None
    event = execution.journal.events()[-1]
    assert event.node == "dev" and event.attempt_id == "dev-1"
    assert event.data["stage_cursor"]["revision"] == 1

    # The pre-existing record() path is untouched.
    checkpoint = execution.record(
        node="context-gather", state="completed", attempt=1, next_node="dev",
        remaining={"dev": 3}, data={"outcome": "pass"},
    )
    assert checkpoint.node == "dev"


def test_run_execution_cursor_rejects_unknown_stage_and_replay(tmp_path):
    from factory.orchestrator.execution import RunCursorError, RunExecution

    git = FakeGitOps(head="a" * 40)
    execution = RunExecution.create(tmp_path, "run-1", "T-001", "a" * 40, git)

    with pytest.raises(RunCursorError):
        execution.open_cursor("dev")
    with pytest.raises(RunCursorError):
        execution.begin_attempt("dev")

    cursor = execution.begin_revision("dev")
    execution.record_stage(cursor, state="completed")
    with pytest.raises(RunCursorError):
        execution.record_stage(cursor)
    assert execution.stage_cursors["dev"].attempt == 1


def test_a_stage_record_cannot_make_a_resume_skip_dev(tmp_path):
    """The blocking Task 8 finding: a governed stage record must never write a
    checkpoint node that the legacy router reads as 'past DEV'.

    runner.py's router computes ``resume_at = resume.node`` and skips the whole
    run_dev block when ``resume_at in {"validation", "review", "human-review"}``.
    A stage record whose checkpoint node was the bare canonical stage id made a
    resume of that checkpoint skip DEV entirely.
    """
    from factory.orchestrator.execution import STAGE_CHECKPOINT_NODE_PREFIX, RunExecution

    skip_set = legacy_resume_skip_set()
    # The literal is real: if it ever stops naming these nodes the probe below
    # would be vacuous, so pin the observed vocabulary first.
    assert skip_set == {"validation", "review", "human-review"}

    git = FakeGitOps(head="a" * 40)
    execution = RunExecution.create(tmp_path, "run-1", "T-001", "a" * 40, git)

    # Nothing else recorded: this is exactly what the adversarial probe did.
    cursor = execution.begin_revision("validation")
    execution.record_stage(cursor, state="completed")
    checkpoint = execution.journal.latest()  # the checkpoint as it lands on disk
    assert checkpoint is not None

    assert checkpoint.node not in skip_set
    assert checkpoint.node == f"{STAGE_CHECKPOINT_NODE_PREFIX}validation"
    assert checkpoint.node != "validation"

    # The router predicate itself: first_dev is True on every fresh resume, so
    # the only thing standing between this checkpoint and a skipped DEV is the
    # node value.
    first_dev = True
    resume_skips_dev = first_dev and checkpoint.node in skip_set
    assert resume_skips_dev is False

    # And it holds for every canonical stage, not just 'validation'.
    for stage_id in CANONICAL_STAGE_IDS:
        if stage_id == "validation":
            continue
        other = execution.begin_revision(stage_id)
        execution.record_stage(other, state="completed")
        latest = execution.journal.latest()
        assert latest is not None
        assert latest.node not in skip_set

    # The governed identity stays queryable in the journal payload.
    event = execution.journal.events()[0]
    assert event.data["stage_cursor"]["stage_id"] == "validation"
    assert event.node == "validation" and event.attempt_id == "validation-1"


def test_invalidated_stages_track_the_current_revision_not_every_revision(tmp_path):
    """A later revision invalidates descendants; re-opening a descendant must
    clear it, or a consumer cannot tell 'invalidated now' from 'invalidated
    three revisions ago' (both were permanent before)."""
    from factory.orchestrator.execution import RunExecution

    git = FakeGitOps(head="a" * 40)
    execution = RunExecution.create(tmp_path, "run-1", "T-001", "a" * 40, git)

    execution.record_stage(execution.begin_revision("fixer"), state="completed")
    execution.record_stage(execution.begin_revision("canonical-gates"), state="completed")
    execution.record_stage(execution.begin_revision("handoff"), state="completed")

    execution.begin_revision("fixer")  # revision 2 invalidates everything after it
    assert {"canonical-gates", "handoff"} <= execution.invalidated_stages

    execution.begin_revision("canonical-gates")  # re-opened: live again
    assert "canonical-gates" not in execution.invalidated_stages
    assert "handoff" in execution.invalidated_stages  # still stale
    # Invalidation drops the stale cursor, so a re-opened descendant restarts its
    # revision count; what matters here is that the stage is live, not stale.
    assert execution.open_cursor("canonical-gates").revision == 1


def test_stage_record_marks_its_empty_remaining_as_not_exhausted_budget(tmp_path):
    """``remaining={}`` on a stage record is 'no legacy budget counters here',
    never 'the driver's budget is spent'."""
    from factory.orchestrator.execution import STAGE_RECORD_BUDGET_NOTE, RunExecution

    git = FakeGitOps(head="a" * 40)
    execution = RunExecution.create(tmp_path, "run-1", "T-001", "a" * 40, git)
    execution.record_stage(execution.begin_revision("dev"), state="completed")
    checkpoint = execution.journal.latest()
    assert checkpoint is not None

    assert checkpoint.remaining == {}
    assert checkpoint.completed[0]["data"]["budget_note"] == STAGE_RECORD_BUDGET_NOTE
    assert "not" in STAGE_RECORD_BUDGET_NOTE and "exhaust" in STAGE_RECORD_BUDGET_NOTE
