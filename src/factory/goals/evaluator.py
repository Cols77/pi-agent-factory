"""Deterministic goal evaluation (spec §14, AC-04/AC-07).

A goal is marked REACHED only by a deterministic metric comparison — no LLM,
no human judgement, no fuzzy match (spec §14). The evaluator compares a run's
metric value against the goal target, records the evidence bundle, and derives
the result state from the goal's prior recorded state:

- first time below target           -> NOT_REACHED
- below target after REACHED        -> REGRESSED
- at/above target                   -> REACHED
- uncomparable (missing metric or
  target contract)                  -> BLOCKED

Task 3b adds the measurable-contract pre-checks (guardrails, confidence,
baseline comparability) that run *before* the target comparison.
"""
from __future__ import annotations

import operator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from factory.goals.lifecycle import GoalState
from factory.goals.schema import Goal

OPS: dict[str, Callable[[float, float], bool]] = {
    ">=": operator.ge,
    "<=": operator.le,
    ">": operator.gt,
    "<": operator.lt,
    "==": operator.eq,
}


@dataclass(frozen=True)
class GoalResult:
    """Outcome of one deterministic evaluation (spec §15 evidence bundle)."""

    goal_id: str
    state: GoalState
    passed: bool
    value: float
    target_value: float | None
    operator: str | None
    evidence: dict[str, Any]
    guardrail_results: list[dict[str, Any]] = field(default_factory=list)
    confidence_met: bool | None = None
    blocked_reason: str | None = None


def _evidence(goal: Goal, run_id: str, commit: str, metrics_path: Path) -> dict[str, Any]:
    return {
        "experiment": goal.metric.get("source_experiment") if goal.metric else None,
        "run": run_id,
        "commit": commit,
        "metrics_path": str(metrics_path),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }


def _blocked(goal: Goal, value: float, run_id: str, commit: str, metrics_path: Path, reason: str) -> GoalResult:
    return GoalResult(
        goal_id=goal.id,
        state="BLOCKED",
        passed=False,
        value=value,
        target_value=None,
        operator=None,
        evidence=_evidence(goal, run_id, commit, metrics_path),
        blocked_reason=reason,
    )


def evaluate(
    goal: Goal,
    value: float,
    *,
    run_id: str,
    commit: str,
    metrics_path: Path,
) -> GoalResult:
    """Compare `value` against the goal target and derive the result state.

    Raises nothing: an uncomparable goal degrades to BLOCKED with a recorded
    reason, matching the registry's never-crash discipline.
    """
    if goal.metric is None or not goal.metric.get("name"):
        return _blocked(goal, value, run_id, commit, metrics_path, "metric missing or unnamed")
    if not goal.metric.get("source_experiment"):
        return _blocked(goal, value, run_id, commit, metrics_path, "metric source_experiment missing")
    target = goal.target
    if target is None or target.get("operator") not in OPS:
        return _blocked(goal, value, run_id, commit, metrics_path, "target operator missing or unknown")
    target_value = target.get("value")
    if not isinstance(target_value, (int, float)):
        return _blocked(goal, value, run_id, commit, metrics_path, "target value not a number")

    op = OPS[target["operator"]]
    passed = bool(op(value, target_value))
    prior = goal.state
    if passed:
        state: GoalState = "REACHED"
    else:
        state = "REGRESSED" if prior == "REACHED" else "NOT_REACHED"

    return GoalResult(
        goal_id=goal.id,
        state=state,
        passed=passed,
        value=value,
        target_value=float(target_value),
        operator=str(target["operator"]),
        evidence=_evidence(goal, run_id, commit, metrics_path),
    )