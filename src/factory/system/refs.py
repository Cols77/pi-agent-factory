from __future__ import annotations

import re

# Trace `satisfies` edges name a bare `SR-146`; navigator scope refs are
# `sr:SR-146`. One mapping, in one place, so no call site invents its own.
_SR_ID = re.compile(r"^SR-\d+$")
_TASK_ID = re.compile(r"^T-\d+$")


def sr_ref_from_trace_id(raw: str) -> str | None:
    """`SR-146` or `sr:SR-146` -> `sr:SR-146`. Anything else -> None."""
    value = raw.strip()
    if value.startswith("sr:"):
        value = value[len("sr:"):]
    return f"sr:{value}" if _SR_ID.match(value) else None


def task_ref_from_trace_id(raw: str) -> str | None:
    """`T-059` or `task:T-059` -> `task:T-059`. Anything else -> None."""
    value = raw.strip()
    if value.startswith("task:"):
        value = value[len("task:"):]
    return f"task:{value}" if _TASK_ID.match(value) else None
