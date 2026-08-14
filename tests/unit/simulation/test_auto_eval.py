from __future__ import annotations

import json

import pytest

from factory.evidence.manifests import write_run_manifest
from factory.goals.registry import load_goal, load_goals
from factory.simulation.evidence import evaluate_goals_from_runs

pytestmark = pytest.mark.unit

GOAL_MD = """---
id: GOAL-NAV-003
title: Reacquisition accuracy on the NAV feature
feature: [FEAT-NAV-017]
requirements: [SR-032]
metric: {name: reacquisition_rate, source_experiment: SIM-047}
target: {operator: ">=", value: 0.90}
state: DECLARED
version: 1
confidence: {min_runs: 1, ci_level: 0.95, repeat_count: 1}
---

# GOAL-NAV-003

Auto-evaluation test goal.
"""


def make_goal(tmp_path, md: str = GOAL_MD):
    goals_dir = tmp_path / "goals"
    goals_dir.mkdir(parents=True, exist_ok=True)
    path = goals_dir / "GOAL-NAV-003.md"
    path.write_text(md, encoding="utf-8")
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
        json.dumps({"reacquisition_rate": value, "false_reacquisition_rate": 0.01}, indent=2),
        encoding="utf-8",
    )


def test_evaluate_goals_from_runs_flips_to_reached_and_records_evidence(tmp_path):
    goal_path = make_goal(tmp_path)
    evidence = tmp_path / "evidence"
    write_bundle(evidence, "RUN-20260811-1702", 0.93)

    results = evaluate_goals_from_runs(evidence, load_goals(tmp_path))

    assert len(results) == 1
    result = results[0]
    assert result.goal_id == "GOAL-NAV-003"
    assert result.state == "REACHED"
    assert result.value == 0.93
    # Evidence recorded into the goal file (Inc 2 record).
    updated = load_goal(goal_path)
    assert updated.state == "REACHED"
    assert updated.evidence and updated.evidence.get("run") == "RUN-20260811-1702"
    assert updated.history and updated.history[-1]["state"] == "REACHED"


def test_evaluate_goals_from_runs_regresses_after_lower_run(tmp_path):
    goal_path = make_goal(tmp_path)
    evidence = tmp_path / "evidence"
    write_bundle(evidence, "RUN-20260811-1702", 0.93)  # -> REACHED
    evaluate_goals_from_runs(evidence, load_goals(tmp_path))

    assert load_goal(goal_path).state == "REACHED"

    write_bundle(evidence, "RUN-20260811-1800", 0.82)  # -> REGRESSED (AC-07)
    results = evaluate_goals_from_runs(evidence, load_goals(tmp_path))

    assert [r.state for r in results] == ["REGRESSED"]
    assert load_goal(goal_path).state == "REGRESSED"


def test_evaluate_goals_uses_latest_passing_complete_run_for_experiment(tmp_path):
    make_goal(tmp_path)
    evidence = tmp_path / "evidence"
    write_bundle(evidence, "RUN-20260811-1000", 0.71, result="passed")
    write_bundle(evidence, "RUN-20260811-1100", 0.95, result="passed")

    results = evaluate_goals_from_runs(evidence, load_goals(tmp_path))

    assert [r.value for r in results] == [0.95]


def test_evaluate_goals_skips_when_no_matching_experiment_run(tmp_path):
    make_goal(tmp_path)
    # A run for a different experiment (SIM-999) bears no SIM-047 result.
    evidence = tmp_path / "evidence"
    write_run_manifest(evidence, {
        "run": "RUN-20260811-1702",
        "experiment": "SIM-999",
        "feature": "FEAT-NAV-017",
        "requirements": [],
        "goals": [],
        "commit": "c",
        "result": "passed",
    })

    assert evaluate_goals_from_runs(evidence, load_goals(tmp_path)) == []
