from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from factory.freshness.model import FreshnessSeverity
from factory.requirements.register import Requirement, is_checksum_current


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
    # 1. Staleness always wins: a binding whose content has changed since it was
    # checksummed may no longer measure the statement it claims to, so nothing
    # downstream (evidence, deferral, plan) can be trusted until it is refreshed.
    if req.binding is not None and not is_checksum_current(req):
        return ClosureFinding(
            req_id=req.id,
            state=RequirementState.PENDING,
            severity=FreshnessSeverity.BLOCKING,
            detail=f"{req.id}: binding checksum is stale; re-bind to refresh it",
        )

    # 2. Evidence outranks a deferral: a requirement that has actually been
    # measured is closed by that fact, regardless of what else is set.
    if validation == "passing":
        return ClosureFinding(
            req_id=req.id,
            state=RequirementState.MEASURED_PASSING,
            severity=None,
            detail=f"{req.id}: measured passing",
        )
    if validation == "failing":
        # A failing measurement is still a healthy *closure* state: the
        # requirement is bound, current and genuinely measured. That the
        # system fails its own requirement is a fact for the validation
        # report to raise, not a defect in the register's structure.
        return ClosureFinding(
            req_id=req.id,
            state=RequirementState.MEASURED_FAILING,
            severity=None,
            detail=f"{req.id}: measured failing",
        )

    # 3. No named harness means there is no instrument to produce evidence with,
    # independent of whatever disposition (deferred/planned) is also on record.
    if req.binding is not None and req.binding.harness is None:
        return ClosureFinding(
            req_id=req.id,
            state=RequirementState.UNMEASURABLE,
            severity=FreshnessSeverity.WARNING,
            detail=f"{req.id}: binding names no harness yet",
        )

    # 4. A deliberate deferral is a healthy, named disposition.
    if deferred_reason:
        return ClosureFinding(
            req_id=req.id,
            state=RequirementState.DECLINED,
            severity=None,
            detail=f"{req.id}: deferred -- {deferred_reason}",
        )

    # 5. Work is underway but hasn't produced a result yet.
    if req.binding is not None and linked_task_status is not None and linked_task_status != "done":
        return ClosureFinding(
            req_id=req.id,
            state=RequirementState.PLANNED,
            severity=None,
            detail=f"{req.id}: linked task is {linked_task_status}",
        )

    # 6. Nothing accounts for this requirement's closure: not measured, not
    # deferred, and no work in flight (or work finished without a result).
    return ClosureFinding(
        req_id=req.id,
        state=RequirementState.PENDING,
        severity=FreshnessSeverity.BLOCKING,
        detail=f"{req.id}: no measurement, task, or deferral accounts for this requirement",
    )
