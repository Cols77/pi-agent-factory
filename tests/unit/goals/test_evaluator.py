"""Deterministic goal evaluator tests (spec AC-04, AC-07, §14)."""

import pytest
from pathlib import Path

from factory.goals.evaluator import OPS, evaluate
from factory.goals.schema import Goal

pytestmark = pytest.mark.unit


_MISSING = object()


def _goal(state="DECLARED", metric=_MISSING, target=_MISSING) -> Goal:
    return Goal(
        id="GOAL-NAV-003",
        title="Reacquisition accuracy",
        path=Path("goals/GOAL-NAV-003.md"),
        feature=["FEAT-NAV-017"],
        requirements=["SR-032"],
        metric=metric if metric is not _MISSING else {"name": "reacquisition_rate", "source_experiment": "SIM-047"},
        target=target if target is not _MISSING else {"operator": ">=", "value": 0.90},
        state=state,
    )


def _run(goal, value, **kw):
    return evaluate(
        goal,
        value,
        run_id=kw.get("run_id", "RUN-001"),
        commit=kw.get("commit", "abc123"),
        metrics_path=kw.get("metrics_path", Path("evidence/runs/x/metrics.json")),
    )


def test_ac04_at_or_above_target_is_reached():
    result = _run(_goal(), 0.93)
    assert result.passed is True
    assert result.state == "REACHED"
    assert result.value == 0.93
    assert result.target_value == 0.90
    assert result.operator == ">="


def test_first_below_target_is_not_reached():
    result = _run(_goal(state="NOT_REACHED"), 0.82)
    assert result.passed is False
    assert result.state == "NOT_REACHED"


def test_ac07_below_target_after_reached_is_regressed():
    result = _run(_goal(state="REACHED"), 0.82)
    assert result.passed is False
    assert result.state == "REGRESSED"


def test_below_target_from_declared_is_not_reached():
    # A goal that has never been REACHED cannot REGRESS.
    result = _run(_goal(), 0.82)
    assert result.state == "NOT_REACHED"


def test_evidence_bundle_records_experiment_run_commit_metrics_path():
    result = _run(_goal(), 0.93, run_id="RUN-demo1", commit="sha1", metrics_path=Path("m.json"))
    ev = result.evidence
    assert ev["experiment"] == "SIM-047"
    assert ev["run"] == "RUN-demo1"
    assert ev["commit"] == "sha1"
    assert ev["metrics_path"] == "m.json"
    assert ev["recorded_at"]  # presence only; the value is a wall-clock record


def test_missing_metric_is_blocked():
    result = _run(_goal(metric=None), 0.93)
    assert result.state == "BLOCKED"
    assert result.passed is False
    assert result.blocked_reason


def test_missing_source_experiment_is_blocked():
    result = _run(_goal(metric={"name": "reacquisition_rate"}), 0.93)
    assert result.state == "BLOCKED"
    assert "source_experiment" in (result.blocked_reason or "")


def test_unknown_target_operator_is_blocked():
    result = _run(_goal(target={"operator": "?=", "value": 0.9}), 0.93)
    assert result.state == "BLOCKED"


def test_non_numeric_target_value_is_blocked():
    result = _run(_goal(target={"operator": ">=", "value": "high"}), 0.93)
    assert result.state == "BLOCKED"


def test_all_operators_compare_correctly():
    assert OPS[">="](0.9, 0.9) and not OPS[">="](0.89, 0.9)
    assert OPS["<="](0.89, 0.9) and not OPS["<="](0.91, 0.9)
    assert OPS[">"](0.91, 0.9) and not OPS[">"](0.9, 0.9)
    assert OPS["<"](0.89, 0.9) and not OPS["<"](0.9, 0.9)
    assert OPS["=="](0.9, 0.9) and not OPS["=="](0.91, 0.9)


def test_boundary_equality_is_reached():
    # Exactly the target satisfies >= (AC-04 boundary).
    result = _run(_goal(), 0.90)
    assert result.passed is True
    assert result.state == "REACHED"
