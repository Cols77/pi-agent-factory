"""SR-034 Coherence-owned immutable ``GatePlan`` compilation and validation.

The canonical execution graph, the gate vocabulary and the preflight policy are
compiled exactly once, here, into one immutable :class:`GatePlan` carrying a
deterministic SHA-256 identity. Every host, transport and driver *carries* that
already-compiled value; nothing outside this module may compile, widen or
re-order it.

Decision 5 (2026-09-11): SR-034 ships ``mandatory-only`` preflight. The
obligation/health variant waits on the FEAT-018 supply, so
:data:`CURRENT_AC8_DECISION_REF` is ``None`` and the ``ac8-obligation-health``
gate is rejected until a current reference exists -- AC-8 is never silently
adopted.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

SCHEMA = 1

# The fixed execution stage graph. Order is part of the identity: revisions,
# descendant invalidation and the transport card projection all read it.
CANONICAL_EXECUTION_STAGES: tuple[str, ...] = (
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
)

# The fixed canonical gate names (Task 4/5 run exactly these).
CANONICAL_GATES: tuple[str, ...] = ("unit", "integration", "full")

# The closed preflight-policy vocabulary shipped by SR-034.
PREFLIGHT_POLICIES: tuple[str, ...] = ("mandatory-only",)

# The AC-8 obligation/health gate and the reference that would make it current.
AC8_GATE = "ac8-obligation-health"
CURRENT_AC8_DECISION_REF: str | None = None

_HEX = set("0123456789abcdef")


class GatePlanError(RuntimeError):
    """A GatePlan could not be compiled: the request is not canonical."""


@dataclass(frozen=True)
class GatePlan:
    """Immutable, Coherence-owned compilation of one workflow's gate plan."""

    schema: int
    workflow_version: str
    version: str
    stages: tuple[str, ...]
    required_gates: tuple[str, ...]
    preflight_policy: str
    ac8_decision_ref: str | None
    gate_plan_sha256: str

    def __post_init__(self) -> None:
        expected = gate_plan_identity_sha256(
            workflow_version=self.workflow_version,
            version=self.version,
            stages=tuple(self.stages),
            required_gates=tuple(self.required_gates),
            preflight_policy=self.preflight_policy,
            ac8_decision_ref=self.ac8_decision_ref,
        )
        if self.gate_plan_sha256 != expected:
            raise ValueError(
                "gate_plan_sha256 does not match the plan's own payload (forged or stale identity)"
            )

    def rebuild_hash(self) -> str:
        """Recompute the identity from the stored inputs (never the stored hash)."""
        return gate_plan_identity_sha256(
            workflow_version=self.workflow_version,
            version=self.version,
            stages=tuple(self.stages),
            required_gates=tuple(self.required_gates),
            preflight_policy=self.preflight_policy,
            ac8_decision_ref=self.ac8_decision_ref,
        )

    def to_dict(self) -> dict[str, Any]:
        """Canonical, JSON-safe projection: ``schema`` + every compiled input."""
        return {
            "schema": self.schema,
            "workflow_version": self.workflow_version,
            "version": self.version,
            "stages": list(self.stages),
            "required_gates": list(self.required_gates),
            "preflight_policy": self.preflight_policy,
            "ac8_decision_ref": self.ac8_decision_ref,
            "gate_plan_sha256": self.gate_plan_sha256,
        }


