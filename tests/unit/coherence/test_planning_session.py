from __future__ import annotations

import json
from pathlib import Path

import pytest

import coherence.planning.session as planning_session
from coherence.planning.session import (
    SessionError,
    append_session_answer,
    finalize_session,
    legal_actions_session,
    propose_session_challenge,
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


def test_legal_actions_for_a_started_run_begin_with_author_requirements(tmp_path: Path) -> None:
    start_session(tmp_path, "run-001", "Build a planner")

    projection = legal_actions_session(tmp_path, "run-001")

    assert projection["run_id"] == "run-001"
    assert projection["schema"] == 2
    assert projection["blocked"] is False
    assert projection["reason"] is None
    assert projection["legal_next_actions"] == ["author-requirements"]
    assert projection["starts_automatically"] is False
    assert projection["action_registry"]["legal_ids"] == [
        "author-requirements", "record-sr-consent", "author-spec", "author-plan",
        "review-spec", "review-plan", "run-planning-gates", "create-handoff",
        "inspect-handoff",
    ]


def test_legal_actions_reject_stale_persisted_identity(tmp_path: Path) -> None:
    start_session(tmp_path, "run-001", "Build a planner")
    state_path = tmp_path / ".factory/planning/run-001/state.json"
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    payload["journal_sha256"] = "0" * 64
    state_path.write_text(json.dumps(payload), encoding="utf-8")

    projection = legal_actions_session(tmp_path, "run-001")

    assert projection["blocked"] is True
    assert projection["reason"] == "STALE_SESSION_STATE"
    assert projection["legal_next_actions"] == []


def test_legal_actions_block_an_unresolved_captured_challenge(tmp_path: Path) -> None:
    start_session(tmp_path, "run-001", "Build a planner")
    append_session_answer(tmp_path, "run-001", "claim", "What do you know?", "This always works")

    projection = legal_actions_session(tmp_path, "run-001")

    assert projection["blocked"] is True
    assert projection["reason"] == "UNRESOLVED_CHALLENGE"
    assert projection["legal_next_actions"] == []


def test_legal_actions_block_an_unresolved_host_proposed_challenge(tmp_path: Path) -> None:
    start_session(tmp_path, "run-001", "Build a planner")
    propose_session_challenge(
        tmp_path, "run-001", "semantic-1", "unsupported_claim", "always safe",
        "No evidence was supplied", "repository inspection", "host:semantic-review",
    )

    projection = legal_actions_session(tmp_path, "run-001")

    assert projection["blocked"] is True
    assert projection["reason"] == "UNRESOLVED_CHALLENGE"


def test_legal_actions_reject_intent_from_another_run(tmp_path: Path) -> None:
    start_session(tmp_path, "run-001", "First request")
    start_session(tmp_path, "run-002", "Another request")

    projection = legal_actions_session(tmp_path, "run-001")

    assert projection["blocked"] is True
    assert projection["reason"] == "STALE_INTENT_SNAPSHOT"
    assert projection["legal_next_actions"] == []


def test_legal_actions_reject_cancelled_capture(tmp_path: Path) -> None:
    start_session(tmp_path, "run-001", "First request")
    finalize_session(tmp_path, "run-001", "cancelled")

    projection = legal_actions_session(tmp_path, "run-001")

    assert projection["blocked"] is True
    assert projection["legal_next_actions"] == []


def test_legal_actions_reject_stale_intent_without_rewriting_it(tmp_path: Path) -> None:
    start_session(tmp_path, "run-001", "First request")
    intent_path = tmp_path / ".intent/intent.json"
    old_intent = intent_path.read_bytes()
    append_session_answer(tmp_path, "run-001", "goal", "What?", "A planner")
    intent_path.write_bytes(old_intent)

    projection = legal_actions_session(tmp_path, "run-001")

    assert projection["reason"] == "STALE_INTENT_SNAPSHOT"
    assert projection["legal_next_actions"] == []
    assert intent_path.read_bytes() == old_intent


def test_legal_actions_for_a_valid_handoff_only_exposes_inspection(tmp_path: Path) -> None:
    start_session(tmp_path, "run-001", "Build a planner")
    handoff_path = tmp_path / ".factory" / "planning" / "run-001" / "handoff.json"
    handoff_path.parent.mkdir(parents=True, exist_ok=True)
    handoff_path.write_text(json.dumps({
        "schema": 1,
        "run_id": "run-001",
        "selected_workflow": "standard-development",
        "menu": [
            {"id": "standard-development", "label": "Standard governed development", "selected": True, "starts_automatically": False},
            {"id": "health-recovery", "label": "Health recovery", "selected": False, "starts_automatically": False},
            {"id": "feature-planning", "label": "Another feature-planning workflow", "selected": False, "starts_automatically": False},
        ],
        "canonical_artifacts": [],
        "semantic_report_hashes": {},
        "resolution_journal_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "starts_automatically": False,
    }), encoding="utf-8")

    projection = legal_actions_session(tmp_path, "run-001")

    assert projection["blocked"] is False
    assert projection["reason"] is None
    assert projection["legal_next_actions"] == ["inspect-handoff"]
