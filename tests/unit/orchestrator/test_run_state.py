import json
import pytest
from factory.orchestrator.run_state import read_last_run

pytestmark = pytest.mark.unit


def _write_mirror(repo_root, task_id, record):
    d = repo_root / "sessions" / ".factory-runs"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{task_id}.json").write_text(json.dumps(record), encoding="utf-8")


def test_read_last_run_returns_stop_point_with_reason(tmp_path):
    _write_mirror(tmp_path, "T-037", {
        "task_id": "T-037", "current_node": "dev", "current_state": "fail",
        "updated_at": "2026-07-28T11:08:16Z",
        "pipeline": [
            {"node": "context-gather", "node_state": "pass", "handoff": "→ dev", "outcome": None},
            {"node": "dev", "node_state": "fail", "handoff": "unit tests still red", "outcome": "escalated"},
        ],
    })
    assert read_last_run(tmp_path, "T-037") == {
        "node": "dev", "state": "fail", "outcome": "escalated",
        "handoff": "unit tests still red", "updated_at": "2026-07-28T11:08:16Z",
    }


def test_read_last_run_none_when_missing(tmp_path):
    assert read_last_run(tmp_path, "T-999") is None


def test_read_last_run_none_on_corrupt_file(tmp_path):
    d = tmp_path / "sessions" / ".factory-runs"
    d.mkdir(parents=True)
    (d / "T-1.json").write_text("{not json", encoding="utf-8")
    assert read_last_run(tmp_path, "T-1") is None


def test_read_last_run_handoff_none_when_no_matching_entry(tmp_path):
    _write_mirror(tmp_path, "T-2", {
        "task_id": "T-2", "current_node": "dev", "current_state": "running",
        "updated_at": "t", "pipeline": [],
    })
    got = read_last_run(tmp_path, "T-2")
    assert got == {"node": "dev", "state": "running", "outcome": None, "handoff": None, "updated_at": "t"}
