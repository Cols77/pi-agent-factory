"""Pure, fail-closed lifecycle projection for guided planning."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, Mapping


EvidenceStatus = Literal["missing", "valid", "stale", "failed", "invalid", "unknown"]

_LEGAL_ACTION_IDS = (
    "author-requirements",
    "record-sr-consent",
    "author-spec",
    "author-plan",
    "review-spec",
    "review-plan",
    "run-planning-gates",
    "create-handoff",
    "inspect-handoff",
)
_ACTION_REGISTRY_HASH = hashlib.sha256("\n".join(_LEGAL_ACTION_IDS).encode()).hexdigest()


@dataclass(frozen=True)
class LifecycleEvidence:
    """Normalized, read-only lifecycle evidence supplied by a loader."""

    run_id: str
    state: str
    run_identity: Mapping[str, object]
    manifest_status: EvidenceStatus
    artifact_kinds: frozenset[str]
    consent_status: EvidenceStatus
    spec_review_status: EvidenceStatus
    plan_review_status: EvidenceStatus
    gate_status: EvidenceStatus
    handoff_status: EvidenceStatus
    unresolved_challenges: bool = False
    intent_status: EvidenceStatus = "valid"

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_identity", MappingProxyType(dict(self.run_identity)))
        object.__setattr__(self, "artifact_kinds", frozenset(self.artifact_kinds))


@dataclass(frozen=True)
class LifecycleProjection:
    """The single display-only action (or attributable block) for a run."""

    schema: int
    run_id: str
    blocked: bool
    reason: str | None
    state: str
    legal_next_actions: tuple[str, ...]
    starts_automatically: bool
    run_identity: Mapping[str, object]
    action_registry: Mapping[str, object]

    def __post_init__(self) -> None:
        if (
            len(self.legal_next_actions) > 1
            or any(action not in _LEGAL_ACTION_IDS for action in self.legal_next_actions)
            or self.starts_automatically is not False
            or (self.blocked and (not self.reason or self.legal_next_actions))
            or (not self.blocked and (self.reason is not None or not self.legal_next_actions))
        ):
            raise ValueError("lifecycle projection requires one display-only action or a block")
        object.__setattr__(self, "legal_next_actions", tuple(self.legal_next_actions))
        object.__setattr__(self, "run_identity", MappingProxyType(dict(self.run_identity)))
        object.__setattr__(self, "action_registry", MappingProxyType(dict(self.action_registry)))

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "run_id": self.run_id,
            "blocked": self.blocked,
            "reason": self.reason,
            "state": self.state,
            "legal_next_actions": list(self.legal_next_actions),
            "starts_automatically": self.starts_automatically,
            "run_identity": dict(self.run_identity),
            "action_registry": {
                "schema": self.action_registry["schema"],
                "legal_ids": list(_LEGAL_ACTION_IDS),
                "registry_hash": self.action_registry["registry_hash"],
            },
        }


def action_registry() -> Mapping[str, object]:
    return MappingProxyType({
        "schema": 1,
        "legal_ids": _LEGAL_ACTION_IDS,
        "registry_hash": _ACTION_REGISTRY_HASH,
    })


def _projection(evidence: LifecycleEvidence, action: str | None, reason: str | None) -> LifecycleProjection:
    return LifecycleProjection(
        schema=2,
        run_id=evidence.run_id,
        blocked=reason is not None,
        reason=reason,
        state=evidence.state,
        legal_next_actions=() if action is None else (action,),
        starts_automatically=False,
        run_identity=evidence.run_identity,
        action_registry=action_registry(),
    )


def _status_reason(status: EvidenceStatus, name: str) -> str | None:
    if status == "valid" or status == "missing":
        return None
    if status == "stale":
        return f"STALE_{name}"
    return f"{name}_{status.upper()}"


def project_lifecycle(evidence: LifecycleEvidence) -> LifecycleProjection:
    """Return one current action, or an explicit fail-closed lifecycle block.

    This function deliberately knows nothing about files, subprocesses, or
    writers.  Evidence loaders may gain richer validation over time without
    moving lifecycle sequencing into hosts or persistence code.
    """
    if evidence.unresolved_challenges:
        return _projection(evidence, None, "UNRESOLVED_CHALLENGE")
    if evidence.state not in {"capture", "intent_provisional"}:
        return _projection(evidence, None, "SESSION_NOT_READY")
    if evidence.intent_status != "valid":
        return _projection(evidence, None, "STALE_INTENT_SNAPSHOT")

    if evidence.handoff_status == "valid":
        return _projection(evidence, "inspect-handoff", None)
    if evidence.handoff_status != "missing":
        return _projection(evidence, None, _status_reason(evidence.handoff_status, "HANDOFF"))

    if evidence.manifest_status == "missing":
        return _projection(evidence, "author-requirements", None)
    manifest_reason = _status_reason(evidence.manifest_status, "ARTIFACT_MANIFEST")
    if manifest_reason is not None:
        return _projection(evidence, None, manifest_reason)
    if "requirements" not in evidence.artifact_kinds:
        return _projection(evidence, "author-requirements", None)

    if evidence.consent_status == "missing":
        return _projection(evidence, "record-sr-consent", None)
    consent_reason = _status_reason(evidence.consent_status, "REQUIREMENT_CONSENT")
    if consent_reason is not None:
        return _projection(evidence, None, consent_reason)
    if "spec" not in evidence.artifact_kinds:
        return _projection(evidence, "author-spec", None)
    if "plan" not in evidence.artifact_kinds:
        return _projection(evidence, "author-plan", None)

    if evidence.spec_review_status == "missing":
        return _projection(evidence, "review-spec", None)
    spec_review_reason = _status_reason(evidence.spec_review_status, "SPEC_REVIEW")
    if spec_review_reason is not None:
        return _projection(evidence, None, spec_review_reason)
    if evidence.plan_review_status == "missing":
        return _projection(evidence, "review-plan", None)
    plan_review_reason = _status_reason(evidence.plan_review_status, "PLAN_REVIEW")
    if plan_review_reason is not None:
        return _projection(evidence, None, plan_review_reason)
    if evidence.gate_status == "missing":
        return _projection(evidence, "run-planning-gates", None)
    gate_reason = _status_reason(evidence.gate_status, "PLANNING_GATES")
    if gate_reason is not None:
        return _projection(evidence, None, gate_reason)
    return _projection(evidence, "create-handoff", None)


__all__ = ["LifecycleEvidence", "LifecycleProjection", "project_lifecycle"]
