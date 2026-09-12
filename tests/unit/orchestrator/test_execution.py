from __future__ import annotations

import ast
import json
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


def test_consume_human_decision_matches_the_pending_request_append_only(tmp_path):
    """The kernel's durable pause/resume seam: a human decision is matched
    append-only against the pending request it recorded, and journalled."""
    from factory.orchestrator.execution import RunCursorError, RunExecution

    git = FakeGitOps(head="a" * 40)
    execution = RunExecution.create(tmp_path, "run-1", "T-001", "a" * 40, git)
    cursor = execution.record_stage(execution.begin_revision("dev"), state="completed")

    cursor, request = execution.open_human_decision_request(
        cursor, reason="fixer budget exhausted", finding_universe_sha256="b" * 64
    )
    assert request["state"] == "pending"
    assert len(request["request_sha256"]) == 64
    assert request["allowed_decisions"] == ("retry", "defer", "block")

    advanced = execution.consume_human_decision(
        "T-001",
        request_sha256=request["request_sha256"],
        decision="retry",
        response="human decision: retry",
        decided_by="human",
    )
    assert advanced.stage_id == "dev"
    decision_record = execution.journal.events()[-1].data["human_decision"]
    assert decision_record["decision"] == "retry"
    assert decision_record["decided_by"] == "human"
    assert decision_record["request_sha256"] == request["request_sha256"]
    assert decision_record["retry_reset_iteration"] == 0

    # Append-only: the same request hash can never be consumed twice.
    with pytest.raises(RunCursorError):
        execution.consume_human_decision(
            "T-001",
            request_sha256=request["request_sha256"],
            decision="block",
            response="again",
            decided_by="human",
        )


def test_consume_human_decision_refuses_unknown_non_human_and_no_request(tmp_path):
    from factory.orchestrator.execution import RunCursorError, RunExecution

    git = FakeGitOps(head="a" * 40)
    execution = RunExecution.create(tmp_path, "run-1", "T-001", "a" * 40, git)
    cursor = execution.record_stage(execution.begin_revision("dev"), state="completed")
    _cursor, request = execution.open_human_decision_request(cursor, reason="budget exhausted")
    digest = request["request_sha256"]

    with pytest.raises(RunCursorError):
        execution.consume_human_decision(
            "T-001", request_sha256=digest, decision="approve", response="?", decided_by="human"
        )
    with pytest.raises(RunCursorError):
        execution.consume_human_decision(
            "T-001", request_sha256=digest, decision="retry", response="?", decided_by="agent"
        )
    with pytest.raises(RunCursorError):
        execution.consume_human_decision(
            "T-001", request_sha256="c" * 64, decision="retry", response="?", decided_by="human"
        )
    with pytest.raises(RunCursorError):
        execution.consume_human_decision(
            "T-999", request_sha256=digest, decision="retry", response="?", decided_by="human"
        )

    fresh = RunExecution.create(tmp_path, "run-2", "T-002", "a" * 40, git)
    with pytest.raises(RunCursorError):
        fresh.consume_human_decision(
            "T-002", request_sha256=digest, decision="retry", response="?", decided_by="human"
        )


def test_governed_cursors_reconstruct_from_the_journal_across_a_restart(tmp_path):
    """``RunExecution.create`` rebuilds the monotonic cursor tail from the
    journal, so a resumed process continues instead of restarting at r1/a1."""
    from factory.orchestrator.execution import RunCursorError, RunExecution

    git = FakeGitOps(head="a" * 40)
    first = RunExecution.create(tmp_path, "run-1", "T-001", "a" * 40, git)
    dev = first.record_stage(first.begin_revision("dev"), state="completed", data={"outcome": "pass"})
    first.record_stage(first.begin_revision("validation"), state="completed")
    campaign = first.record_stage(
        first.begin_revision("campaign-classification"), state="completed"
    )
    first.record_stage(first.begin_revision("fixer"), state="completed")
    validation = first.record_stage(first.begin_revision("validation"), state="completed")

    resumed = RunExecution.create(tmp_path, "run-1", "T-001", "a" * 40, git)

    # The monotonic tail survives: max revision/attempt per stage, chained.
    assert (resumed.open_cursor("dev").revision, resumed.open_cursor("dev").attempt) == (1, 1)
    assert (resumed.open_cursor("validation").revision, resumed.open_cursor("validation").attempt) == (2, 1)
    assert resumed.open_cursor("dev").parent_event_sha256 == dev.parent_event_sha256
    assert resumed.open_cursor("validation").parent_event_sha256 == validation.parent_event_sha256
    assert resumed.open_cursor("validation").attempt_key == validation.attempt_key

    # Replaying the validation r2 record invalidated everything after it.
    with pytest.raises(RunCursorError):
        resumed.open_cursor("campaign-classification")
    with pytest.raises(RunCursorError):
        resumed.open_cursor("fixer")
    assert {"campaign-classification", "fixer"} <= resumed.invalidated_stages

    # A journalled attempt_key can never be reused after a restart: the
    # re-opened stage restarts its own revision counter (its cursor was dropped
    # by the invalidation) but is issued a fresh key, so the earlier r1/a1
    # record's key is not inherited.
    reopened = resumed.begin_revision("campaign-classification")
    assert reopened.revision == 1
    assert reopened.attempt_key != campaign.attempt_key
    assert reopened.attempt_key.startswith("run-1/T-001/campaign-classification/r1/a1/v")
    assert campaign.attempt_key in resumed.prior_attempt_keys
    assert reopened.attempt_key not in {campaign.attempt_key}


