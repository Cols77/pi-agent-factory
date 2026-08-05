from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

SrState = Literal["passed", "failed", "error", "never_validated"]

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
