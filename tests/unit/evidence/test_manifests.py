from __future__ import annotations

import json

import pytest

from factory.evidence.manifests import (
    list_run_manifests,
    load_run_manifest,
    write_run_manifest,
)

pytestmark = pytest.mark.unit


def manifest(run_id: str = "run-1", task_id: str = "T-001", ended: str = "2026-08-07T12:01:00Z") -> dict:
    return {
        "schema_version": 2,
        "run_id": run_id,
        "task_id": task_id,
        "started_at": "2026-08-07T12:00:00Z",
        "ended_at": ended,
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


def test_manifest_round_trip_is_atomic_and_validated(tmp_path):
    path = write_run_manifest(tmp_path / "evidence", manifest())

    assert path.name == "run-1.json"
    assert load_run_manifest(path)["result_commit"] == "b" * 40
    assert not path.with_name(path.name + ".tmp").exists()


def test_invalid_manifest_is_refused(tmp_path):
    bad = manifest()
    del bad["task_id"]

    with pytest.raises(ValueError, match="invalid evidence manifest"):
        write_run_manifest(tmp_path / "evidence", bad)


def test_list_filters_by_task_sorts_newest_first_and_skips_corrupt_files(tmp_path):
    root = tmp_path / "evidence"
    write_run_manifest(root, manifest("run-old", "T-001", "2026-08-07T12:01:00Z"))
    write_run_manifest(root, manifest("run-new", "T-001", "2026-08-07T12:02:00Z"))
    write_run_manifest(root, manifest("run-other", "T-002", "2026-08-07T12:03:00Z"))
    (root / "runs" / "corrupt.json").write_text("not json", encoding="utf-8")

    assert [item["run_id"] for item in list_run_manifests(root, "T-001")] == [
        "run-new",
        "run-old",
    ]


def test_loader_migrates_v1_known_inputs_without_inventing_provenance(tmp_path):
    legacy = manifest()
    legacy["schema_version"] = 1
    del legacy["dependencies"]
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps(legacy), encoding="utf-8")
    loaded = load_run_manifest(path)
    assert loaded["schema_version"] == 2
    assert [item["name"] for item in loaded["dependencies"]] == [
        "factory-config", "task:T-001"
    ]
    assert all(item["kind"] == "file" for item in loaded["dependencies"])


def test_loader_migrates_version_less_legacy_manifest(tmp_path):
    """KB-0004: a manifest written before schema_version existed must not crash
    finalize with "schema_version: 2 was expected" -- it is treated as the
    legacy v1 shape and migrated, then schema-validated."""
    legacy = manifest()
    del legacy["schema_version"]
    del legacy["dependencies"]
    path = tmp_path / "legacy-v0.json"
    path.write_text(json.dumps(legacy), encoding="utf-8")

    loaded = load_run_manifest(path)

    assert loaded["schema_version"] == 2
    assert "task:T-001" in [item["name"] for item in loaded["dependencies"]]


def test_loader_rejects_unsupported_schema_versions_with_actionable_message(tmp_path):
    bad = manifest()
    bad["schema_version"] = 99
    path = tmp_path / "future.json"
    path.write_text(json.dumps(bad), encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported evidence manifest schema version: 99"):
        load_run_manifest(path)


def test_version_less_garbage_still_fails_schema_validation(tmp_path):
    """Migrating version-less manifests must not silently accept garbage: the
    migrated output is still validated against the v2 schema."""
    path = tmp_path / "garbage.json"
    path.write_text(json.dumps({"run_id": "run-1", "foo": 1}), encoding="utf-8")

    with pytest.raises(ValueError, match="invalid evidence manifest"):
        load_run_manifest(path)


def test_loader_rejects_non_object_json(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid evidence manifest"):
        load_run_manifest(path)


def test_blob_hash_shape_is_validated(tmp_path):
    bad = manifest()
    bad["implementation"]["patch"]["sha256"] = "short"

    with pytest.raises(ValueError, match="invalid evidence manifest"):
        write_run_manifest(tmp_path / "evidence", bad)
