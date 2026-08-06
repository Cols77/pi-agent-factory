from __future__ import annotations

import json

import pytest

from factory.evidence.cli import main
from factory.evidence.manifests import write_run_manifest

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


def test_task_json_returns_newest_first(tmp_path, capsys):
    write_run_manifest(
        tmp_path / "evidence",
        manifest("old", "T-001", ended="2026-01-01T00:00:00Z"),
    )
    write_run_manifest(
        tmp_path / "evidence",
        manifest("new", "T-001", ended="2026-01-02T00:00:00Z"),
    )

    assert main(["task", "T-001", "--repo", str(tmp_path), "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert [item["run_id"] for item in payload["runs"]] == ["new", "old"]


def test_list_json_returns_every_task(tmp_path, capsys):
    write_run_manifest(tmp_path / "evidence", manifest("one", "T-001"))
    write_run_manifest(tmp_path / "evidence", manifest("two", "T-002"))

    assert main(["list", "--repo", str(tmp_path), "--json"]) == 0
    assert {item["task_id"] for item in json.loads(capsys.readouterr().out)["runs"]} == {
        "T-001",
        "T-002",
    }


def test_run_json_returns_exact_manifest(tmp_path, capsys):
    write_run_manifest(tmp_path / "evidence", manifest("run-1", "T-001"))

    assert main(["run", "run-1", "--repo", str(tmp_path), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["run_id"] == "run-1"


def test_missing_run_is_nonzero_and_stdout_stays_clean(tmp_path, capsys):
    assert main(["run", "gone", "--repo", str(tmp_path), "--json"]) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "not found" in captured.err


def test_run_id_cannot_escape_evidence_directory(tmp_path, capsys):
    assert main(["run", "../../secret", "--repo", str(tmp_path), "--json"]) == 2
    assert "invalid run id" in capsys.readouterr().err