def gate_plan_identity_sha256(
    *,
    workflow_version: str,
    version: str,
    stages: tuple[str, ...] | list[str],
    required_gates: tuple[str, ...] | list[str],
    preflight_policy: str,
    ac8_decision_ref: str | None,
) -> str:
    """The total identity function: canonical SHA-256 over the compiled payload.

    It validates nothing -- :func:`compile_gate_plan` is the validating entry
    point -- so a changed stage list, gate list or preflight policy always lands
    in a different identity instead of silently colliding.
    """
    payload = {
        "schema": SCHEMA,
        "workflow_version": workflow_version,
        "version": version,
        "stages": list(stages),
        "required_gates": list(required_gates),
        "preflight_policy": preflight_policy,
        "ac8_decision_ref": ac8_decision_ref,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compile_gate_plan(
    *,
    workflow_version: object,
    version: object,
    required_gates: object,
    preflight_policy: object,
    ac8_decision_ref: object = None,
    stages: object = CANONICAL_EXECUTION_STAGES,
) -> GatePlan:
    """Compile and validate one canonical, immutable GatePlan.

    Rejects any missing, extra, duplicated or reordered stage; any unknown or
    non-canonical gate; any unknown preflight policy; and the
    ``ac8-obligation-health`` gate unless its decision reference is current.
    """
    workflow = _required_text("workflow_version", workflow_version)
    plan_version = _required_text("version", version)
    policy = _required_text("preflight_policy", preflight_policy)
    if policy not in PREFLIGHT_POLICIES:
        raise GatePlanError(
            f"unknown preflight_policy {policy!r}; SR-034 ships {PREFLIGHT_POLICIES}"
        )

    canonical_stages = _canonical_stages(stages)
    gates = _canonical_gates(required_gates)

    ref = ac8_decision_ref
    if ref is not None and not isinstance(ref, str):
        raise GatePlanError("ac8_decision_ref must be a string or None")
    if AC8_GATE in gates:
        if CURRENT_AC8_DECISION_REF is None:
            raise GatePlanError(
                f"{AC8_GATE!r} is not compilable: no current AC-8 decision reference "
                "exists (decision 5 -- the FEAT-018 supply is unconfirmed)"
            )
        if ref != CURRENT_AC8_DECISION_REF:
            raise GatePlanError(
                f"{AC8_GATE!r} requires the current ac8_decision_ref "
                f"{CURRENT_AC8_DECISION_REF!r}; got {ref!r}"
            )

    digest = gate_plan_identity_sha256(
        workflow_version=workflow,
        version=plan_version,
        stages=canonical_stages,
        required_gates=gates,
        preflight_policy=policy,
        ac8_decision_ref=ref,
    )
    return GatePlan(
        schema=SCHEMA,
        workflow_version=workflow,
        version=plan_version,
        stages=canonical_stages,
        required_gates=gates,
        preflight_policy=policy,
        ac8_decision_ref=ref,
        gate_plan_sha256=digest,
    )


def _required_text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GatePlanError(f"{name} must be a non-blank string")
    return value.strip()


def _canonical_stages(stages: object) -> tuple[str, ...]:
    if not isinstance(stages, (tuple, list)):
        raise GatePlanError("stages must be a tuple of stage ids")
    items = tuple(stages)
    if any(not isinstance(item, str) or not item for item in items):
        raise GatePlanError("stages must be a tuple of non-blank stage ids")
    canonical = CANONICAL_EXECUTION_STAGES
    if len(set(items)) != len(items):
        raise GatePlanError("the execution stage graph must not duplicate a stage")
    missing = [stage for stage in canonical if stage not in items]
    if missing:
        raise GatePlanError(f"missing canonical execution stages: {', '.join(missing)}")
    extra = [stage for stage in items if stage not in canonical]
    if extra:
        raise GatePlanError(f"unknown execution stages: {', '.join(extra)}")
    if items != canonical:
        raise GatePlanError("the execution stage graph must not be reordered")
    return items


def _canonical_gates(required_gates: object) -> tuple[str, ...]:
    if not isinstance(required_gates, (tuple, list)):
        raise GatePlanError("required_gates must be a tuple of gate names")
    items = tuple(required_gates)
    if not items:
        raise GatePlanError("required_gates must not be empty")
    if any(not isinstance(item, str) or not item for item in items):
        raise GatePlanError("required_gates must be a tuple of non-blank gate names")
    if len(set(items)) != len(items):
        raise GatePlanError("required_gates must not contain duplicates")
    allowed = set(CANONICAL_GATES) | {AC8_GATE}
    unknown = [gate for gate in items if gate not in allowed]
    if unknown:
        raise GatePlanError(f"unknown gate names: {', '.join(unknown)}")
    return items


def is_sha256(value: object) -> bool:
    """True only for a lowercase 64-char hex digest."""
    return isinstance(value, str) and len(value) == 64 and set(value) <= _HEX
