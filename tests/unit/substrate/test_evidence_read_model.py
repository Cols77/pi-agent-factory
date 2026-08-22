from __future__ import annotations

import json
import warnings

import pytest
from substrate.evidence import model as evidence_model
from substrate.evidence import read as evidence_read
from substrate.evidence.model import MANIFEST_SCHEMA_VERSION, migrate_manifest
from substrate.evidence.read import list_run_manifests, load_run_manifest

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


def _write_via_canonical_writer(evidence_dir, manifest_dict):
    """Use the ONE canonical writer (factory.evidence.manifests.write_run_manifest)
    to produce the on-disk fixture, so substrate's reader is exercised against
    the real artifact shape the factory actually writes, not a hand-rolled one."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        from factory.evidence.manifests import write_run_manifest

    return write_run_manifest(evidence_dir, manifest_dict)


def test_substrate_exposes_no_write_function():
    """write_run_manifest is factory.evidence.manifests' alone; substrate.evidence
    must never grow a write path (Task 3's read/write split)."""
    for module in (evidence_model, evidence_read):
        write_like = [name for name in dir(module) if name.lower().startswith("write")]
        assert write_like == [], f"{module.__name__} exposes a write-shaped name: {write_like}"
    assert not hasattr(evidence_read, "write_run_manifest")
    assert not hasattr(evidence_model, "write_run_manifest")


def test_load_run_manifest_reads_back_the_canonical_writers_fixture(tmp_path):
    path = _write_via_canonical_writer(tmp_path / "evidence", manifest())

    assert path.name == "run-1.json"
    assert load_run_manifest(path)["result_commit"] == "b" * 40


def test_list_filters_by_task_sorts_newest_first_and_skips_corrupt_files(tmp_path):
    root = tmp_path / "evidence"
    _write_via_canonical_writer(root, manifest("run-old", "T-001", "2026-08-07T12:01:00Z"))
    _write_via_canonical_writer(root, manifest("run-new", "T-001", "2026-08-07T12:02:00Z"))
    _write_via_canonical_writer(root, manifest("run-other", "T-002", "2026-08-07T12:03:00Z"))
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
    path = tmp_path / "garbage.json"
    path.write_text(json.dumps({"run_id": "run-1", "foo": 1}), encoding="utf-8")

    with pytest.raises(ValueError, match="invalid evidence manifest"):
        load_run_manifest(path)


def test_loader_rejects_non_object_json(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid evidence manifest"):
        load_run_manifest(path)


def test_migrate_manifest_is_idempotent_at_the_current_schema_version():
    current = manifest()
    assert migrate_manifest(current) is current  # already v2: returned unchanged
    assert MANIFEST_SCHEMA_VERSION == 2


def test_factory_manifests_writer_calls_the_substrate_normaliser_and_still_validates(tmp_path):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        from factory.evidence.manifests import write_run_manifest

    bad = manifest()
    del bad["task_id"]
    with pytest.raises(ValueError, match="invalid evidence manifest"):
        write_run_manifest(tmp_path / "evidence", bad)


def test_write_run_manifest_is_still_the_only_writer_and_never_warns():
    """write_run_manifest is genuinely retained (not deprecated) under
    factory.evidence.manifests: importing it must NOT warn, unlike the
    load_run_manifest/list_run_manifests re-exports which did move."""
    import importlib
    import sys

    sys.modules.pop("factory.evidence.manifests", None)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        module = importlib.import_module("factory.evidence.manifests")
        write_run_manifest = module.write_run_manifest  # real attribute access

    assert [item for item in caught if item.category is DeprecationWarning] == []
    assert callable(write_run_manifest)

    # But load_run_manifest/list_run_manifests -- moved to substrate.evidence.read
    # -- DO warn when accessed through the legacy module (standard
    # warn-and-reexport shim idiom, same as factory.paths).
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        _ = module.load_run_manifest
        _ = module.list_run_manifests

    deprecation = [item for item in caught if item.category is DeprecationWarning]
    assert len(deprecation) == 2
