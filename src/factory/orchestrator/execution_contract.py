"""SR-034/SR-049 backend-neutral execution contract for one selected task.

One immutable :class:`ExecutionContract` binds a single run + task + workflow
version + workspace + configured fixer budget, and carries a canonical SHA-256
digest that can be attached to ``NodeEvent.extra`` and run evidence (SR-049).

:class:`WorkerAssignment` is the single lane -> role -> prompt mapping shared by
the driver and every host adapter, so no second mapping can drift. The closed
lane vocabulary is :data:`Lane`; the stage-id <-> review-lane mapping required
by decision 4 is :data:`STAGE_TO_LANE`.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, get_args

from factory.orchestrator.types import AgentRole

# The closed worker-lane vocabulary. Declared once; every signature that takes a
# lane uses this alias.
Lane = Literal["dev", "spec-review", "quality-review", "fixer"]

LANES: tuple[Lane, ...] = get_args(Lane)

# Decision 4: a stage id maps to exactly one review lane.
STAGE_TO_LANE: dict[str, Lane] = {
    "review-spec": "spec-review",
    "review-quality": "quality-review",
}
LANE_TO_STAGE: dict[Lane, str] = {lane: stage for stage, lane in STAGE_TO_LANE.items()}

# The one place a lane becomes a role.
_LANE_ROLE: dict[Lane, AgentRole] = {
    "dev": AgentRole.DEV,
    "spec-review": AgentRole.REVIEW,
    "quality-review": AgentRole.REVIEW,
    "fixer": AgentRole.DEV,
}

_LANE_INSTRUCTION: dict[Lane, str] = {
    "dev": "You are the DEV worker. Implement only the assigned task.",
    "spec-review": (
        "You are the SPEC-COMPLIANCE reviewer. Judge the change against the "
        "contract and the manifest; do not modify files."
    ),
    "quality-review": (
        "You are the CODE-QUALITY reviewer. Judge correctness, tests and "
        "style of the change; do not modify files."
    ),
    "fixer": "You are the FIXER. Apply only the fixes the reviews asked for.",
}


@dataclass(frozen=True)
class ExecutionContract:
    """Immutable binding of every execution input for one governed task."""

    run_id: str
    task_id: str
    workflow_version: str
    workspace: Path
    required_gates: tuple[str, ...]
    satisfies: tuple[str, ...]
    plan_ref: str | None
    spec_ref: str | None
    max_fixer_iterations: int
    contract_sha256: str

    @classmethod
    def build(cls, **values: object) -> ExecutionContract:
        normalized = _normalize_contract_values(values)
        digest = _sha256_canonical(_payload_from_values(normalized))
        return cls(**normalized, contract_sha256=digest)

    def rebuild_hash(self) -> str:
        """Recompute the digest from the stored inputs (never the stored hash)."""
        return _sha256_canonical(_payload_without_hash(self))

    def to_dict(self) -> dict[str, Any]:
        """Canonical, JSON-safe projection: ``schema: 1`` + every bound input."""
        return {"schema": 1, **_payload_without_hash(self), "contract_sha256": self.contract_sha256}


@dataclass(frozen=True)
class WorkerAssignment:
    """One worker lane bound to the shared absolute workspace and its prompt."""

    lane: Lane
    role: AgentRole
    prompt: str
    workspace: Path

    def __post_init__(self) -> None:
        if self.lane not in LANES:
            raise ValueError(f"unknown worker lane: {self.lane!r}")
        if not self.workspace.is_absolute():
            raise ValueError(f"workspace must be absolute: {self.workspace}")

    @classmethod
    def for_lane(cls, contract: ExecutionContract, lane: Lane, workspace: Path) -> WorkerAssignment:
        """The single lane -> role -> prompt construction path for driver and hosts."""
        if lane not in LANES:
            raise ValueError(f"unknown worker lane: {lane!r}")
        prompt = (
            f"{_LANE_INSTRUCTION[lane]}\n"
            f"RUN: {contract.run_id}\nTASK: {contract.task_id}\n"
            f"WORKFLOW: {contract.workflow_version}"
            f"{workspace_prompt_suffix(workspace, contract)}"
        )
        return cls(lane=lane, role=_LANE_ROLE[lane], prompt=prompt, workspace=workspace)


def workspace_prompt_suffix(workspace: Path, contract: ExecutionContract) -> str:
    """The one prompt suffix: same absolute workspace path and contract hash."""
    return (
        f"\n\nEXECUTION CONTRACT: {contract.contract_sha256}\n"
        f"SHARED WORKSPACE: {workspace.resolve().as_posix()}\n"
        "All assigned work must stay in this workspace."
    )


def _payload_from_values(values: dict[str, Any]) -> dict[str, Any]:
    """The canonical hashed payload from normalized values (workspace as posix str)."""
    workspace = values["workspace"]
    assert isinstance(workspace, Path)
    return {
        "run_id": values["run_id"],
        "task_id": values["task_id"],
        "workflow_version": values["workflow_version"],
        "workspace": workspace.resolve().as_posix(),
        "required_gates": list(values["required_gates"]),
        "satisfies": list(values["satisfies"]),
        "plan_ref": values["plan_ref"],
        "spec_ref": values["spec_ref"],
        "max_fixer_iterations": values["max_fixer_iterations"],
    }


def _payload_without_hash(contract: ExecutionContract) -> dict[str, Any]:
    """The hashed payload: sorted collections, absolute posix workspace, no digest."""
    return _payload_from_values(
        {
            "run_id": contract.run_id,
            "task_id": contract.task_id,
            "workflow_version": contract.workflow_version,
            "workspace": contract.workspace,
            "required_gates": contract.required_gates,
            "satisfies": contract.satisfies,
            "plan_ref": contract.plan_ref,
            "spec_ref": contract.spec_ref,
            "max_fixer_iterations": contract.max_fixer_iterations,
        }
    )


def _sha256_canonical(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _normalize_contract_values(values: dict[str, object]) -> dict[str, Any]:
    required = (
        "run_id",
        "task_id",
        "workflow_version",
        "workspace",
        "required_gates",
        "satisfies",
        "plan_ref",
        "spec_ref",
        "max_fixer_iterations",
    )
    missing = [name for name in required if name not in values]
    if missing:
        raise ValueError(f"missing contract values: {', '.join(sorted(missing))}")

    normalized: dict[str, Any] = {}
    for name in ("run_id", "task_id", "workflow_version"):
        value = values[name]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-blank string")
        normalized[name] = value

    workspace = values["workspace"]
    if not isinstance(workspace, Path):
        raise ValueError("workspace must be a pathlib.Path")
    if not workspace.is_absolute():
        raise ValueError(f"workspace must be absolute: {workspace}")
    normalized["workspace"] = workspace

    for name in ("required_gates", "satisfies"):
        raw = values[name]
        items = tuple(raw) if isinstance(raw, (tuple, list)) else None
        if items is None or any(not isinstance(item, str) or not item for item in items):
            raise ValueError(f"{name} must be a tuple of non-blank strings")
        if len(set(items)) != len(items):
            raise ValueError(f"{name} must not contain duplicates")
        normalized[name] = tuple(sorted(items))

    for name in ("plan_ref", "spec_ref"):
        value = values[name]
        if value is not None and not isinstance(value, str):
            raise ValueError(f"{name} must be a string or None")
        normalized[name] = value

    iterations = values["max_fixer_iterations"]
    if not isinstance(iterations, int) or isinstance(iterations, bool) or iterations <= 0:
        raise ValueError("max_fixer_iterations must be a positive int")
    normalized["max_fixer_iterations"] = iterations
    return normalized