def test_open_task_cursor_addresses_the_cursor_by_run_and_task_identity(tmp_path):
    from coherence.execution.gate_plan import compile_gate_plan
    from factory.orchestrator.execution import RunCursorError, RunExecution

    git = FakeGitOps(head="a" * 40)
    execution = RunExecution.create(tmp_path, "run-1", "T-001", "a" * 40, git)
    plan = compile_gate_plan(
        workflow_version="governed-execution/v1",
        version="v1",
        required_gates=("unit",),
        preflight_policy="mandatory-only",
    )

    cursor = execution.open_task_cursor("T-001", plan)
    assert cursor.stage_id == plan.stages[0] == "contract-compiled"
    assert (cursor.revision, cursor.attempt) == (1, 1)
    assert execution.open_task_cursor("T-001", plan) == cursor  # the live root, not a new one
    assert execution.open_cursor("contract-compiled") == cursor  # 1-arg meaning unchanged

    with pytest.raises(RunCursorError):
        execution.open_task_cursor("T-999", plan)
    with pytest.raises(RunCursorError):
        execution.open_task_cursor("T-001", object())
    # The additive gate_plan parameter validates membership; it never widens a cursor.
    with pytest.raises(RunCursorError):
        execution.open_cursor("not-a-stage", plan)
    with pytest.raises(RunCursorError):
        execution.open_cursor("dev", object())


# --- FEAT-013 increment 4 (SR-034 Task 5): the fail-closed defects the
# --- adversarial review reproduced. Each test below is a RED probe for one of
# --- them; the docstring names the defect and the observable it pins.

_RUN_DIR = Path("sessions") / ".factory-runs" / "by-session" / "run-1"


def _rewrite_journal(run_dir: Path, mutate) -> None:
    """Hand-edit the journal the way a tamperer would: mutate and write back."""
    path = run_dir / "journal.jsonl"
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        mutate(event)
        out.append(json.dumps(event, separators=(",", ":")))
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def _reseal(event: dict) -> None:
    """Recompute a record's digest after editing it, so only the edit is left to catch."""
    from factory.orchestrator.execution import GovernedStageCursor, _stage_event_sha256

    data = event["data"]
    cursor = GovernedStageCursor(
        stage_id=data["stage_cursor"]["stage_id"],
        revision=data["stage_cursor"]["revision"],
        attempt=data["stage_cursor"]["attempt"],
        parent_event_sha256=data["stage_cursor"].get("parent_event_sha256"),
        attempt_key=data["stage_cursor"]["attempt_key"],
    )
    body = {key: value for key, value in data.items() if key != "stage_event_sha256"}
    data["stage_event_sha256"] = _stage_event_sha256(cursor, event["state"], body)


