from __future__ import annotations

import json

import pytest

from factory.evidence.manifests import write_run_manifest
from factory.simulation.evidence import (
    evidence_for_goal,
    latest_failure,
    metric_history,
    metric_values,
)

pytestmark = pytest.mark.unit


def sim_manifest(
    run: str,
    experiment: str = "SIM-047",
    feature: str = "FEAT-NAV-017",
    requirements: list[str] | None = None,
    goals: list[str] | None = None,
    commit: str | None = "f92b004",
    result: str = "passed",
    recorded_ts: str | None = None,
) -> dict:
    manifest = {
        "run": run,
        "experiment": experiment,
        "feature": feature,
        "requirements": requirements or [],
        "goals": goals if goals is not None else ["GOAL-NAV-003"],
        "commit": commit,
        "result": result,
    }
    if recorded_ts is not None:
        manifest["recorded_ts"] = recorded_ts
    return manifest


def write_bundle(evidence_dir, manifest: dict, metrics: dict | None = None):
    path = write_run_manifest(evidence_dir, manifest)
    if metrics is not None:
        (path.parent / "metrics.json").write_text(
            json.dumps(metrics, indent=2), encoding="utf-8"
        )


def test_metric_values_extracts_flat_metric_entries(tmp_path):
    evidence = tmp_path / "evidence"
    write_bundle(evidence, sim_manifest("RUN-20260811-1702"), {
        "target_reacquisition_rate": 0.93,
        "false_reacquisition_rate": 0.01,
    })
    from factory.simulation.registry import load_runs

    values = metric_values(load_runs(evidence)[0], {
        "target_reacquisition_rate": 0.93,
        "false_reacquisition_rate": 0.01,
    })
    assert values == {
        "target_reacquisition_rate": 0.93,
        "false_reacquisition_rate": 0.01,
    }


def test_metric_history_is_ascending_and_deterministic(tmp_path):
    evidence = tmp_path / "evidence"
    # §9.3 style: 0.71 -> 0.83 -> 0.87 across three runs.
    for run, value in [
        ("RUN-20260811-1000", 0.71),
        ("RUN-20260811-1100", 0.83),
        ("RUN-20260811-1200", 0.87),
    ]:
        write_bundle(
            evidence,
            sim_manifest(run, recorded_ts=f"2026-08-11T{run[-6:-2]}:00:00Z"),
            {"target_reacquisition_rate": value},
        )

    history = metric_history(evidence, "target_reacquisition_rate")

    assert [entry["value"] for entry in history] == [0.71, 0.83, 0.87]
    assert [entry["run"] for entry in history] == [
        "RUN-20260811-1000",
        "RUN-20260811-1100",
        "RUN-20260811-1200",
    ]
    assert all({"run", "commit", "value", "ts"} <= set(entry) for entry in history)


def test_metric_history_uses_recorded_ts_not_mtime(tmp_path):
    import os

    evidence = tmp_path / "evidence"
    # Older run id but newer mtime: recorded_ts must win (never mtime).
    write_bundle(
        evidence,
        sim_manifest("RUN-20260811-1000", recorded_ts="2026-08-11T10:00:00Z"),
        {"target_reacquisition_rate": 0.71},
    )
    write_bundle(
        evidence,
        sim_manifest("RUN-20260811-1100", recorded_ts="2026-08-11T11:00:00Z"),
        {"target_reacquisition_rate": 0.83},
    )
    old_path = evidence / "runs" / "RUN-20260811-1000" / "manifest.json"
    new_path = evidence / "runs" / "RUN-20260811-1100" / "manifest.json"
    past = old_path.stat().st_mtime
    os.utime(new_path, (past - 100, past - 100))  # newest id gets oldest mtime

    history = metric_history(evidence, "target_reacquisition_rate")
    assert [entry["value"] for entry in history] == [0.71, 0.83]


def test_latest_failure_returns_most_recent_non_passed_run(tmp_path):
    evidence = tmp_path / "evidence"
    write_bundle(evidence, sim_manifest("RUN-20260811-1000", result="failed"))
    write_bundle(evidence, sim_manifest("RUN-20260811-1100", result="passed"))
    write_bundle(evidence, sim_manifest("RUN-20260811-1200", result="failed"))

    failure = latest_failure(evidence, "FEAT-NAV-017")

    assert failure is not None
    assert failure.run_id == "RUN-20260811-1200"


def test_latest_failure_returns_none_when_all_passed(tmp_path):
    evidence = tmp_path / "evidence"
    write_bundle(evidence, sim_manifest("RUN-20260811-1000", result="passed"))

    assert latest_failure(evidence, "FEAT-NAV-017") is None


def test_evidence_for_goal_finds_runs_listing_the_goal(tmp_path):
    evidence = tmp_path / "evidence"
    write_bundle(evidence, sim_manifest("RUN-1", goals=["GOAL-NAV-003"]))
    write_bundle(evidence, sim_manifest("RUN-2", goals=["GOAL-ALT-001"]))
    write_bundle(evidence, sim_manifest("RUN-3", goals=["GOAL-NAV-003", "GOAL-ALT-001"]))

    runs = evidence_for_goal(evidence, "GOAL-NAV-003")

    assert [r.run_id for r in runs] == ["RUN-1", "RUN-3"]
