from __future__ import annotations

import pytest

from factory.evidence.manifests import write_run_manifest
from factory.simulation.registry import (
    Run,
    latest_run,
    load_runs,
    runs_for,
)

pytestmark = pytest.mark.unit


def sim_manifest(
    run: str = "RUN-20260811-1702",
    experiment: str = "SIM-047",
    feature: str = "FEAT-NAV-017",
    requirements: list[str] | None = None,
    goals: list[str] | None = None,
    commit: str | None = "f92b004",
    result: str = "passed",
) -> dict:
    return {
        "run": run,
        "experiment": experiment,
        "feature": feature,
        "requirements": requirements or [],
        "goals": goals if goals is not None else ["GOAL-NAV-003"],
        "commit": commit,
        "result": result,
    }


def seed(evidence_dir, *manifests):
    for manifest in manifests:
        write_run_manifest(evidence_dir, manifest)


def test_load_runs_parses_seed_manifests(tmp_path):
    evidence = tmp_path / "evidence"
    seed(evidence, sim_manifest())

    runs = load_runs(evidence)

    assert len(runs) == 1
    run = runs[0]
    assert isinstance(run, Run)
    assert run.run_id == "RUN-20260811-1702"
    assert run.experiment == "SIM-047"
    assert run.feature == "FEAT-NAV-017"
    assert run.requirements == []
    assert run.goals == ["GOAL-NAV-003"]
    assert run.commit == "f92b004"
    assert run.result == "passed"


def test_load_runs_returns_empty_list_on_empty_dir(tmp_path):
    assert load_runs(tmp_path / "evidence") == []


def test_runs_for_filters_by_each_dimension(tmp_path):
    evidence = tmp_path / "evidence"
    seed(
        evidence,
        sim_manifest("RUN-1", "SIM-047", "FEAT-NAV-017", requirements=["NAV-REQ-021"]),
        sim_manifest("RUN-2", "SIM-048", "FEAT-NAV-017", requirements=["NAV-REQ-022"]),
        sim_manifest("RUN-3", "SIM-047", "FEAT-ALT-001", goals=["GOAL-ALT-001"]),
    )

    assert [r.run_id for r in runs_for(evidence, feature="FEAT-NAV-017")] == [
        "RUN-1", "RUN-2",
    ]
    assert [r.run_id for r in runs_for(evidence, requirement="NAV-REQ-022")] == ["RUN-2"]
    assert [r.run_id for r in runs_for(evidence, experiment="SIM-047")] == ["RUN-1", "RUN-3"]
    assert [r.run_id for r in runs_for(evidence, goal="GOAL-ALT-001")] == ["RUN-3"]


def test_latest_run_is_deterministic_by_run_id(tmp_path):
    evidence = tmp_path / "evidence"
    seed(
        evidence,
        sim_manifest("RUN-20260811-1702"),
        sim_manifest("RUN-20260811-1800"),
        sim_manifest("RUN-20260811-1702", feature="FEAT-OTHER"),
    )

    latest = latest_run(evidence, "FEAT-NAV-017")
    assert latest is not None
    assert latest.run_id == "RUN-20260811-1800"


def test_latest_run_returns_none_on_empty(tmp_path):
    assert latest_run(tmp_path / "evidence", "FEAT-NAV-017") is None