def test_a_reissued_request_after_a_consumed_decision_is_a_new_request(tmp_path):
    """F1 (wedged run): request identity had no nonce, so a re-issue at the same
    live cursor after a consumed decision inherited the consumed digest; the
    re-open was accepted, `pending_human_decision_request()` returned None while
    the live request sat in the journal, and every consume was then refused as
    'already consumed' -- the durable needs_input path deadlocked."""
    from factory.orchestrator.execution import RunExecution

    git = FakeGitOps(head="a" * 40)
    first = RunExecution.create(tmp_path, "run-1", "T-001", "a" * 40, git)
    cursor = first.record_stage(first.begin_revision("dev"), state="completed")
    cursor, request = first.open_human_decision_request(cursor, reason="budget exhausted")
    first.consume_human_decision(
        "T-001",
        request_sha256=request["request_sha256"],
        decision="defer",
        response="human: defer",
        decided_by="human",
    )

    # Crash before begin_attempt, restart, re-issue at the same live cursor.
    resumed = RunExecution.create(tmp_path, "run-1", "T-001", "a" * 40, git)
    assert resumed.pending_human_decision_request() is None
    live, again = resumed.open_human_decision_request(
        resumed.open_cursor("dev"), reason="budget exhausted"
    )
    assert again["request_sha256"] != request["request_sha256"]
    assert again["issuance_serial"] == request["issuance_serial"] + 1

    pending = resumed.pending_human_decision_request()
    assert pending is not None, "a live request must never read as absent"
    assert pending["request_sha256"] == again["request_sha256"]

    advanced = resumed.consume_human_decision(
        "T-001",
        request_sha256=again["request_sha256"],
        decision="retry",
        response="human: retry",
        decided_by="human",
    )
    assert advanced.stage_id == "dev"
    assert advanced.revision == 1


def test_an_exact_decision_replay_is_an_idempotent_read(tmp_path):
    """F1: an identical decision-id/request/hash replay is an idempotent read
    (plan lines 181-182); a conflicting replay still raises."""
    from factory.orchestrator.execution import RunCursorError, RunExecution

    git = FakeGitOps(head="a" * 40)
    execution = RunExecution.create(tmp_path, "run-1", "T-001", "a" * 40, git)
    cursor = execution.record_stage(execution.begin_revision("dev"), state="completed")
    cursor, request = execution.open_human_decision_request(cursor, reason="budget exhausted")
    advanced = execution.consume_human_decision(
        "T-001",
        request_sha256=request["request_sha256"],
        decision="retry",
        response="human: retry",
        decided_by="human",
    )
    journal_lines = len(execution.journal.events())

    replayed = execution.consume_human_decision(
        "T-001",
        request_sha256=request["request_sha256"],
        decision="retry",
        response="human: retry",
        decided_by="human",
    )
    assert replayed == advanced
    assert len(execution.journal.events()) == journal_lines, "an idempotent replay writes nothing"

    with pytest.raises(RunCursorError, match="conflicting replay"):
        execution.consume_human_decision(
            "T-001",
            request_sha256=request["request_sha256"],
            decision="block",
            response="human: retry",
            decided_by="human",
        )


def test_a_reopened_stage_fences_out_a_cursor_held_before_the_invalidation(tmp_path):
    """F2 (fencing key reuse in-process): after a descendant invalidation popped
    a stage, begin_revision re-opened it at revision 1 with the *same*
    attempt_key the earlier record already used, and prior_attempt_keys was only
    filled by restore_cursors -- so in-process the guard was empty and a cursor
    held from before the invalidation was accepted afterwards."""
    from factory.orchestrator.execution import RunCursorError, RunExecution

    git = FakeGitOps(head="a" * 40)
    execution = RunExecution.create(tmp_path, "run-1", "T-001", "a" * 40, git)
    stale = execution.record_stage(execution.begin_revision("validation"), state="completed")
    execution.record_stage(execution.begin_revision("dev"), state="completed")
    # A *second* dev revision invalidates every later stage, validation included.
    execution.record_stage(execution.begin_revision("dev"), state="completed")

    fresh = execution.begin_revision("validation")
    assert (fresh.stage_id, fresh.revision, fresh.attempt) == ("validation", 1, 1)
    assert fresh.attempt_key != stale.attempt_key
    assert stale.attempt_key in execution.prior_attempt_keys
    execution.record_stage(fresh, state="completed")

    with pytest.raises(RunCursorError):
        execution.record_stage(stale)


