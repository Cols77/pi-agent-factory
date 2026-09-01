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


# --- Review round 3, Important 5 ---------------------------------------
#
# `load_runs` skipped any manifest without a "run" key. The repository's
# first recorded evidence (T-6) is a v1 orchestration manifest keyed
# `run_id`, written as a flat `evidence/runs/<run_id>.json` rather than a
# `RUN-<ts>/manifest.json` bundle. It loads fine through
# `list_run_manifests`, so `register check` sees it -- but it never reached
# the registry, so `freshness_universe` stayed empty and `evidence_freshness`
# read 0/0: the first evidence this repo ever recorded could not be reported
# stale, because it was not in the universe that staleness is measured over.


def _write_v1_manifest(evidence_dir, run_id="T-6-evidence-execution-20260901T114021Z"):
    import json

    runs = evidence_dir / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    path = runs / f"{run_id}.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "run_id": run_id,
                "task_id": "T-6",
                "started_at": "2026-09-01T11:40:21Z",
                "ended_at": "2026-09-01T11:40:28Z",
                "start_commit": "44d585a5a0898ed52b8aa296b387cac3c948120b",
                "result_commit": "44d585a5a0898ed52b8aa296b387cac3c948120b",
                "outcome": "completed",
                "inputs": {
                    "task": {"path": "tasks/T-6.md", "sha256": "0" * 64},
                    "requirements": [],
                    "factory_config_sha256": "0" * 64,
                },
                "dependencies": [],
                "implementation": {
                    "changed_files": [],
                    "patch": {"sha256": "0" * 64, "size": 0, "media_type": "text/x-diff"},
                },
                "validation": [],
                "reviews": [],
                "decisions": [],
                "publication": {"state": "local", "errors": []},
            }
        ),
        encoding="utf-8",
    )
    return path


def test_load_runs_sees_a_v1_manifest_keyed_run_id(tmp_path):
    evidence = tmp_path / "evidence"
    path = _write_v1_manifest(evidence)

    runs = load_runs(evidence)

    assert [r.run_id for r in runs] == ["T-6-evidence-execution-20260901T114021Z"]
    run = runs[0]
    assert run.path == path, "the flat-file layout must resolve to the real file"
    assert run.scope_errors == [], "a v1 manifest declares no experiment; that is not an error"
    assert run.commit == "44d585a5a0898ed52b8aa296b387cac3c948120b"
    assert run.result == "completed"
    assert run.recorded_ts == "2026-09-01T11:40:28Z"


def test_a_spec20_bundle_missing_its_experiment_still_reports_a_scope_error(tmp_path):
    """The v1 accommodation must not blunt the §20 bundle's own checks."""
    import json

    evidence = tmp_path / "evidence"
    manifest = sim_manifest()
    del manifest["experiment"]
    # Written directly: `write_run_manifest` validates on write, and the point
    # here is what the tolerant READER does with a bundle already on disk.
    bundle = evidence / "runs" / manifest["run"]
    bundle.mkdir(parents=True, exist_ok=True)
    (bundle / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    runs = load_runs(evidence)

    assert runs[0].scope_errors == ["experiment: not a string"]


def test_both_manifest_shapes_load_side_by_side(tmp_path):
    evidence = tmp_path / "evidence"
    seed(evidence, sim_manifest())
    _write_v1_manifest(evidence)

    assert len(load_runs(evidence)) == 2
