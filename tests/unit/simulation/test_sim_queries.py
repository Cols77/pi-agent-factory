"""`system.queries` simulation queries (Inc 3 Task 5, additive)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from factory.evidence.manifests import write_run_manifest
from factory.system.queries import (
    ScopeNotFoundError,
    query_latest_failure,
    query_latest_simulation,
    query_metric_history,
    query_simulation_run,
)

pytestmark = pytest.mark.unit


def sim_manifest(
    run: str,
    experiment: str = "SIM-047",
    feature: str = "FEAT-NAV-017",
    goals: list[str] | None = None,
    result: str = "passed",
    **extra,
) -> dict:
    manifest = {
        "run": run,
        "experiment": experiment,
        "feature": feature,
        "requirements": [],
        "goals": goals if goals is not None else ["GOAL-NAV-003"],
        "commit": run,
        "result": result,
    }
    manifest.update(extra)
    return manifest


def write_bundle(root: Path, manifest: dict, metrics: dict | None = None):
    path = write_run_manifest(root / "evidence", manifest)
    if metrics is not None:
        (path.parent / "metrics.json").write_text(
            json.dumps(metrics, indent=2), encoding="utf-8"
        )


def test_query_simulation_run_returns_one_run(tmp_path):
    write_bundle(tmp_path, sim_manifest("RUN-20260811-1702"))

    payload = query_simulation_run(tmp_path, "RUN-20260811-1702")

    assert payload["run"] == "RUN-20260811-1702"
    assert payload["experiment"] == "SIM-047"
    assert payload["feature"] == "FEAT-NAV-017"
    assert payload["goals"] == ["GOAL-NAV-003"]
    assert payload["result"] == "passed"


def test_query_simulation_run_carries_additive_metrics_and_recording(tmp_path):
    """Inc 6 Task 5: the run payload gains recorded metrics (metrics.json)
    and the recording link (the bundle manifest's repo-relative path). A run
    with no metrics.json degrades to an empty map, never a crash."""
    write_bundle(
        tmp_path,
        sim_manifest("RUN-20260811-1702", recorded_ts="2026-08-11T17:02:00Z"),
        {"target_reacquisition_rate": 0.93, "false_reacquisition_rate": 0.01},
    )
    write_bundle(tmp_path, sim_manifest("RUN-20260811-1800", result="failed"))

    payload = query_simulation_run(tmp_path, "RUN-20260811-1702")
    assert payload["metrics"] == {"target_reacquisition_rate": 0.93, "false_reacquisition_rate": 0.01}
    assert payload["recording"] == "evidence/runs/RUN-20260811-1702/manifest.json"
    assert payload["recorded_ts"] == "2026-08-11T17:02:00Z"

    bare = query_simulation_run(tmp_path, "RUN-20260811-1800")
    assert bare["metrics"] == {}
    assert bare["recording"] == "evidence/runs/RUN-20260811-1800/manifest.json"
    assert bare["recorded_ts"] is None


def test_query_simulation_run_unknown_raises(tmp_path):
    with pytest.raises(ScopeNotFoundError):
        query_simulation_run(tmp_path, "RUN-NOPE")


def test_query_latest_simulation_returns_most_recent_for_feature(tmp_path):
    write_bundle(tmp_path, sim_manifest("RUN-20260811-1000", result="failed"))
    write_bundle(tmp_path, sim_manifest("RUN-20260811-1100", result="passed"))

    payload = query_latest_simulation(tmp_path, "FEAT-NAV-017")

    assert payload["run"] == "RUN-20260811-1100"
    assert payload["result"] == "passed"


def test_query_latest_failure_returns_most_recent_non_passed(tmp_path):
    write_bundle(tmp_path, sim_manifest("RUN-20260811-1000", result="failed"))
    write_bundle(tmp_path, sim_manifest("RUN-20260811-1100", result="passed"))
    write_bundle(tmp_path, sim_manifest("RUN-20260811-1200", result="failed"))

    payload = query_latest_failure(tmp_path, "FEAT-NAV-017")

    assert payload["run"] == "RUN-20260811-1200"
    assert payload["result"] == "failed"


def test_query_latest_failure_none_when_all_passed(tmp_path):
    write_bundle(tmp_path, sim_manifest("RUN-20260811-1100", result="passed"))

    assert query_latest_failure(tmp_path, "FEAT-NAV-017") is None


def test_query_metric_history_ascending(tmp_path):
    for run, value in [
        ("RUN-20260811-1000", 0.71),
        ("RUN-20260811-1100", 0.83),
        ("RUN-20260811-1200", 0.87),
    ]:
        write_bundle(
            tmp_path,
            sim_manifest(run, recorded_ts=f"2026-08-11T{run[-6:-2]}:00:00Z"),
            metrics={"target_reacquisition_rate": value},
        )

    history = query_metric_history(tmp_path, "target_reacquisition_rate")

    assert [e["value"] for e in history] == [0.71, 0.83, 0.87]
