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
    assert record["current_node"] == "dev"
    assert record["current_state"] == "running"
    assert len(record["pipeline"]) == 1
    assert record["pipeline"][0]["node"] == "dev"
    assert record["pipeline"][0]["node_state"] == "running"
    assert record["pipeline"][0]["snippet"] == "working on it"
    assert "updated_at" in record


def test_file_status_reporter_accumulates_pipeline(tmp_path):
    path = tmp_path / "status.json"
    reporter = FileStatusReporter(path=path, session_id="s1")
    reporter.report(task_id="T-001", node="context-gather", node_state="pass", attempt=1, max_attempts=2,
                    handoff="3 files, coherence=yes")
    reporter.report(task_id="T-001", node="dev", node_state="running", attempt=1, max_attempts=3)
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["current_node"] == "dev"
    assert len(record["pipeline"]) == 2
    assert record["pipeline"][0]["node"] == "context-gather"
    assert record["pipeline"][0]["handoff"] == "3 files, coherence=yes"
    assert record["pipeline"][1]["node"] == "dev"


def test_file_status_reporter_updates_existing_node(tmp_path):
    path = tmp_path / "status.json"
    reporter = FileStatusReporter(path=path, session_id="s1")
    reporter.report(task_id="T-001", node="context-gather", node_state="running", attempt=1, max_attempts=2)
    reporter.report(task_id="T-001", node="context-gather", node_state="pass", attempt=2, max_attempts=2,
                    handoff="→ dev: 3 files")
    record = json.loads(path.read_text(encoding="utf-8"))
    assert len(record["pipeline"]) == 1  # same node updated, not duplicated
    assert record["pipeline"][0]["node_state"] == "pass"
    assert record["pipeline"][0]["handoff"] == "→ dev: 3 files"


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


def test_report_persists_session_id_summary_and_start_commit(tmp_path):
    path = tmp_path / "status.json"
    r = FileStatusReporter(path=path, session_id="s1")
    r.report(
        task_id="T-1", node="dev", node_state="running", attempt=1, max_attempts=3,
        session_id="019f-uuid", summary="changed 3 files; unit tests pass",
    )
    r.report(
        task_id="T-1", node="human-review", node_state="blocked", attempt=1, max_attempts=1,
        start_commit="abc123",
    )
    record = json.loads(path.read_text(encoding="utf-8"))
    dev = next(e for e in record["pipeline"] if e["node"] == "dev")
    hr = next(e for e in record["pipeline"] if e["node"] == "human-review")
    assert dev["session_id"] == "019f-uuid"
    assert dev["summary"] == "changed 3 files; unit tests pass"
    assert hr["start_commit"] == "abc123"


def test_report_defaults_new_fields_to_none(tmp_path):
    path = tmp_path / "status.json"
    FileStatusReporter(path=path, session_id="s1").report(
        task_id="T-1", node="validation", node_state="pass", attempt=1, max_attempts=1,
    )
    entry = json.loads(path.read_text(encoding="utf-8"))["pipeline"][0]
    assert entry["session_id"] is None
    assert entry["summary"] is None
    assert entry["start_commit"] is None
