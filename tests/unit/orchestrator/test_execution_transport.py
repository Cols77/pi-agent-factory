"""SR-034/SR-049 host-neutral transport projection: RED tests (Task 8, Step 1/4)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from coherence.execution.gate_plan import compile_gate_plan
from factory.orchestrator.execution import GovernedStageCursor, RunCursorError, RunExecution
from factory.orchestrator.execution_contract import ExecutionContract
from factory.orchestrator.execution_transport import (
    ALLOWED_TRANSPORTS,
    ExecutionTransport,
    TransportError,
    materialize_transport,
)
from factory.orchestrator.git_ops import FakeGitOps

pytestmark = pytest.mark.unit

CANONICAL_STAGE_IDS = [
    "contract-compiled",
    "preflight",
    "transport-materialized",
    "baseline",
    "dev",
    "validation",
    "campaign-classification",
    "review-spec",
    "review-quality",
    "review-join",
    "fixer",
    "canonical-gates",
    "handoff",
]


def contract_fixture(tmp_path: Path, **overrides: object) -> ExecutionContract:
    values: dict[str, object] = {
        "run_id": "feat013",
        "task_id": "FEAT-013",
        "workflow_version": "governed-execution/v1",
        "workspace": tmp_path / "worktree",
        "required_gates": ("unit", "full"),
        "satisfies": ("SR-034", "SR-049"),
        "plan_ref": "docs/superpowers/plans/2026-09-10-feat013-governed-execution-driver-plan.md",
        "spec_ref": "docs/superpowers/specs/feat013.md",
        "max_fixer_iterations": 2,
    }
    values.update(overrides)
    return ExecutionContract.build(**values)  # type: ignore[arg-type]


def gate_plan_fixture(contract: ExecutionContract):
    return compile_gate_plan(
        workflow_version=contract.workflow_version,
        version="behavior-change@1",
        required_gates=("unit", "full"),
        preflight_policy="mandatory-only",
    )


def cursor_fixture(
    contract: ExecutionContract, *, stage_id: str = "transport-materialized", **overrides: object
) -> GovernedStageCursor:
    values: dict[str, object] = {
        "stage_id": stage_id,
        "revision": 1,
        "attempt": 1,
        "parent_event_sha256": None,
        "attempt_key": f"{contract.run_id}/{contract.task_id}/{stage_id}/r1/a1/v1",
    }
    values.update(overrides)
    return GovernedStageCursor(**values)  # type: ignore[arg-type]


def test_transport_projection_carries_contract_and_gate_plan_identity(tmp_path: Path) -> None:
    contract = contract_fixture(tmp_path)
    gate_plan = compile_gate_plan(
        workflow_version=contract.workflow_version,
        version="behavior-change@1",
        required_gates=("unit", "full"),
        preflight_policy="mandatory-only",
    )

    bound = contract.with_gate_plan(gate_plan)  # new frozen contract; digest recomputed, never mutated
    cursor = GovernedStageCursor(
        stage_id="transport-materialized", revision=1, attempt=1,
        parent_event_sha256=None,
        attempt_key="feat013/FEAT-013/transport-materialized/r1/a1/v1",
    )
    projection = materialize_transport(
        transport="hermes-kanban", contract=bound, gate_plan=gate_plan, cursor=cursor,
    )

    assert all(card.revision == 1 and card.attempt == 1 for card in projection.cards)

    assert projection.root.run_id == bound.run_id
    assert all(card.contract_sha256 == bound.contract_sha256 for card in projection.cards)
    assert all(card.gate_plan_sha256 == gate_plan.gate_plan_sha256 for card in projection.cards)
    assert all(card.workflow_version == contract.workflow_version for card in projection.cards)
    assert [card.stage_id for card in projection.cards] == [
        "contract-compiled", "preflight", "transport-materialized", "baseline", "dev",
        "validation", "campaign-classification", "review-spec", "review-quality",
        "review-join", "fixer", "canonical-gates", "handoff",
    ]


def test_transport_is_a_projection_not_a_scheduler_or_allocator() -> None:
    assert not hasattr(ExecutionTransport, "schedule")
    assert not hasattr(ExecutionTransport, "retry")
    assert not hasattr(ExecutionTransport, "allocate_worktree")

    assert not hasattr(ExecutionTransport, "compile_gate_plan")
    assert not hasattr(ExecutionTransport, "heartbeat")
    assert not hasattr(ExecutionTransport, "complete")
    assert not hasattr(ExecutionTransport, "dispatch")


def test_card_attempt_and_revision_track_the_current_cursor_never_a_constant(
    tmp_path: Path,
) -> None:
    contract = contract_fixture(tmp_path)
    gate_plan = gate_plan_fixture(contract)
    bound = contract.with_gate_plan(gate_plan)
    cursor = cursor_fixture(
        contract, revision=4, attempt=3,
        attempt_key="feat013/FEAT-013/transport-materialized/r4/a3/v1",
    )

    projection = materialize_transport(
        transport="direct", contract=bound, gate_plan=gate_plan, cursor=cursor
    )

    assert all(card.revision == 4 and card.attempt == 3 for card in projection.cards)
    assert all(card.attempt_key == cursor.attempt_key for card in projection.cards)
    assert projection.root.revision == 4 and projection.root.attempt == 3


def test_direct_and_hermes_kanban_expose_identical_canonical_stage_metadata(
    tmp_path: Path,
) -> None:
    contract = contract_fixture(tmp_path)
    gate_plan = gate_plan_fixture(contract)
    bound = contract.with_gate_plan(gate_plan)
    cursor = cursor_fixture(contract)

    direct = materialize_transport(
        transport="direct", contract=bound, gate_plan=gate_plan, cursor=cursor
    )
    kanban = materialize_transport(
        transport="hermes-kanban", contract=bound, gate_plan=gate_plan, cursor=cursor
    )

    def metadata(projection) -> list[tuple[object, ...]]:
        return [
            (
                card.stage_id, card.revision, card.attempt, card.run_id,
                card.contract_sha256, card.gate_plan_sha256, card.workflow_version,
            )
            for card in projection.cards
        ]

    assert metadata(direct) == metadata(kanban)
    assert direct.transport == "direct"
    assert kanban.transport == "hermes-kanban"
    assert ALLOWED_TRANSPORTS == ("direct", "hermes-kanban")

    # A projection is a deterministic immutable value, not a mutable board.
    again = materialize_transport(
        transport="direct", contract=bound, gate_plan=gate_plan, cursor=cursor
    )
    assert again.projection_sha256 == direct.projection_sha256
    with pytest.raises(FrozenInstanceError):
        direct.root.revision = 9  # type: ignore[misc]


def test_human_retry_emits_attempt_two_without_overwriting_attempt_one(tmp_path: Path) -> None:
    contract = contract_fixture(tmp_path)
    gate_plan = gate_plan_fixture(contract)
    bound = contract.with_gate_plan(gate_plan)
    execution = RunExecution.create(tmp_path, "feat013", "FEAT-013", "a" * 40, FakeGitOps(head="a" * 40))

    first = execution.begin_revision("dev")
    execution.record_stage(first, state="completed", data={"outcome": "needs_input"})
    second = execution.begin_attempt("dev")

    assert second.attempt == 2
    assert second.revision == first.revision == 1
    execution.record_stage(second, state="completed", data={"outcome": "human-retry"})

    events = [event for event in execution.journal.events() if event.node == "dev"]
    assert [event.attempt_id for event in events] == ["dev-1", "dev-2"]
    assert events[0].data["outcome"] == "needs_input"
    assert execution.stage_cursors["dev"].attempt == 2

    attempt_one = materialize_transport(
        transport="hermes-kanban", contract=bound, gate_plan=gate_plan, cursor=first
    )
    attempt_two = materialize_transport(
        transport="hermes-kanban", contract=bound, gate_plan=gate_plan, cursor=second
    )
    assert all(card.attempt == 1 for card in attempt_one.cards)
    assert all(card.attempt == 2 for card in attempt_two.cards)
    assert attempt_one.root.attempt_key != attempt_two.root.attempt_key


def test_fixer_emits_a_new_revision_with_descendant_invalidation(tmp_path: Path) -> None:
    contract = contract_fixture(tmp_path)
    gate_plan = gate_plan_fixture(contract)
    bound = contract.with_gate_plan(gate_plan)
    execution = RunExecution.create(tmp_path, "feat013", "FEAT-013", "a" * 40, FakeGitOps(head="a" * 40))

    fixer_r1 = execution.begin_revision("fixer")
    execution.record_stage(fixer_r1, state="completed")
    gates_r1 = execution.begin_revision("canonical-gates")
    execution.record_stage(gates_r1, state="completed")

    fixer_r2 = execution.begin_revision("fixer")

    assert fixer_r2.revision == 2 and fixer_r2.attempt == 1
    assert "canonical-gates" in execution.invalidated_stages
    assert "handoff" in execution.invalidated_stages
    with pytest.raises(RunCursorError):
        execution.record_stage(gates_r1)
    with pytest.raises(RunCursorError):
        execution.open_cursor("canonical-gates")

    revision_two = materialize_transport(
        transport="direct", contract=bound, gate_plan=gate_plan, cursor=fixer_r2
    )
    revision_one = materialize_transport(
        transport="direct", contract=bound, gate_plan=gate_plan, cursor=fixer_r1
    )
    assert all(card.revision == 2 for card in revision_two.cards)
    assert all(card.revision == 1 for card in revision_one.cards)


def test_contract_gate_plan_hash_mismatch_is_rejected_before_dev(tmp_path: Path) -> None:
    contract = contract_fixture(tmp_path)
    gate_plan = gate_plan_fixture(contract)
    other_plan = compile_gate_plan(
        workflow_version=contract.workflow_version,
        version="behavior-change@2",
        required_gates=("unit", "full"),
        preflight_policy="mandatory-only",
    )
    bound = contract.with_gate_plan(gate_plan)
    cursor = cursor_fixture(contract)

    with pytest.raises(TransportError):
        materialize_transport(
            transport="direct", contract=bound, gate_plan=other_plan, cursor=cursor
        )

    # A contract that never learned a GatePlan cannot be transported at all.
    with pytest.raises(TransportError):
        materialize_transport(
            transport="direct", contract=contract, gate_plan=gate_plan, cursor=cursor
        )

    with pytest.raises(TransportError):
            materialize_transport(
                transport="not-a-transport", contract=bound, gate_plan=gate_plan, cursor=cursor
            )

    # The rejected projection never produced a DEV card.
    assert not any(
        card.stage_id == "dev"
        for card in materialize_transport(
            transport="direct", contract=bound, gate_plan=gate_plan, cursor=cursor
        ).cards
        if card.contract_sha256 != bound.contract_sha256
    )


def test_cursor_rejects_stale_replay_non_monotonic_and_parent_hash_mismatch(
    tmp_path: Path,
) -> None:
    execution = RunExecution.create(tmp_path, "feat013", "FEAT-013", "a" * 40, FakeGitOps(head="a" * 40))

    with pytest.raises(RunCursorError):
        execution.open_cursor("dev")

    started = execution.begin_revision("dev")
    recorded = execution.record_stage(started, state="completed")

    with pytest.raises(RunCursorError):
        execution.record_stage(started)  # replay of the already-recorded evidence

    stale = GovernedStageCursor(
        stage_id="dev", revision=1, attempt=1,
        parent_event_sha256=recorded.parent_event_sha256,
        attempt_key=started.attempt_key,
    )
    execution.begin_attempt("dev")
    with pytest.raises(RunCursorError):
        execution.record_stage(stale)  # non-monotonic: attempt 1 after attempt 2 began

    current = execution.open_cursor("dev")
    forged_parent = GovernedStageCursor(
        stage_id="dev", revision=current.revision, attempt=current.attempt,
        parent_event_sha256="f" * 64, attempt_key=current.attempt_key,
    )
    with pytest.raises(RunCursorError):
        execution.record_stage(forged_parent)

    forged_key = GovernedStageCursor(
        stage_id="dev", revision=current.revision, attempt=current.attempt,
        parent_event_sha256=current.parent_event_sha256,
        attempt_key="feat013/FEAT-013/dev/r1/a9/v1",
    )
    with pytest.raises(RunCursorError):
        execution.record_stage(forged_key)

    unknown = GovernedStageCursor(
        stage_id="not-a-stage", revision=1, attempt=1, parent_event_sha256=None,
        attempt_key="feat013/FEAT-013/not-a-stage/r1/a1/v1",
    )
    with pytest.raises(RunCursorError):
        execution.record_stage(unknown)


def test_cursor_value_is_frozen_and_the_live_cursor_advances_the_parent_hash(
    tmp_path: Path,
) -> None:
    execution = RunExecution.create(tmp_path, "feat013", "FEAT-013", "a" * 40, FakeGitOps(head="a" * 40))
    started = execution.begin_revision("dev")

    assert started.parent_event_sha256 is None
    with pytest.raises(FrozenInstanceError):
        started.attempt = 2  # type: ignore[misc]

    recorded = execution.record_stage(started, state="completed")
    assert recorded.parent_event_sha256 is not None
    assert len(recorded.parent_event_sha256) == 64
    assert started.parent_event_sha256 is None  # evidence is never rewritten in place
    assert execution.stage_cursors["dev"] == recorded
