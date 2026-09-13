from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from factory.orchestrator.execution_contract import ExecutionContract, WorkerAssignment
from factory.orchestrator.types import AgentRole

pytestmark = pytest.mark.unit


def test_contract_hash_is_stable_and_binds_all_execution_inputs(tmp_path: Path) -> None:
    contract = ExecutionContract.build(
        run_id="run-013",
        task_id="T-013",
        workflow_version="governed-execution/v1",
        workspace=tmp_path / "worktree",
        required_gates=("unit", "full"),
        satisfies=("SR-034", "SR-049"),
        plan_ref="docs/superpowers/plans/plan.md",
        spec_ref="docs/superpowers/specs/spec.md",
        max_fixer_iterations=2,
    )

    assert len(contract.contract_sha256) == 64
    assert contract.contract_sha256 == contract.rebuild_hash()
    assert contract.to_dict()["workspace"] == (tmp_path / "worktree").as_posix()


def test_contract_and_worker_assignment_are_frozen(tmp_path: Path) -> None:
    contract = ExecutionContract.build(
        run_id="run-013",
        task_id="T-013",
        workflow_version="v1",
        workspace=tmp_path,
        required_gates=("unit",),
        satisfies=(),
        plan_ref=None,
        spec_ref=None,
        max_fixer_iterations=1,
    )
    assignment = WorkerAssignment("spec-review", AgentRole.REVIEW, "prompt", tmp_path)

    with pytest.raises(FrozenInstanceError):
        contract.max_fixer_iterations = 2  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        assignment.workspace = Path("other")  # type: ignore[misc]


def test_build_rejects_blank_ids_duplicate_gates_and_relative_workspace(tmp_path: Path) -> None:
    base = {
        "run_id": "run-013",
        "task_id": "T-013",
        "workflow_version": "v1",
        "workspace": tmp_path,
        "required_gates": ("unit",),
        "satisfies": ("SR-034",),
        "plan_ref": None,
        "spec_ref": None,
        "max_fixer_iterations": 1,
    }

    with pytest.raises(ValueError):
        ExecutionContract.build(**{**base, "run_id": "  "})
    with pytest.raises(ValueError):
        ExecutionContract.build(**{**base, "required_gates": ("unit", "unit")})
    with pytest.raises(ValueError):
        ExecutionContract.build(**{**base, "satisfies": ("SR-034", "SR-034")})
    with pytest.raises(ValueError):
        ExecutionContract.build(**{**base, "workspace": Path("relative")})
    with pytest.raises(ValueError):
        ExecutionContract.build(**{**base, "max_fixer_iterations": 0})


def test_for_lane_is_the_one_lane_to_role_to_prompt_mapping(tmp_path: Path) -> None:
    contract = ExecutionContract.build(
        run_id="run-013",
        task_id="T-013",
        workflow_version="v1",
        workspace=tmp_path,
        required_gates=("unit",),
        satisfies=("SR-049",),
        plan_ref=None,
        spec_ref=None,
        max_fixer_iterations=1,
    )
    workspace = tmp_path / "worktree"

    dev = WorkerAssignment.for_lane(contract, "dev", workspace)
    fixer = WorkerAssignment.for_lane(contract, "fixer", workspace)
    spec_review = WorkerAssignment.for_lane(contract, "spec-review", workspace)
    quality_review = WorkerAssignment.for_lane(contract, "quality-review", workspace)

    assert dev.role is AgentRole.DEV
    assert fixer.role is AgentRole.DEV
    assert spec_review.role is AgentRole.REVIEW
    assert quality_review.role is AgentRole.REVIEW
    assert {a.lane for a in (dev, fixer, spec_review, quality_review)} == {
        "dev",
        "fixer",
        "spec-review",
        "quality-review",
    }
    assert all(a.workspace == workspace for a in (dev, fixer, spec_review, quality_review))
    for assignment in (dev, fixer, spec_review, quality_review):
        assert contract.contract_sha256 in assignment.prompt
        assert workspace.resolve().as_posix() in assignment.prompt
    with pytest.raises(ValueError):
        WorkerAssignment.for_lane(contract, "scheduler", workspace)  # type: ignore[arg-type]


