import json

import pytest
from factory.orchestrator.status import FakeStatusReporter, FileStatusReporter, NullStatusReporter

pytestmark = pytest.mark.unit


def test_null_status_reporter_does_nothing():
    NullStatusReporter().report(
        task_id="T-001", node="dev", node_state="running", attempt=1, max_attempts=3
    )


def test_file_status_reporter_writes_json(tmp_path):
    path = tmp_path / "status.json"
    reporter = FileStatusReporter(path=path, session_id="s1")
    reporter.report(
        task_id="T-001",
        node="dev",
        node_state="running",
        attempt=2,
        max_attempts=3,
        snippet="working on it",
        outcome=None,
    )
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["session_id"] == "s1"
    assert record["task_id"] == "T-001"
    assert record["node"] == "dev"
    assert record["node_state"] == "running"
    assert record["attempt"] == 2
    assert record["max_attempts"] == 3
    assert record["snippet"] == "working on it"
    assert record["outcome"] is None
    assert "updated_at" in record


def test_file_status_reporter_overwrites_on_each_report(tmp_path):
    path = tmp_path / "status.json"
    reporter = FileStatusReporter(path=path, session_id="s1")
    reporter.report(task_id="T-001", node="context-gather", node_state="running", attempt=1, max_attempts=2)
    reporter.report(task_id="T-001", node="dev", node_state="pass", attempt=1, max_attempts=3)
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["node"] == "dev"
    assert record["node_state"] == "pass"


def test_file_status_reporter_leaves_no_tmp_file(tmp_path):
    path = tmp_path / "status.json"
    FileStatusReporter(path=path, session_id="s1").report(
        task_id="T-001", node="dev", node_state="running", attempt=1, max_attempts=3
    )
    assert not (tmp_path / "status.json.tmp").exists()


def test_file_status_reporter_creates_parent_dir(tmp_path):
    path = tmp_path / "nested" / "status.json"
    FileStatusReporter(path=path, session_id="s1").report(
        task_id="T-001", node="dev", node_state="running", attempt=1, max_attempts=3
    )
    assert path.exists()


def test_fake_status_reporter_records_calls():
    fake = FakeStatusReporter()
    fake.report(task_id="T-001", node="dev", node_state="running", attempt=1, max_attempts=3)
    fake.report(task_id="T-001", node="dev", node_state="pass", attempt=1, max_attempts=3, outcome="completed")
    assert [(c["node"], c["node_state"]) for c in fake.calls] == [("dev", "running"), ("dev", "pass")]
    assert fake.calls[-1]["outcome"] == "completed"
