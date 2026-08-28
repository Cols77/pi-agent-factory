from __future__ import annotations

import json
from pathlib import Path

import pytest

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


def test_append_and_finalize_project_user_text(tmp_path: Path) -> None:
    start_session(tmp_path, "run-001", "Build a planner")
    append_session_answer(tmp_path, "run-001", "goal", "What is the goal?", "Keep it deterministic")
    finalized = finalize_session(tmp_path, "run-001", "provisional")
    assert finalized.state == "intent_provisional"
    assert finalized.next_sequence == 4
    assert "Keep it deterministic" in (tmp_path / ".intent" / "intent.json").read_text(encoding="utf-8")


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