def test_a_replayed_stage_position_is_refused_on_restore(tmp_path):
    """F2: a position (stage, revision, attempt, key, parent, state) that the run
    already recorded must be refused rather than journalled twice -- the replay
    of a journal line was silently accepted (and chained) before."""
    from factory.orchestrator.execution import RunCursorError, RunExecution

    git = FakeGitOps(head="a" * 40)
    execution = RunExecution.create(tmp_path, "run-1", "T-001", "a" * 40, git)
    execution.record_stage(execution.begin_revision("dev"), state="completed")
    execution.record_stage(execution.begin_revision("validation"), state="completed")
    execution.begin_revision("dev")  # dev r2: a genuine bump, so it IS journalled
    run_dir = tmp_path / _RUN_DIR

    # Duplicate that bump record in place, so the replay is chain-consistent and
    # the only thing that can catch it is the position it duplicates.
    path = run_dir / "journal.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    target = None
    for index, line in enumerate(lines):
        data = (json.loads(line).get("data") or {})
        if data.get("cursor_opened") and (data.get("stage_cursor") or {}).get("stage_id") == "dev":
            target = index
    assert target is not None
    lines.insert(target + 1, lines[target])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(RunCursorError, match="recorded twice"):
        RunExecution.create(tmp_path, "run-1", "T-001", "a" * 40, git)


def test_a_revision_bump_survives_a_restart_and_keeps_descendants_invalidated(tmp_path):
    """F3 (restored invalidation not faithful): begin_revision journalled
    nothing, so a bump that had invalidated descendants in memory was invisible
    after a restart -- the restored invalidated set was empty, the descendants
    were open again, and a cursor the live process had invalidated was accepted
    post-resume."""
    from factory.orchestrator.execution import RunCursorError, RunExecution

    git = FakeGitOps(head="a" * 40)
    first = RunExecution.create(tmp_path, "run-1", "T-001", "a" * 40, git)
    first.record_stage(first.begin_revision("dev"), state="completed")
    first.record_stage(first.begin_revision("validation"), state="completed")
    first.record_stage(first.begin_revision("fixer"), state="completed")

    bumped = first.begin_revision("dev")  # crash before any record at the new revision
    assert bumped.revision == 2
    assert {"validation", "fixer"} <= first.invalidated_stages

    resumed = RunExecution.create(tmp_path, "run-1", "T-001", "a" * 40, git)
    assert resumed.open_cursor("dev").revision == 2
    assert {"validation", "fixer"} <= resumed.invalidated_stages
    with pytest.raises(RunCursorError):
        resumed.open_cursor("validation")
    with pytest.raises(RunCursorError):
        resumed.open_cursor("fixer")


def test_a_decision_cannot_be_consumed_after_begin_attempt_supersedes_it(tmp_path):
    """F4 (decision applied to a superseded position): consume matched by request
    hash only and journalled the decision against whatever cursor was live
    *now*, so a request opened at dev r1 a1 was consumed as dev-2 while its
    payload still said revision 1 / attempt 1."""
    from factory.orchestrator.execution import RunCursorError, RunExecution

    git = FakeGitOps(head="a" * 40)
    execution = RunExecution.create(tmp_path, "run-1", "T-001", "a" * 40, git)
    cursor = execution.record_stage(execution.begin_revision("dev"), state="completed")
    cursor, request = execution.open_human_decision_request(cursor, reason="budget exhausted")
    execution.begin_attempt("dev")  # the position the request named is gone

    with pytest.raises(RunCursorError, match="superseded"):
        execution.consume_human_decision(
            "T-001",
            request_sha256=request["request_sha256"],
            decision="defer",
            response="human: defer",
            decided_by="human",
        )
    assert execution.consumed_request_sha256s() == set()


def test_a_decision_cannot_be_consumed_after_a_same_stage_revision_supersedes_it(tmp_path):
    """F4: the same refusal for a same-stage begin_revision (open at dev r1,
    consumed against r2)."""
    from factory.orchestrator.execution import RunCursorError, RunExecution

    git = FakeGitOps(head="a" * 40)
    execution = RunExecution.create(tmp_path, "run-1", "T-001", "a" * 40, git)
    cursor = execution.record_stage(execution.begin_revision("dev"), state="completed")
    cursor, request = execution.open_human_decision_request(cursor, reason="budget exhausted")
    assert execution.begin_revision("dev").revision == 2

    with pytest.raises(RunCursorError, match="superseded"):
        execution.consume_human_decision(
            "T-001",
            request_sha256=request["request_sha256"],
            decision="block",
            response="human: block",
            decided_by="human",
        )


