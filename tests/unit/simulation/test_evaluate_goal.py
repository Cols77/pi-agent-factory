from __future__ import annotations

import json

import pytest

from factory.evidence.manifests import write_run_manifest
from factory.goals.registry import load_goal, load_goals
from factory.simulation.evidence import (
    GoalNotFoundError,
    evaluate_goal_from_runs,
)

pytestmark = pytest.mark.unit

GOAL_META = (
    "---\n"
    "id: GOAL-NAV-003\n"
    "title: Reacquisition accuracy on the NAV feature\n"
    "feature: [FEAT-NAV-017]\n"
    "requirements: [SR-032]\n"
    "metric: {name: reacquisition_rate, source_experiment: SIM-047}\n"
    "target: {operator: \">=\", value: 0.90}\n"
    "version: 1\n"
)


def make_goal(tmp_path, state: str = "DECLARED"):
    goals_dir = tmp_path / "goals"
    goals_dir.mkdir(parents=True, exist_ok=True)
    body = GOAL_META + f"state: {state}\n" + "---\n\n# GOAL-NAV-003\n\nTest goal.\n"
    path = goals_dir / "GOAL-NAV-003.md"
    path.write_text(body, encoding="utf-8")
    return path


def write_bundle(evidence_dir, run: str, value: float, result: str = "passed"):
    manifest = {
        "run": run,
        "experiment": "SIM-047",
        "feature": "FEAT-NAV-017",
        "requirements": ["SR-032"],
        "goals": ["GOAL-NAV-003"],
        "commit": run,
        "result": result,
    }
    path = write_run_manifest(evidence_dir, manifest)
    (path.parent / "metrics.json").write_text(
        json.dumps({"reacquisition_rate": value}, indent=2),
        encoding="utf-8",
    )


def test_evaluate_goal_records_a_legal_transition_and_reports_it(tmp_path):
    goal_path = make_goal(tmp_path, state="EVALUATING")
    evidence = tmp_path / "evidence"
    write_bundle(evidence, "RUN-20260811-1702", 0.93)

    out = evaluate_goal_from_runs(evidence, load_goals(tmp_path), "GOAL-NAV-003")

    assert out["evaluated"] is True
    assert out["transition"] == {"from": "EVALUATING", "to": "REACHED", "legal": True}
    assert out["derived"]["passed"] is True
    assert out["derived"]["value"] == 0.93
    # State was actually persisted (the ONLY goal-state write path).
    assert load_goal(goal_path).state == "REACHED"
    assert load_goal(goal_path).evidence.get("run") == "RUN-20260811-1702"


def test_evaluate_goal_does_not_write_an_illegal_lifecycle_edge(tmp_path):
    # From DECLARED, spec §13 only permits ACTIVE -- a derived REACHED must
    # not be written.
    goal_path = make_goal(tmp_path, state="DECLARED")
    evidence = tmp_path / "evidence"
    write_bundle(evidence, "RUN-20260811-1702", 0.93)

    out = evaluate_goal_from_runs(evidence, load_goals(tmp_path), "GOAL-NAV-003")

    assert out["evaluated"] is False
    assert out["transition"] is None
    assert out["derived"]["state"] == "REACHED"
    assert "not a legal transition" in out["note"]
    assert load_goal(goal_path).state == "DECLARED"  # untouched


def test_evaluate_goal_with_no_measurable_run_is_a_reported_noop(tmp_path):
    goal_path = make_goal(tmp_path, state="EVALUATING")
    evidence = tmp_path / "evidence"
    # A run for a different experiment carries no SIM-047 metric.
    write_run_manifest(
        evidence,
        {
            "run": "RUN-20260811-1702",
            "experiment": "SIM-999",
            "feature": "FEAT-NAV-017",
            "requirements": [],
            "goals": ["GOAL-NAV-003"],
            "commit": "c",
            "result": "passed",
        },
    )

    out = evaluate_goal_from_runs(evidence, load_goals(tmp_path), "GOAL-NAV-003")

    assert out["evaluated"] is False
    assert out["transition"] is None
    assert "no measurable run" in out["note"]
    assert load_goal(goal_path).state == "EVALUATING"  # untouched


def test_evaluate_goal_raises_when_goal_does_not_exist(tmp_path):
    with pytest.raises(GoalNotFoundError):
        evaluate_goal_from_runs(tmp_path / "evidence", load_goals(tmp_path), "GOAL-NOPE")
