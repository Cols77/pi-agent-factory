"""SR-034/SR-049 host-neutral transport projection of one compiled GatePlan.

The transport is a *projection*, never an owner: it receives an already-compiled
Coherence :class:`~coherence.execution.gate_plan.GatePlan` plus the bound
:class:`ExecutionContract` and the governed stage cursor, and returns a
deterministic, immutable root + stage-card projection for the selected transport
(``direct`` or ``hermes-kanban``).

It has no compiler, dispatch, durable-lifecycle, retry, heartbeat,
workspace-allocation or completion-status authority. When the selected transport
is Hermes Kanban, Hermes remains the operational owner: this module only
describes the cards. A retry materialises a new immutable projection for the
next attempt; a reclaim resumes the same attempt under its fencing rules.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal, get_args

from coherence.execution.gate_plan import CANONICAL_EXECUTION_STAGES, GatePlan, is_sha256
from factory.orchestrator.execution import GovernedStageCursor
from factory.orchestrator.execution_contract import ExecutionContract

# The closed transport vocabulary. Nothing else may carry a GatePlan.
TransportName = Literal["direct", "hermes-kanban"]
ALLOWED_TRANSPORTS: tuple[TransportName, ...] = get_args(TransportName)

# The transport that keeps Hermes as the operational owner of the cards.
_DURABLE_OWNER: dict[str, str] = {
    "direct": "factory-driver",
    "hermes-kanban": "hermes",
}


class TransportError(RuntimeError):
    """The transport cannot carry this contract/GatePlan/cursor combination."""


@dataclass(frozen=True)
class TransportCard:
    """One immutable stage card. Carries identity and the *current* attempt."""

    transport: str
    run_id: str
    task_id: str
    contract_sha256: str
    gate_plan_sha256: str
    workflow_version: str
    stage_id: str
    revision: int
    attempt: int
    attempt_key: str
    parent_event_sha256: str | None

    def metadata(self) -> tuple[Any, ...]:
        """The canonical stage metadata shared by every transport."""
        return (
            self.stage_id,
            self.revision,
            self.attempt,
            self.run_id,
            self.contract_sha256,
            self.gate_plan_sha256,
            self.workflow_version,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "transport": self.transport,
            "run_id": self.run_id,
            "task_id": self.task_id,
            "contract_sha256": self.contract_sha256,
            "gate_plan_sha256": self.gate_plan_sha256,
            "workflow_version": self.workflow_version,
            "stage_id": self.stage_id,
            "revision": self.revision,
            "attempt": self.attempt,
            "attempt_key": self.attempt_key,
            "parent_event_sha256": self.parent_event_sha256,
        }


@dataclass(frozen=True)
class TransportProjection:
    """One immutable, deterministic projection for one revision/attempt."""

    transport: str
    durable_owner: str
    root: TransportCard
    cards: tuple[TransportCard, ...]
    projection_sha256: str

    def __post_init__(self) -> None:
        expected = _projection_sha256(self.transport, self.durable_owner, self.cards)
        if self.projection_sha256 != expected:
            raise ValueError(
                "projection_sha256 does not match the projection's own cards "
                "(forged or stale identity)"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": 1,
            "transport": self.transport,
            "durable_owner": self.durable_owner,
            "root": self.root.to_dict(),
            "cards": [card.to_dict() for card in self.cards],
            "projection_sha256": self.projection_sha256,
        }


@dataclass(frozen=True)
class ExecutionTransport:
    """The selected transport: a pure, stateless GatePlan projector."""

    name: TransportName
    durable_owner: str

    def __post_init__(self) -> None:
        if self.name not in ALLOWED_TRANSPORTS:
            raise TransportError(
                f"unknown transport {self.name!r}; allowed: {', '.join(ALLOWED_TRANSPORTS)}"
            )

    @classmethod
    def for_transport(cls, transport: object) -> ExecutionTransport:
        if not isinstance(transport, str) or transport not in ALLOWED_TRANSPORTS:
            raise TransportError(
                f"unknown transport {transport!r}; allowed: {', '.join(ALLOWED_TRANSPORTS)}"
            )
        return cls(name=transport, durable_owner=_DURABLE_OWNER[transport])  # type: ignore[arg-type]

    def project(
        self,
        *,
        contract: ExecutionContract,
        gate_plan: GatePlan,
        cursor: GovernedStageCursor,
    ) -> TransportProjection:
        """Materialise the stage cards for one revision/attempt. Fail closed."""
        validated = validate_binding(contract=contract, gate_plan=gate_plan)
        if not isinstance(cursor, GovernedStageCursor):
            raise TransportError("materialize_transport requires a GovernedStageCursor")
        if cursor.stage_id not in CANONICAL_EXECUTION_STAGES:
            raise TransportError(f"cursor stage is not in the canonical graph: {cursor.stage_id!r}")
        if cursor.revision < 1 or cursor.attempt < 1:
            raise TransportError("a cursor revision and attempt must both be >= 1")

        cards = tuple(
            TransportCard(
                transport=self.name,
                run_id=validated.run_id,
                task_id=validated.task_id,
                contract_sha256=validated.contract_sha256,
                gate_plan_sha256=gate_plan.gate_plan_sha256,
                workflow_version=validated.workflow_version,
                stage_id=stage_id,
                revision=cursor.revision,
                attempt=cursor.attempt,
                attempt_key=cursor.attempt_key,
                parent_event_sha256=cursor.parent_event_sha256,
            )
            for stage_id in gate_plan.stages
        )
        return TransportProjection(
            transport=self.name,
            durable_owner=self.durable_owner,
            root=cards[0],
            cards=cards,
            projection_sha256=_projection_sha256(self.name, self.durable_owner, cards),
        )


def validate_binding(*, contract: ExecutionContract, gate_plan: GatePlan) -> ExecutionContract:
    """Reject a plan/contract hash mismatch *before* any stage card exists."""
    if not isinstance(gate_plan, GatePlan):
        raise TransportError("materialize_transport requires a compiled Coherence GatePlan")
    if not isinstance(contract, ExecutionContract):
        raise TransportError("materialize_transport requires an ExecutionContract")
    if contract.gate_plan_sha256 is None:
        raise TransportError(
            "contract is not bound to a gate plan; call ExecutionContract.with_gate_plan()"
        )
    if not is_sha256(contract.gate_plan_sha256):
        raise TransportError("contract gate_plan_sha256 is not a canonical digest")
    if contract.gate_plan_sha256 != gate_plan.gate_plan_sha256:
        raise TransportError(
            "plan/contract hash mismatch: the contract is bound to a different GatePlan "
            "(rejected before DEV)"
        )
    if contract.workflow_version != gate_plan.workflow_version:
        raise TransportError(
            "workflow version mismatch between the contract and the compiled GatePlan"
        )
    return contract


def materialize_transport(
    *,
    transport: object,
    contract: ExecutionContract,
    gate_plan: GatePlan,
    cursor: GovernedStageCursor,
) -> TransportProjection:
    """Project one already-compiled GatePlan through the selected transport."""
    return ExecutionTransport.for_transport(transport).project(
        contract=contract, gate_plan=gate_plan, cursor=cursor
    )


def _projection_sha256(
    transport: str, durable_owner: str, cards: tuple[TransportCard, ...]
) -> str:
    payload = {
        "schema": 1,
        "transport": transport,
        "durable_owner": durable_owner,
        "cards": [card.to_dict() for card in cards],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
