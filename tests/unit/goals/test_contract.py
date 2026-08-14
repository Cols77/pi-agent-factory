"""Measurable goal contract + guardrail gate tests (brief §5.3, Task 3b)."""

import pytest
from pathlib import Path

from factory.goals.evaluator import evaluate
from factory.goals.schema import Goal

pytestmark = pytest.mark.unit


def _goal(*, state="DECLARED", guardrails=None, confidence=None, baseline=None, metric=None, target=None, history=None) -> Goal:
    return Goal(
        id="GOAL-NAV-003",
        title="Reacquisition accuracy",
        path=Path("goals/GOAL-NAV-003.md"),
        feature=["FEAT-NAV-017"],
        requirements=["SR-032"],
        metric=metric or {"name": "reacquisition_rate", "source_experiment": "SIM-047"},
        target=target or {"operator": ">=", "value": 0.90},
        state=state,
        guardrails=guardrails or [],
        confidence=confidence,
        baseline=baseline,
        history=history or [],
    )


def _run(goal, value, **kw):
    return evaluate(
        goal,
        value,
        run_id=kw.get("run_id", "RUN-001"),
        commit=kw.get("commit", "abc123"),
        metrics_path=Path("evidence/runs/x/metrics.json"),
        guardrail_values=kw.get("guardrail_values"),
    )


_GUARDRAIL = {"metric": "false_reacquisition_rate", "operator": "<=", "value": 0.03}


def test_guardrail_failure_blocks_reached():
    g = _goal(guardrails=[_GUARDRAIL])
    result = _run(g, 0.93, guardrail_values={"false_reacquisition_rate": 0.05})
    assert result.passed is False
    assert result.state == "BLOCKED"
    assert result.blocked_reason == "guardrail failed"
    assert result.guardrail_results
    assert result.guardrail_results[0]["violated"] is True


def test_guardrail_met_allows_reached():
    g = _goal(guardrails=[_GUARDRAIL])
    result = _run(g, 0.93, guardrail_values={"false_reacquisition_rate": 0.02})
    assert result.passed is True
    assert result.state == "REACHED"
    assert result.guardrail_results[0]["violated"] is False


def test_guardrail_break_after_reached_regresses():
    g = _goal(state="REACHED", guardrails=[_GUARDRAIL])
    result = _run(g, 0.93, guardrail_values={"false_reacquisition_rate": 0.05})
    assert result.state == "REGRESSED"
    assert result.passed is False
    assert result.guardrail_results[0]["violated"] is True


def test_unverifiable_guardrail_fails_closed():
    # Guardrail metric never measured -> cannot prove safe -> not REACHED.
    g = _goal(guardrails=[{"metric": "unknown_rate", "operator": "<=", "value": 0.1}])
    result = _run(g, 0.93)
    assert result.state == "BLOCKED"
    assert result.guardrail_results[0]["violated"] is True


def test_single_run_under_confidence_is_not_reached():
    # Value meets target but confidence.min_runs=2 and only this run exists.
    g = _goal(confidence={"min_runs": 2, "ci_level": 0.95, "repeat_count": 1})
    result = _run(g, 0.93)
    assert result.state == "NOT_REACHED"  # never REACHED on single run
    assert result.confidence_met is False
    assert result.blocked_reason


def test_confidence_met_after_enough_runs_reaches():
    # One prior recorded run + this one meets min_runs=2.
    history = [{"state": "NOT_REACHED", "recorded_at": "2026-01-01T00:00:00+00:00"}]
    g = _goal(confidence={"min_runs": 2, "ci_level": 0.95, "repeat_count": 1}, history=history)
    result = _run(g, 0.93)
    assert result.state == "REACHED"
    assert result.confidence_met is True


def test_baseline_metric_mismatch_is_blocked_not_silent():
    g = _goal(
        metric={"name": "reacquisition_rate", "source_experiment": "SIM-047"},
        baseline={"metric": "precision", "value": 0.8, "commit": "aaa", "state": "NOT_REACHED"},
    )
    result = _run(g, 0.93)
    assert result.state == "BLOCKED"
    assert "baseline" in (result.blocked_reason or "")


def test_comparable_baseline_allows_reached():
    g = _goal(baseline={"metric": "reacquisition_rate", "value": 0.8, "commit": "aaa", "state": "DECLARED"})
    result = _run(g, 0.93)
    assert result.state == "REACHED"
    assert result.blocked_reason is None