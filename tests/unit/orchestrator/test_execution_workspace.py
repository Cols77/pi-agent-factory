from __future__ import annotations

import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

import pytest

from factory.orchestrator.execution_contract import ExecutionContract
from factory.orchestrator.execution_workspace import (
    BoundExecution,
    WorkspaceLease,
    build_write_policy,
    workspace_prompt_suffix,
)

pytestmark = pytest.mark.unit


class _FakeBackend:
    """Stands in for the unchanged AgentBackend protocol."""

    def run(self, role, prompt, on_snippet=None, on_session_id=None):  # pragma: no cover
        raise AssertionError("not exercised in this test")


@dataclass
class RecordingWorkspaceOwner:
    root: Path
    acquired: list[str] = field(default_factory=list)
    released: list[str] = field(default_factory=list)

    @contextmanager
    def acquire(self, contract: ExecutionContract) -> Iterator[WorkspaceLease]:
        self.acquired.append(contract.run_id)
        try:
            yield WorkspaceLease(
                execution_id=contract.run_id,
                path=self.root,
                policy=build_write_policy(self.root),
            )
        finally:
            self.released.append(contract.run_id)


class RecordingBackendFactory:
    def __init__(self) -> None:
        self.bound_paths: list[Path] = []
        self.bound_policies: list[object] = []

    def bind(self, lease: WorkspaceLease, contract: ExecutionContract) -> BoundExecution:
        self.bound_paths.append(lease.path)
        self.bound_policies.append(lease.policy)
        return BoundExecution(
            backend=_FakeBackend(),
            contract=contract,
            workspace=lease.path,
            policy=lease.policy,
        )


def contract_fixture(workspace: Path) -> ExecutionContract:
    return ExecutionContract.build(
        run_id="run-013",
        task_id="T-013",
        workflow_version="governed-execution/v1",
        workspace=workspace,
        required_gates=("unit",),
        satisfies=("SR-034", "SR-049"),
        plan_ref="docs/superpowers/plans/plan.md",
        spec_ref="docs/superpowers/specs/spec.md",
        max_fixer_iterations=2,
    )


def test_driver_dependencies_can_bind_all_worker_roles_to_one_lease(tmp_path: Path) -> None:
    owner = RecordingWorkspaceOwner(tmp_path / "execution-worktree")
    factory = RecordingBackendFactory()
    contract = contract_fixture(tmp_path / "execution-worktree")

    with owner.acquire(contract) as lease:
        bound = factory.bind(lease, contract)
        assignments = [
            bound.assignment("dev"),
            bound.assignment("spec-review"),
            bound.assignment("quality-review"),
            bound.assignment("fixer"),
        ]

    assert owner.acquired == ["run-013"]
    assert owner.released == ["run-013"]
    assert {item.workspace for item in assignments} == {lease.path}
    assert factory.bound_paths == [lease.path]
    assert lease.policy.deny_outside_roots == (lease.path.resolve(),)
    assert Path(tempfile.gettempdir()).resolve() in lease.policy.allowed_roots
    assert factory.bound_policies == [lease.policy]
    assert lease.policy.on_denied == "deny-and-evidence"


def test_write_policy_has_exactly_one_legal_denial_mode(tmp_path: Path) -> None:
    policy = build_write_policy(tmp_path / "worktree")

    assert policy.on_denied == "deny-and-evidence"
    with pytest.raises(ValueError):
        build_write_policy(tmp_path / "worktree", on_denied="fail-task")


def test_policy_carve_outs_are_absolute_and_workspace_identity_is_in_evidence(tmp_path: Path) -> None:
    workspace = tmp_path / "worktree"
    lease = WorkspaceLease(execution_id="run-013", path=workspace, policy=build_write_policy(workspace))
    contract = contract_fixture(workspace)

    assert all(root.is_absolute() for root in lease.policy.allowed_roots)
    assert lease.execution_id == "run-013"
    suffix = workspace_prompt_suffix(workspace, contract)
    assert contract.contract_sha256 in suffix
    assert workspace.resolve().as_posix() in suffix


def test_binding_fails_closed_when_lease_workspace_disagrees_with_contract(tmp_path: Path) -> None:
    # F2: the increment's title property -- workspace agreement -- must be
    # enforced on the binding and on the factory's bind, not merely documented.
    contract = contract_fixture(tmp_path / "contract-ws")
    lease = WorkspaceLease(
        execution_id="run-013",
        path=tmp_path / "lease-ws",
        policy=build_write_policy(tmp_path / "lease-ws"),
    )

    with pytest.raises(ValueError):
        BoundExecution(
            backend=_FakeBackend(),
            contract=contract,
            workspace=lease.path,
            policy=lease.policy,
        )

    from factory.orchestrator.pi_backend import PiBackendFactory

    with pytest.raises(ValueError):
        PiBackendFactory(tmp_path, tmp_path / "ext.ts").bind(lease, contract)


def test_workspace_lease_rejects_a_non_string_execution_id_with_value_error(tmp_path: Path) -> None:
    # F3: an invalid id must raise a clean ValueError, not AttributeError.
    from typing import Any

    bad_id: Any = 5
    with pytest.raises(ValueError):
        WorkspaceLease(
            execution_id=bad_id, path=tmp_path, policy=build_write_policy(tmp_path)
        )
