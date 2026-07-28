import json
import os
from unittest.mock import patch

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


def test_file_status_reporter_retries_transient_rename_failure(tmp_path):
    # On Windows os.replace() can fail with WinError 5 when the destination is
    # briefly held open by another reader. A transient failure must not lose the
    # write -- it should retry and succeed.
    path = tmp_path / "status.json"
    reporter = FileStatusReporter(path=path, session_id="s1")
    real_replace = os.replace
    calls = {"n": 0}

    def flaky_replace(src, dst):
        calls["n"] += 1
        if calls["n"] < 3:
            raise PermissionError("[WinError 5] Access is denied")
        return real_replace(src, dst)

    with patch("factory.orchestrator.status.os.replace", side_effect=flaky_replace):
        reporter.report(task_id="T-001", node="dev", node_state="running", attempt=1, max_attempts=3)

    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["pipeline"][0]["node"] == "dev"
    assert calls["n"] == 4  # primary: failed twice, succeeded on third; mirror: succeeded on first


def test_file_status_reporter_does_not_raise_on_persistent_lock(tmp_path):
    # Status is best-effort observer telemetry: a permanently locked file must
    # not abort the orchestrator run. The report call swallows the error.
    path = tmp_path / "status.json"
    reporter = FileStatusReporter(path=path, session_id="s1")
    with patch("factory.orchestrator.status.os.replace", side_effect=PermissionError("[WinError 5]")):
        # Must not raise.
        reporter.report(task_id="T-001", node="dev", node_state="running", attempt=1, max_attempts=3)
    # No leftover temp file after giving up.
    assert not (tmp_path / "status.json.tmp").exists()


def test_session_id_is_sticky_across_a_nodes_reports(tmp_path):
    # Regression: session_id is captured mid-run (streamed pi `session` event)
    # and reported on a "running" update, but a node's FINAL report can omit it
    # (the reject/escalate paths in nodes.py do). Without stickiness the final
    # report clobbers session_id back to None and the dashboard can no longer
    # open the live session -- exactly the "session inspect doesn't work" bug.
    path = tmp_path / "status.json"
    reporter = FileStatusReporter(path=path, session_id="run-1")
    reporter.report(task_id="T-1", node="context-gather", node_state="running",
                    attempt=1, max_attempts=1, session_id="abc-123")
    # Final reject report omits session_id (session_id defaults to None).
    reporter.report(task_id="T-1", node="context-gather", node_state="reject",
                    attempt=1, max_attempts=1, outcome="rejected")
    record = json.loads(path.read_text(encoding="utf-8"))
    entry = record["pipeline"][0]
    assert entry["node_state"] == "reject"
    assert entry["session_id"] == "abc-123"  # preserved, not clobbered to None


def test_start_commit_is_sticky_across_a_nodes_reports(tmp_path):
    # Same stickiness guarantee for start_commit, which the review browser needs.
    path = tmp_path / "status.json"
    reporter = FileStatusReporter(path=path, session_id="run-1")
    reporter.report(task_id="T-1", node="human-review", node_state="blocked",
                    attempt=1, max_attempts=1, start_commit="deadbeef")
    reporter.report(task_id="T-1", node="human-review", node_state="changes-requested",
                    attempt=1, max_attempts=1)
    record = json.loads(path.read_text(encoding="utf-8"))
    entry = record["pipeline"][0]
    assert entry["start_commit"] == "deadbeef"


def test_report_records_already_done_and_deliverables(tmp_path):
    path = tmp_path / "status.json"
    reporter = FileStatusReporter(path=path, session_id="run-1")
    reporter.report(task_id="T-1", node="human-review", node_state="blocked",
                    attempt=1, max_attempts=1, start_commit="abc",
                    already_done=True, deliverables=["src/x.py", "tests/test_x.py"])
    record = json.loads(path.read_text(encoding="utf-8"))
    entry = record["pipeline"][0]
    assert entry["already_done"] is True
    assert entry["deliverables"] == ["src/x.py", "tests/test_x.py"]


def test_report_mirrors_record_to_per_task_file(tmp_path):
    path = tmp_path / "sessions" / ".factory-status.json"
    reporter = FileStatusReporter(path=path, session_id="s1")
    reporter.report(task_id="T-037", node="dev", node_state="fail", attempt=3, max_attempts=3,
                    handoff="unit tests still red", outcome="escalated")
    mirror = tmp_path / "sessions" / ".factory-runs" / "T-037.json"
    assert mirror.exists()
    rec = json.loads(mirror.read_text(encoding="utf-8"))
    assert rec["task_id"] == "T-037"
    assert rec["current_node"] == "dev"
    assert rec["current_state"] == "fail"
    assert rec["pipeline"][0]["handoff"] == "unit tests still red"


def test_report_mirror_write_failure_does_not_raise(tmp_path):
    # Best-effort: a failing mirror write must not abort the run, and the primary
    # status file must still be written.
    path = tmp_path / "sessions" / ".factory-status.json"
    reporter = FileStatusReporter(path=path, session_id="s1")
    # Make the mirror dir path a FILE so mkdir(parents=True) under it raises.
    (tmp_path / "sessions").mkdir()
    (tmp_path / "sessions" / ".factory-runs").write_text("x", encoding="utf-8")
    reporter.report(task_id="T-1", node="dev", node_state="running", attempt=1, max_attempts=3)  # must not raise
    assert path.exists()  # primary write still happened