def test_direct_construction_cannot_forge_or_invalidate_contract_identity(tmp_path: Path) -> None:
    # F1: the public constructor must enforce the same invariants as build()
    # and reject a stored contract_sha256 that does not match its own payload.
    bogus: dict[str, object] = {
        "run_id": "",
        "task_id": "",
        "workflow_version": "",
        "workspace": Path("rel"),
        "required_gates": ("a", "a"),
        "satisfies": ("b", "b"),
        "plan_ref": 5,
        "spec_ref": 5,
        "max_fixer_iterations": 0,
        "contract_sha256": "BOGUS",
    }
    with pytest.raises(ValueError):
        ExecutionContract(**bogus)  # type: ignore[arg-type]

    forged: dict[str, object] = {
        "run_id": "run-013",
        "task_id": "T-013",
        "workflow_version": "v1",
        "workspace": tmp_path,
        "required_gates": ("unit",),
        "satisfies": (),
        "plan_ref": None,
        "spec_ref": None,
        "max_fixer_iterations": 1,
        "contract_sha256": "BOGUS",
    }
    with pytest.raises(ValueError):
        ExecutionContract(**forged)  # type: ignore[arg-type]


def test_payload_builder_raises_a_real_exception_not_a_bare_assert(tmp_path: Path) -> None:
    # F4: an assert disappears under ``python -O``; the guard must be a real
    # exception so the behaviour is identical with and without optimisation.
    from factory.orchestrator.execution_contract import _payload_from_values

    with pytest.raises(ValueError):
        _payload_from_values(
            {
                "run_id": "run-013",
                "task_id": "T-013",
                "workflow_version": "v1",
                "workspace": str(tmp_path),  # deliberately not a pathlib.Path
                "required_gates": ("unit",),
                "satisfies": (),
                "plan_ref": None,
                "spec_ref": None,
                "max_fixer_iterations": 1,
            }
        )


def test_with_gate_plan_returns_a_new_frozen_contract_and_never_mutates_the_digest(
    tmp_path: Path,
) -> None:
    from coherence.execution.gate_plan import compile_gate_plan

    contract = ExecutionContract.build(
        run_id="run-013",
        task_id="T-013",
        workflow_version="governed-execution/v1",
        workspace=tmp_path / "worktree",
        required_gates=("unit", "full"),
        satisfies=("SR-034", "SR-049"),
        plan_ref=None,
        spec_ref=None,
        max_fixer_iterations=2,
    )
    gate_plan = compile_gate_plan(
        workflow_version=contract.workflow_version,
        version="behavior-change@1",
        required_gates=("unit", "full"),
        preflight_policy="mandatory-only",
    )

    assert contract.gate_plan_sha256 is None
    bound = contract.with_gate_plan(gate_plan)

    assert bound is not contract
    assert bound.gate_plan_sha256 == gate_plan.gate_plan_sha256
    assert bound.workflow_version == gate_plan.workflow_version
    assert bound.contract_sha256 == bound.rebuild_hash()
    assert bound.contract_sha256 != contract.contract_sha256
    assert bound.to_dict()["gate_plan_sha256"] == gate_plan.gate_plan_sha256

    # The unbound contract keeps its own identity: nothing was rewritten in place.
    assert contract.gate_plan_sha256 is None
    assert contract.contract_sha256 == contract.rebuild_hash()
    assert contract.to_dict()["gate_plan_sha256"] is None

    with pytest.raises(FrozenInstanceError):
        bound.contract_sha256 = "0" * 64  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        bound.gate_plan_sha256 = "0" * 64  # type: ignore[misc]


def test_with_gate_plan_rejects_a_forged_plan_or_a_divergent_workflow(tmp_path: Path) -> None:
    from coherence.execution.gate_plan import compile_gate_plan

    contract = ExecutionContract.build(
        run_id="run-013",
        task_id="T-013",
        workflow_version="governed-execution/v1",
        workspace=tmp_path,
        required_gates=("unit",),
        satisfies=(),
        plan_ref=None,
        spec_ref=None,
        max_fixer_iterations=1,
    )
    other_workflow = compile_gate_plan(
        workflow_version="governed-execution/v2",
        version="behavior-change@1",
        required_gates=("unit",),
        preflight_policy="mandatory-only",
    )

    with pytest.raises(ValueError):
        contract.with_gate_plan("not-a-gate-plan")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        contract.with_gate_plan(other_workflow)

    # A directly-constructed contract cannot forge a binding either.
    with pytest.raises(ValueError):
        ExecutionContract(
            run_id="run-013",
            task_id="T-013",
            workflow_version="governed-execution/v1",
            workspace=tmp_path,
            required_gates=("unit",),
            satisfies=(),
            plan_ref=None,
            spec_ref=None,
            max_fixer_iterations=1,
            contract_sha256="f" * 64,
            gate_plan_sha256="0" * 64,
        )
