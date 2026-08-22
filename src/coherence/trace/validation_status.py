from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Literal, Protocol

SrState = Literal["passed", "failed", "error", "never_validated"]


class HasState(Protocol):
    @property
    def state(self) -> str: ...

REPORT_RELPATH = ("validation", "validation-report.json")


@dataclass(frozen=True)
class SrStatus:
    id: str
    state: SrState
    stale: bool = False
    metric: str | None = None
    value: float | None = None
    assert_expr: str | None = None
    trials: int | None = None
    declared_trials: int | None = None
    artifacts: list[str] = field(default_factory=list)
    error: str | None = None


def report_path(root: Path) -> Path:
    return root.joinpath(*REPORT_RELPATH)


def _entry_state(entry: dict) -> SrState:
    if entry.get("error"):
        return "error"
    return "passed" if entry.get("passed") else "failed"


def load_validation(root: Path) -> dict[str, SrStatus]:
    # A missing or unreadable report means "nothing has been validated", which is
    # never_validated for every SR -- not failed. Spec section 5.
    try:
        raw = json.loads(report_path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    statuses: dict[str, SrStatus] = {}
    for entry in raw.get("requirements", []):
        req_id = str(entry.get("id", ""))
        if not req_id:
            continue
        value = entry.get("value")
        statuses[req_id] = SrStatus(
            id=req_id,
            state=_entry_state(entry),
            stale=bool(entry.get("stale", False)),
            metric=entry.get("metric"),
            value=float(value) if isinstance(value, (int, float)) else None,
            assert_expr=entry.get("assert"),
            trials=entry.get("trials"),
            declared_trials=entry.get("declared_trials"),
            artifacts=[str(a) for a in entry.get("artifacts", [])],
            error=entry.get("error"),
        )
    return statuses


GoalValidation = Literal["VALIDATED", "REGRESSED", "VERIFICATION_PENDING", "VERIFICATION_STALE"]


def requirement_validation(
    goals: Iterable[HasState], *, stale: bool = False
) -> GoalValidation | None:
    """Derive a requirement's D5 goal-aware status from its goal states.

    Pure and derived -- never stored (spec §28). Rules, in priority order:

    * any goal in REGRESSED                    -> "REGRESSED"
    * every goal REACHED and ``stale``         -> "VERIFICATION_STALE" (spec §30)
    * every goal REACHED                       -> "VALIDATED"
    * goals exist, none reached, no regression -> "VERIFICATION_PENDING"
    * no goals                                 -> None (v1 behaviour unchanged)

    ``stale`` is the caller's recorded/live staleness signal (the register
    checksum / validation-report flag), passed in -- never re-derived here.

    The caller decides which goals belong to the requirement (via the goals'
    declared `requirements`/`demonstrates` bindings).
    """
    goal_states = [g.state for g in goals]
    if not goal_states:
        return None
    if "REGRESSED" in goal_states:
        return "REGRESSED"
    if all(state == "REACHED" for state in goal_states):
        return "VERIFICATION_STALE" if stale else "VALIDATED"
    return "VERIFICATION_PENDING"
