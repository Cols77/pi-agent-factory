from __future__ import annotations

import pytest

from factory.evidence.manifests import (
    list_run_manifests,
    load_run_manifest,
    write_run_manifest,
)

pytestmark = pytest.mark.unit


def sim_manifest(run: str = "RUN-20260811-1702") -> dict:
    """A spec §20 simulation run manifest (the seven SHALL-identify fields)."""
    return {
        "run": run,
        "experiment": "SIM-047",
        "feature": "FEAT-NAV-017",
        "requirements": ["NAV-REQ-021"],
        "goals": ["GOAL-NAV-003"],
        "commit": "f92b004",
        "result": "passed",
    }


def test_spec20_manifest_writes_then_loads_losslessly(tmp_path):
    root = tmp_path / "evidence"
    manifest = sim_manifest()

    path = write_run_manifest(root, manifest)

    assert path.name == "manifest.json"
    assert path.parent.name == "RUN-20260811-1702"
    loaded = load_run_manifest(path)
    assert loaded == manifest


def test_spec20_manifest_missing_optional_keys_is_default_safe(tmp_path):
    root = tmp_path / "evidence"
    manifest = sim_manifest()
    del manifest["feature"]
    del manifest["commit"]
    del manifest["result"]

    path = write_run_manifest(root, manifest)

    loaded = load_run_manifest(path)
    assert loaded["run"] == "RUN-20260811-1702"
    assert loaded["experiment"] == "SIM-047"
    assert loaded["feature"] is None
    assert loaded["goals"] == ["GOAL-NAV-003"]
    assert loaded["commit"] is None
    assert loaded["result"] is None


def test_spec20_manifest_unknown_fields_are_returned_untouched(tmp_path):
    root = tmp_path / "evidence"
    manifest = sim_manifest()
    manifest["sensor_sweep"] = {"hz": 50}  # newer key must survive, not break

    path = write_run_manifest(root, manifest)

    loaded = load_run_manifest(path)
    assert loaded["sensor_sweep"] == {"hz": 50}
    assert loaded["run"] == "RUN-20260811-1702"


def test_spec20_malformed_manifest_degrades_not_raises(tmp_path):
    # A malformed §20 manifest must never raise: it loads as a dict the
    # registry turns into a scope_errors-carrying Run (Task 2 contract).
    root = tmp_path / "evidence"
    bundle = root / "runs" / "RUN-20260811-1702"
    bundle.mkdir(parents=True)
    (bundle / "manifest.json").write_text('{"run": 42, "experiment": ', encoding="utf-8")

    with pytest.raises(ValueError):  # tolerated by the registry (Task 2)
        load_run_manifest(bundle / "manifest.json")


def test_v1_orchestration_manifest_without_spec20_keys_still_loads(tmp_path):
    root = tmp_path / "evidence"
    orchestration = {
        "schema_version": 2,
        "run_id": "run-orch-1",
        "task_id": "T-001",
        "started_at": "2026-08-07T12:00:00Z",
        "ended_at": "2026-08-07T12:01:00Z",
        "start_commit": "a" * 40,
        "result_commit": "b" * 40,
        "outcome": "completed",
        "inputs": {
            "task": {"path": "tasks/T-001.md", "sha256": "c" * 64},
            "requirements": [],
            "factory_config_sha256": "d" * 64,
        },
        "dependencies": [],
        "implementation": {
            "changed_files": ["src/a.py"],
            "patch": {"sha256": "e" * 64, "size": 12, "media_type": "text/x-diff"},
        },
        "validation": [],
        "reviews": [],
        "decisions": [],
        "publication": {"state": "local", "errors": []},
    }
    path = write_run_manifest(root, orchestration)

    assert path.name == "run-orch-1.json"  # flat file: v1 shape unchanged
    loaded = load_run_manifest(path)
    assert loaded["task_id"] == "T-001"
    assert loaded["run_id"] == "run-orch-1"


def test_list_finds_directory_bundles_and_flat_runs_side_by_side(tmp_path):
    root = tmp_path / "evidence"
    # Flat orchestration run (existing behaviour).
    orchestration = {
        "schema_version": 2,
        "run_id": "run-orch-1",
        "task_id": "T-001",
        "started_at": "2026-08-07T12:00:00Z",
        "ended_at": "2026-08-07T12:01:00Z",
        "start_commit": "a" * 40,
        "result_commit": "b" * 40,
        "outcome": "completed",
        "inputs": {
            "task": {"path": "tasks/T-001.md", "sha256": "c" * 64},
            "requirements": [],
            "factory_config_sha256": "d" * 64,
        },
        "dependencies": [],
        "implementation": {
            "changed_files": ["src/a.py"],
            "patch": {"sha256": "e" * 64, "size": 12, "media_type": "text/x-diff"},
        },
        "validation": [],
        "reviews": [],
        "decisions": [],
        "publication": {"state": "local", "errors": []},
    }
    write_run_manifest(root, orchestration)
    # Directory §20 bundle.
    write_run_manifest(root, sim_manifest("RUN-20260811-1702"))
    write_run_manifest(root, sim_manifest("RUN-20260811-1800"))

    runs = list_run_manifests(root)
    by_run = {item["run"] if "run" in item else item["run_id"]: item for item in runs}
    assert set(by_run) == {"run-orch-1", "RUN-20260811-1702", "RUN-20260811-1800"}
    assert by_run["RUN-20260811-1702"]["experiment"] == "SIM-047"


def test_list_with_task_filter_skips_spec20_runs(tmp_path):
    root = tmp_path / "evidence"
    orchestration = {
        "schema_version": 2,
        "run_id": "run-orch-1",
        "task_id": "T-001",
        "started_at": "2026-08-07T12:00:00Z",
        "ended_at": "2026-08-07T12:01:00Z",
        "start_commit": "a" * 40,
        "result_commit": "b" * 40,
        "outcome": "completed",
        "inputs": {
            "task": {"path": "tasks/T-001.md", "sha256": "c" * 64},
            "requirements": [],
            "factory_config_sha256": "d" * 64,
        },
        "dependencies": [],
        "implementation": {
            "changed_files": ["src/a.py"],
            "patch": {"sha256": "e" * 64, "size": 12, "media_type": "text/x-diff"},
        },
        "validation": [],
        "reviews": [],
        "decisions": [],
        "publication": {"state": "local", "errors": []},
    }
    write_run_manifest(root, orchestration)
    write_run_manifest(root, sim_manifest("RUN-20260811-1702"))

    runs = list_run_manifests(root, "T-001")
    assert [item["run_id"] for item in runs] == ["run-orch-1"]


def test_invalid_spec20_manifest_is_refused_at_write(tmp_path):
    bad = sim_manifest()
    del bad["experiment"]  # required by the §20 contract

    with pytest.raises(ValueError, match="invalid run manifest"):
        write_run_manifest(tmp_path / "evidence", bad)


def test_run_schema_json_exists_and_describes_spec20(tmp_path):
    import json as _json

    from factory.validation.schema_validator import SCHEMA_DIR

    schema = _json.loads((SCHEMA_DIR / "run.schema.json").read_text(encoding="utf-8"))
    assert "run" in schema["properties"]
    assert "experiment" in schema["properties"]
    assert "feature" in schema["properties"]
    assert "requirements" in schema["properties"]
    assert "goals" in schema["properties"]
    assert "commit" in schema["properties"]
    assert "result" in schema["properties"]
