import json
import pytest
from factory.orchestrator.run_state import read_last_run

pytestmark = pytest.mark.unit


def _write_mirror(repo_root, task_id, record):
    d = repo_root / "sessions" / ".factory-runs"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{task_id}.json").write_text(json.dumps(record), encoding="utf-8")


def _write_global(repo_root, record):
    d = repo_root / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    (d / ".factory-status.json").write_text(json.dumps(record), encoding="utf-8")


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


def test_read_last_run_outcome_is_last_non_null_across_pipeline(tmp_path):
    # Two non-null outcomes: the LAST wins. And a trailing null must NOT erase it.
    _write_mirror(tmp_path, "T-3", {
        "task_id": "T-3", "current_node": "review", "current_state": "changes-requested",
        "updated_at": "t",
        "pipeline": [
            {"node": "dev", "node_state": "pass", "handoff": None, "outcome": "escalated"},
            {"node": "validation", "node_state": "pass", "handoff": None, "outcome": "completed"},
            {"node": "review", "node_state": "changes-requested", "handoff": "2 findings", "outcome": None},
        ],
    })
    got = read_last_run(tmp_path, "T-3")
    assert got["outcome"] == "completed"  # last non-null, not the trailing None
    assert got["handoff"] == "2 findings"  # from the current_node (review) entry


def test_read_last_run_none_when_top_level_not_a_dict(tmp_path):
    d = tmp_path / "sessions" / ".factory-runs"
    d.mkdir(parents=True)
    (d / "T-4.json").write_text("[1, 2, 3]", encoding="utf-8")
    assert read_last_run(tmp_path, "T-4") is None


def test_read_last_run_tolerates_non_list_pipeline(tmp_path):
    _write_mirror(tmp_path, "T-5", {
        "task_id": "T-5", "current_node": "dev", "current_state": "running",
        "updated_at": "t", "pipeline": "oops-not-a-list",
    })
    # Must not raise; pipeline treated as empty -> outcome/handoff None.
    assert read_last_run(tmp_path, "T-5") == {
        "node": "dev", "state": "running", "outcome": None, "handoff": None, "updated_at": "t",
    }


def test_read_last_run_falls_back_to_global_status_when_no_mirror(tmp_path):
    # No per-task mirror (e.g. a run that predates per-task mirroring, or a
    # mirror write that failed while the global write succeeded). The global
    # status slot holds the most-recent run -- if it's THIS task, use it.
    _write_global(tmp_path, {
        "task_id": "T-037", "current_node": "dev", "current_state": "fail",
        "updated_at": "2026-07-28T11:08:16Z",
        "pipeline": [
            {"node": "dev", "node_state": "fail", "handoff": "unit tests still red", "outcome": "escalated"},
        ],
    })
    assert read_last_run(tmp_path, "T-037") == {
        "node": "dev", "state": "fail", "outcome": "escalated",
        "handoff": "unit tests still red", "updated_at": "2026-07-28T11:08:16Z",
    }


def test_read_last_run_ignores_global_status_for_a_different_task(tmp_path):
    # The global slot holds a DIFFERENT task than the one asked about -> no
    # fallback (we must not misattribute another task's run to this one).
    _write_global(tmp_path, {
        "task_id": "T-999", "current_node": "dev", "current_state": "fail",
        "updated_at": "t", "pipeline": [],
    })
    assert read_last_run(tmp_path, "T-037") is None


def test_read_last_run_prefers_mirror_over_global_status(tmp_path):
    # Both exist: the per-task mirror is authoritative for this task; the global
    # slot (which may hold a newer, different task's run) must not override it.
    _write_mirror(tmp_path, "T-037", {
        "task_id": "T-037", "current_node": "review", "current_state": "changes-requested",
        "updated_at": "mirror-time",
        "pipeline": [{"node": "review", "node_state": "changes-requested", "handoff": "from mirror", "outcome": None}],
    })
    _write_global(tmp_path, {
        "task_id": "T-037", "current_node": "dev", "current_state": "fail",
        "updated_at": "global-time",
        "pipeline": [{"node": "dev", "node_state": "fail", "handoff": "from global", "outcome": "escalated"}],
    })
    got = read_last_run(tmp_path, "T-037")
    assert got["handoff"] == "from mirror"
    assert got["updated_at"] == "mirror-time"
