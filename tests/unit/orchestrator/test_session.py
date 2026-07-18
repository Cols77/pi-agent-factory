import json
import pytest
from factory.orchestrator.types import TaskResult, NodeEvent
from factory.orchestrator.session import build_record, write_session

pytestmark = pytest.mark.unit


def _result(outcome="completed", dod_met=True):
    return TaskResult("T-001", "t", outcome, 1, [NodeEvent("dev", "pass")], dod_met, None)


def test_build_and_write_valid(tmp_path):
    rec = build_record("s1", "anthropic:claude-opus-4-8", [_result()], {"branch": "main"})
    path = write_session(tmp_path, rec)
    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8"))["tasks"][0]["task_id"] == "T-001"
    assert (tmp_path / "latest.md").exists()


def test_write_rejects_invalid_record(tmp_path):
    # completed but dod not met -> Plan 1 session validator fails
    rec = build_record("s1", "backend", [_result(dod_met=False)], {})
    with pytest.raises(ValueError):
        write_session(tmp_path, rec)
