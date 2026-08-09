import json
import pytest
from factory.system.sessions import SessionRun, load_session_runs  # noqa: F401

from ._fixtures import write_session as _write_session

pytestmark = pytest.mark.unit


def test_loads_only_runs_for_the_requested_task(tmp_path):
    _write_session(tmp_path, "2026-08-06T20-00-00Z", "T-055", "completed")
    _write_session(tmp_path, "2026-08-06T21-00-00Z", "T-056", "rejected")

    runs = load_session_runs(tmp_path, "T-055")

    assert [r.task_id for r in runs] == ["T-055"]
    assert runs[0].outcome == "completed"
    assert runs[0].run_id == "2026-08-06T20-00-00Z"
    assert runs[0].dod_met is True


def test_rejected_and_escalated_runs_are_kept(tmp_path):
    _write_session(tmp_path, "s1", "T-055", "rejected", dod_met=False)
    _write_session(tmp_path, "s2", "T-055", "escalated", dod_met=False)

    outcomes = sorted(r.outcome for r in load_session_runs(tmp_path, "T-055"))

    assert outcomes == ["escalated", "rejected"], "failed attempts are part of the story"


def test_absent_sessions_directory_returns_no_runs_and_does_not_raise(tmp_path):
    assert load_session_runs(tmp_path, "T-055") == []


def test_an_unreadable_session_record_is_skipped_not_fatal(tmp_path):
    (tmp_path / "sessions").mkdir()
    (tmp_path / "sessions" / "broken.session.json").write_text("{not json", encoding="utf-8")
    _write_session(tmp_path, "good", "T-055", "completed")

    assert [r.run_id for r in load_session_runs(tmp_path, "T-055")] == ["good"]


def test_runs_are_ordered_by_recorded_start_time(tmp_path):
    _write_session(tmp_path, "later", "T-055", "completed")
    path = _write_session(tmp_path, "earlier", "T-055", "completed")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["started_at"] = "2026-08-01T00:00:00Z"
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert [r.run_id for r in load_session_runs(tmp_path, "T-055")] == ["earlier", "later"]


def test_wrong_shaped_tasks_field_is_skipped_not_fatal(tmp_path):
    sessions = tmp_path / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    # Record with tasks as a scalar instead of list
    bad_payload = {
        "session_id": "bad",
        "started_at": "2026-08-06T20:00:00Z",
        "ended_at": "2026-08-06T20:30:00Z",
        "tasks": 42,
    }
    (sessions / "bad.session.json").write_text(json.dumps(bad_payload), encoding="utf-8")
    # Record with good tasks list
    _write_session(tmp_path, "good", "T-055", "completed")

    runs = load_session_runs(tmp_path, "T-055")

    assert [r.run_id for r in runs] == ["good"]


def test_wrong_shaped_nodes_field_is_skipped_not_fatal(tmp_path):
    sessions = tmp_path / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    # Record with nodes as a scalar instead of list
    bad_payload = {
        "session_id": "bad",
        "started_at": "2026-08-06T20:00:00Z",
        "ended_at": "2026-08-06T20:30:00Z",
        "tasks": [{
            "task_id": "T-055",
            "title": "Some task",
            "outcome": "completed",
            "iterations": 1,
            "commits": [],
            "dod": {"met": True},
            "nodes": 42,  # wrong: should be a list
        }],
    }
    (sessions / "bad.session.json").write_text(json.dumps(bad_payload), encoding="utf-8")
    # Record with good nodes list
    _write_session(tmp_path, "good", "T-055", "completed")

    runs = load_session_runs(tmp_path, "T-055")

    assert [r.run_id for r in runs] == ["good"]
