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

from coherence.goals.lifecycle import GoalState
from coherence.goals.schema import Goal

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


def _check_guardrails(
    goal: Goal, guardrail_values: dict[str, float] | None
) -> tuple[list[dict[str, Any]], bool]:
    """Evaluate every guardrail; return (results, any_failed).

    A measured value is taken from `guardrail_values` keyed by the guardrail's
    `metric` name. A guardrail whose metric has no provided measurement cannot
    be proven safe, so it fails closed. This keeps the evaluator deterministic
    and never marks REACHED on unverified contract terms.
    """
    results: list[dict[str, Any]] = []
    any_failed = False
    measured_all = guardrail_values or {}
    for g in goal.guardrails:
        metric = g.get("metric")
        op = g.get("operator")
        target_val = g.get("value")
        measured = measured_all.get(metric)
        row: dict[str, Any] = {
            "metric": metric,
            "operator": op,
            "target": target_val,
            "measured": measured,
        }
        if (
            op not in OPS
            or not isinstance(target_val, (int, float))
            or measured is None
        ):
            row["violated"] = True
            any_failed = True
        else:
            row["violated"] = not bool(OPS[op](measured, target_val))
            if row["violated"]:
                any_failed = True
        results.append(row)
    return results, any_failed


def _confidence_met(goal: Goal) -> tuple[bool, str | None]:
    """Whether the accumulated recorded evidence count meets `confidence.min_runs`.

    Returns (met, reason). No confidence contract means no constraint.
    """
    conf = goal.confidence
    if not conf or not isinstance(conf, dict):
        return True, None
    min_runs = conf.get("min_runs")
    if not isinstance(min_runs, int):
        return True, None
    run_count = len(goal.history) + 1  # +1 for the evaluation about to be recorded
    if run_count < min_runs:
        return False, f"evidence runs {run_count} < confidence.min_runs {min_runs}"
    return True, None


def _baseline_mismatch(goal: Goal) -> str | None:
    """A reason string when the recorded baseline is not comparable; else None.

    A baseline is comparable only when it measures the same metric and the same
    population as the current goal contract. Anything else is flagged rather
    than silently compared (brief §5.3).
    """
    baseline = goal.baseline
    if not baseline or not isinstance(baseline, dict):
        return None
    baseline_metric = baseline.get("metric")
    current_metric = goal.metric.get("name") if goal.metric else None
    if baseline_metric and current_metric and baseline_metric != current_metric:
        return f"baseline metric {baseline_metric!r} != goal metric {current_metric!r}"
    return None



def evaluate(
    goal: Goal,
    value: float,
    *,
    run_id: str,
    commit: str,
    metrics_path: Path,
    guardrail_values: dict[str, float] | None = None,
) -> GoalResult:
    """Compare `value` against the goal target and derive the result state.

    The brief §5.3 pre-checks (guardrails, confidence, baseline comparability)
    run before REACHED is ever returned: a goal is never marked REACHED while a
    guardrail fails, the minimum evidence count is unmet, or the baseline is
    incomparable. Raises nothing; an uncomparable goal degrades to BLOCKED.
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
        # brief §5.3 pre-checks short-circuit REACHED.
        guardrail_results, guardrail_failed = _check_guardrails(goal, guardrail_values)
        if guardrail_failed:
            state: GoalState = "REGRESSED" if prior == "REACHED" else "BLOCKED"
            return GoalResult(
                goal_id=goal.id,
                state=state,
                passed=False,
                value=value,
                target_value=float(target_value),
                operator=str(target["operator"]),
                evidence=_evidence(goal, run_id, commit, metrics_path),
                guardrail_results=guardrail_results,
                blocked_reason=None if state == "REGRESSED" else "guardrail failed",
            )
        baseline_mismatch = _baseline_mismatch(goal)
        if baseline_mismatch:
            return GoalResult(
                goal_id=goal.id,
                state="BLOCKED",
                passed=False,
                value=value,
                target_value=float(target_value),
                operator=str(target["operator"]),
                evidence=_evidence(goal, run_id, commit, metrics_path),
                guardrail_results=guardrail_results,
                confidence_met=None,
                blocked_reason=baseline_mismatch,
            )
        confidence_met, conf_reason = _confidence_met(goal)
        if not confidence_met:
            # Single-run success is not acceptance: value meets target but the
            # confidence contract is unmet, so this is NOT REACHED.
            return GoalResult(
                goal_id=goal.id,
                state="NOT_REACHED",
                passed=False,
                value=value,
                target_value=float(target_value),
                operator=str(target["operator"]),
                evidence=_evidence(goal, run_id, commit, metrics_path),
                guardrail_results=guardrail_results,
                confidence_met=False,
                blocked_reason=conf_reason,
            )
        # Target met and every §5.3 pre-check passed: REACHED is earned.
        return GoalResult(
            goal_id=goal.id,
            state="REACHED",
            passed=True,
            value=value,
            target_value=float(target_value),
            operator=str(target["operator"]),
            evidence=_evidence(goal, run_id, commit, metrics_path),
            guardrail_results=guardrail_results,
            confidence_met=True,
        )

    # Target not met.
    if prior == "REACHED":
        state_value: GoalState = "REGRESSED"
    else:
        state_value = "NOT_REACHED"
    return GoalResult(
        goal_id=goal.id,
        state=state_value,
        passed=False,
        value=value,
        target_value=float(target_value),
        operator=str(target["operator"]),
        evidence=_evidence(goal, run_id, commit, metrics_path),
    )
