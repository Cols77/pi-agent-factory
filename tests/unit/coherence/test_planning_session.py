from __future__ import annotations

import json
from pathlib import Path

import pytest

import coherence.planning.session as planning_session
from coherence.planning.session import (
    SessionError,
    append_session_answer,
    finalize_session,
    resume_session,
    start_session,
    status_session,
)

pytestmark = pytest.mark.unit


def test_start_and_resume_create_durable_capture_state(tmp_path: Path) -> None:
    session = start_session(tmp_path, "run-001", "Build a planner")
    assert session.state == "capture"
    assert session.next_sequence == 2
    resumed = resume_session(tmp_path, "run-001")
    assert resumed.run_id == "run-001"
    assert resumed.state == "capture"
    assert (tmp_path / ".factory" / "planning" / "run-001" / "state.json").is_file()


def test_start_progressively_materializes_initial_request(tmp_path: Path) -> None:
    start_session(tmp_path, "run-001", "  Preserve this request exactly.\n")

    intent = json.loads((tmp_path / ".intent" / "intent.json").read_text(encoding="utf-8"))
    assert intent["prompt"] == "  Preserve this request exactly.\n"
    assert intent["answers"] == []
    assert intent["run_id"] == "run-001"


def test_append_progressively_materializes_each_answer(tmp_path: Path) -> None:
    start_session(tmp_path, "run-001", "request")
    append_session_answer(tmp_path, "run-001", "goal", "  Question?\n", "  Answer.\n", source="user:pi")

    intent = json.loads((tmp_path / ".intent" / "intent.json").read_text(encoding="utf-8"))
    assert intent["answers"] == [{
        "id": "goal",
        "question": "  Question?\n",
        "text": "  Answer.\n",
        "source": "user:pi",
        "sequence": 2,
    }]


def test_resume_rebuilds_snapshot_from_journal_after_interruption(tmp_path: Path) -> None:
    start_session(tmp_path, "run-001", "request")
    append_session_answer(tmp_path, "run-001", "goal", "Question?", "Answer")
    intent_path = tmp_path / ".intent" / "intent.json"
    intent_path.unlink()

    resumed = resume_session(tmp_path, "run-001")

    assert resumed.next_sequence == 3
    assert json.loads(intent_path.read_text(encoding="utf-8"))["answers"][0]["text"] == "Answer"


def test_materialization_failure_preserves_last_known_good_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    start_session(tmp_path, "run-001", "request")
    intent_path = tmp_path / ".intent" / "intent.json"
    before = intent_path.read_bytes()

    def fail(*args: object, **kwargs: object) -> Path:
        raise planning_session.SessionError("intent could not be materialized")

    monkeypatch.setattr(planning_session, "materialize_intent", fail)
    with pytest.raises(SessionError, match="materialized"):
        append_session_answer(tmp_path, "run-001", "goal", "Question?", "Answer")

    assert intent_path.read_bytes() == before
    assert "Answer" in (tmp_path / ".factory" / "planning" / "run-001" / "capture" / "events.jsonl").read_text()


def test_append_and_finalize_project_user_text(tmp_path: Path) -> None:
    start_session(tmp_path, "run-001", "Build a planner")
    append_session_answer(tmp_path, "run-001", "goal", "What is the goal?", "Keep it deterministic")
    finalized = finalize_session(tmp_path, "run-001", "provisional")
    assert finalized.state == "intent_provisional"
    assert finalized.next_sequence == 4
    assert "Keep it deterministic" in (tmp_path / ".intent" / "intent.json").read_text(encoding="utf-8")


@pytest.mark.parametrize("status", ["needs_user", "cancelled"])
def test_finalize_progressively_materializes_each_status(tmp_path: Path, status: str) -> None:
    start_session(tmp_path, "run-001", "request")

    finalize_session(tmp_path, "run-001", status)

    intent = json.loads((tmp_path / ".intent" / "intent.json").read_text(encoding="utf-8"))
    assert intent["capture_status"] == status
    assert not (tmp_path / ".factory" / "runs").exists()


def test_status_rejects_stale_derived_state(tmp_path: Path) -> None:
    start_session(tmp_path, "run-001", "Build a planner")
    state_path = tmp_path / ".factory" / "planning" / "run-001" / "state.json"
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    payload["state"] = "handoff_ready"
    state_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(SessionError, match="stale"):
        status_session(tmp_path, "run-001")


def test_session_rejects_unsafe_or_mismatched_run_ids(tmp_path: Path) -> None:
    with pytest.raises(SessionError):
        start_session(tmp_path, "../escape", "bad")
    start_session(tmp_path, "run-001", "Build a planner")
    with pytest.raises(SessionError, match="does not match"):
        append_session_answer(tmp_path, "run-001", "x", "q", "a", event_run_id="run-002")
