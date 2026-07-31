import pytest
from factory.validation.session_validator import validate_session

pytestmark = pytest.mark.unit


def _record(**task_over):
    task = {"task_id": "T-001", "outcome": "completed",
            "nodes": [{"node": "dev", "result": "pass"}],
            "dod": {"met": True}}
    task.update(task_over)
    return {"session_id": "s1", "started_at": "2026-07-16T14:30:00Z",
            "model_backend": "anthropic:claude-opus-4-8", "tasks": [task]}


def test_valid_session_passes():
    assert validate_session(_record()) == []


def test_completed_without_dod_met_fails():
    errors = validate_session(_record(dod={"met": False}))
    assert any("dod.met" in e for e in errors)


def test_escalated_task_needs_no_dod():
    assert validate_session(_record(outcome="escalated", dod={})) == []


def test_schema_violation_reported():
    bad = _record()
    bad["tasks"][0]["outcome"] = "banana"
    assert validate_session(bad)