def test_a_forged_or_non_canonical_digest_fails_closed_on_restore(tmp_path):
    """F5 (tamper-evidence was live-only): restore trusted any 64-hex
    `stage_event_sha256` it found and silently degraded to the stored parent
    otherwise, and never recomputed anything. A forged digest must fail closed."""
    from factory.orchestrator.execution import RunCursorError, RunExecution

    git = FakeGitOps(head="a" * 40)
    execution = RunExecution.create(tmp_path, "run-1", "T-001", "a" * 40, git)
    execution.record_stage(execution.begin_revision("dev"), state="completed")
    run_dir = tmp_path / _RUN_DIR

    # (a) a forged digest that does not recompute from the persisted payload
    _rewrite_journal(
        run_dir,
        lambda event: event["data"].update({"stage_event_sha256": "f" * 64})
        if "stage_cursor" in event["data"]
        else None,
    )
    with pytest.raises(RunCursorError, match="tamper-evidence"):
        RunExecution.create(tmp_path, "run-1", "T-001", "a" * 40, git)

    # (b) a non-canonical digest (previously degraded to the stored parent)
    _rewrite_journal(
        run_dir,
        lambda event: event["data"].update({"stage_event_sha256": "not-a-digest"})
        if "stage_cursor" in event["data"]
        else None,
    )
    with pytest.raises(RunCursorError, match="stage_event_sha256"):
        RunExecution.create(tmp_path, "run-1", "T-001", "a" * 40, git)


def test_a_dangling_parent_link_fails_closed_on_restore(tmp_path):
    """F5: restore never checked that a record's stored parent equals the
    previous record's digest, so a hand-edited (but self-consistent) dangling
    parent was accepted and chained."""
    from factory.orchestrator.execution import RunCursorError, RunExecution

    git = FakeGitOps(head="a" * 40)
    execution = RunExecution.create(tmp_path, "run-1", "T-001", "a" * 40, git)
    execution.record_stage(execution.begin_revision("dev"), state="completed")
    execution.record_stage(execution.begin_revision("validation"), state="completed")
    run_dir = tmp_path / _RUN_DIR

    seen: list[int] = []

    def _dangle(event: dict) -> None:
        data = event.get("data")
        if not isinstance(data, dict) or "stage_cursor" not in data:
            return
        seen.append(1)
        if len(seen) == 2:  # the validation evidence record: valid digest, wrong parent
            data["stage_cursor"]["parent_event_sha256"] = "e" * 64
            _reseal(event)

    _rewrite_journal(run_dir, _dangle)
    with pytest.raises(RunCursorError, match="chain is broken"):
        RunExecution.create(tmp_path, "run-1", "T-001", "a" * 40, git)


def test_restore_rejects_a_stage_outside_the_canonical_graph(tmp_path):
    """F6a: a journal whose stage id is outside the canonical graph made restore
    raise a bare `ValueError: tuple.index(x): x not in tuple` from
    _invalidate_descendants instead of the module's RunCursorError."""
    from factory.orchestrator.execution import RunCursorError, RunExecution

    git = FakeGitOps(head="a" * 40)
    execution = RunExecution.create(tmp_path, "run-1", "T-001", "a" * 40, git)
    execution.record_stage(execution.begin_revision("dev"), state="completed")
    execution.record_stage(execution.begin_revision("dev"), state="completed")
    run_dir = tmp_path / _RUN_DIR

    def _bogus(event: dict) -> None:
        data = event.get("data")
        if isinstance(data, dict) and "stage_cursor" in data:
            data["stage_cursor"]["stage_id"] = "not-a-canonical-stage"
            _reseal(event)

    _rewrite_journal(run_dir, _bogus)
    with pytest.raises(RunCursorError, match="unknown execution stage"):
        RunExecution.create(tmp_path, "run-1", "T-001", "a" * 40, git)


def test_the_human_decision_surface_documents_its_real_durability_guarantee():
    """F6c: the journal is rewritten in place, so the docstrings must not imply
    a cryptographic append-only log -- deleting a decision line resurrects its
    request as pending."""
    from factory.orchestrator.execution import RunExecution

    request_doc = RunExecution.open_human_decision_request.__doc__ or ""
    consume_doc = RunExecution.consume_human_decision.__doc__ or ""
    restore_doc = RunExecution.restore_cursors.__doc__ or ""
    assert "not a cryptographic append-only" in request_doc
    assert "plain" in consume_doc and "file" in consume_doc
    assert "deleting a decision line resurrects" in consume_doc
    assert "not stable across this change" in restore_doc
