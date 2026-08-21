# src/factory/coverage/gate.py
from __future__ import annotations

from enum import Enum
from typing import Mapping


class GateOutcome(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    DEGRADED = "degraded"


_GATE_FAIL_STATES = frozenset({"unlinked", "not_implemented", "dishonest"})
_GATE_WARN_STATES = frozenset({"suspect", "unmeasured"})


def run_gate(
    states: Mapping[str, tuple[str, list[str]]],
    tool_failures: list[dict],
) -> tuple[GateOutcome, list[str], list[str], list[str]]:
    """Evaluate gate rules.

    Returns (outcome, failed_srs, warned_srs, degraded_srs). Hard failures
    take precedence over degraded; a tool-failed 'unverified' SR is degraded
    rather than failed.
    """
    failed: list[str] = []
    warned: list[str] = []
    degraded: list[str] = []
    unverified_srs: list[str] = []

    for sr_id, (state, notes) in states.items():
        if state == "declined":
            continue
        if state in _GATE_FAIL_STATES:
            failed.append(sr_id)
        elif state in _GATE_WARN_STATES:
            warned.append(sr_id)
        elif state == "unverified":
            unverified_srs.append(sr_id)

    tool_failure_ids = {f.get("sr_id", "") for f in tool_failures if f.get("sr_id")}
    for sr_id in unverified_srs:
        if sr_id in tool_failure_ids:
            degraded.append(sr_id)
        else:
            failed.append(sr_id)

    if failed:
        return GateOutcome.FAIL, failed, warned, degraded
    if degraded:
        return GateOutcome.DEGRADED, [], warned, degraded
    return GateOutcome.PASS, [], warned, degraded
