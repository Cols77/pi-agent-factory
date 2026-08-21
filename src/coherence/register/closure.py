from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from coherence.register.register import Requirement, is_checksum_current
from substrate.freshness.model import FreshnessSeverity


class RequirementState(str, Enum):
    MEASURED_PASSING = "measured-passing"
    MEASURED_FAILING = "measured-failing"
    PLANNED = "planned"
    UNMEASURABLE = "unmeasurable"
    DECLINED = "declined"
    PENDING = "pending"


@dataclass(frozen=True)
class ClosureFinding:
    req_id: str
    state: RequirementState
    # None for every healthy state: a healthy finding is not a problem report,
    # and giving it a severity would force every consumer to filter one out.
    severity: FreshnessSeverity | None
    detail: str


def classify(
    req: Requirement,
    *,
    validation: str | None,
    linked_task_status: str | None,
    deferred_reason: str | None,
) -> ClosureFinding:
    if req.binding is not None and not is_checksum_current(req):
        return ClosureFinding(
            req_id=req.id,
            state=RequirementState.PENDING,
            severity=FreshnessSeverity.BLOCKING,
            detail=f"{req.id}: binding checksum is stale; re-bind to refresh it",
        )

    if validation == "passing":
        return ClosureFinding(
            req_id=req.id,
            state=RequirementState.MEASURED_PASSING,
            severity=None,
            detail=f"{req.id}: measured passing",
        )
    if validation == "failing":
        return ClosureFinding(
            req_id=req.id,
            state=RequirementState.MEASURED_FAILING,
            severity=None,
            detail=f"{req.id}: measured failing",
        )

    if req.binding is not None and req.binding.harness is None:
        return ClosureFinding(
            req_id=req.id,
            state=RequirementState.UNMEASURABLE,
            severity=FreshnessSeverity.WARNING,
            detail=f"{req.id}: binding names no harness yet",
        )

    if deferred_reason:
        return ClosureFinding(
            req_id=req.id,
            state=RequirementState.DECLINED,
            severity=None,
            detail=f"{req.id}: deferred -- {deferred_reason}",
        )

    if req.binding is not None and linked_task_status is not None and linked_task_status != "done":
        return ClosureFinding(
            req_id=req.id,
            state=RequirementState.PLANNED,
            severity=None,
            detail=f"{req.id}: linked task is {linked_task_status}",
        )

    return ClosureFinding(
        req_id=req.id,
        state=RequirementState.PENDING,
        severity=FreshnessSeverity.BLOCKING,
        detail=f"{req.id}: no measurement, task, or deferral accounts for this requirement",
    )


__all__ = ["ClosureFinding", "RequirementState", "classify"]
