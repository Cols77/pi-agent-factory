from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from coherence.planning.cli import main as planning_main
import coherence.planning.session as planning_session
from coherence.planning.session import (
    SessionError,
    append_session_answer,
    finalize_session,
    legal_actions_session,
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

    intent = json.loads(
        (tmp_path / ".factory" / "planning" / "run-001" / "intent.json").read_text(encoding="utf-8")
    )
    assert intent["prompt"] == "  Preserve this request exactly.\n"
    assert intent["answers"] == []
    assert intent["run_id"] == "run-001"


def test_append_progressively_materializes_each_answer(tmp_path: Path) -> None:
    start_session(tmp_path, "run-001", "request")
    append_session_answer(tmp_path, "run-001", "goal", "  Question?\n", "  Answer.\n", source="user:pi")

    intent = json.loads(
        (tmp_path / ".factory" / "planning" / "run-001" / "intent.json").read_text(encoding="utf-8")
    )
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
    intent_path = tmp_path / ".factory" / "planning" / "run-001" / "intent.json"
    intent_path.unlink()

    resumed = resume_session(tmp_path, "run-001")

    assert resumed.next_sequence == 3
    assert json.loads(intent_path.read_text(encoding="utf-8"))["answers"][0]["text"] == "Answer"


def test_materialization_failure_preserves_last_known_good_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    start_session(tmp_path, "run-001", "request")
    intent_path = tmp_path / ".factory" / "planning" / "run-001" / "intent.json"
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
    assert "Keep it deterministic" in (
        tmp_path / ".factory" / "planning" / "run-001" / "intent.json"
    ).read_text(encoding="utf-8")


@pytest.mark.parametrize("status", ["needs_user", "cancelled"])
def test_finalize_progressively_materializes_each_status(tmp_path: Path, status: str) -> None:
    start_session(tmp_path, "run-001", "request")

    finalize_session(tmp_path, "run-001", status)

    intent = json.loads(
        (tmp_path / ".factory" / "planning" / "run-001" / "intent.json").read_text(encoding="utf-8")
    )
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


def test_legal_actions_offer_start_capture_before_a_run_exists(tmp_path: Path) -> None:
    projection = legal_actions_session(tmp_path, "run-001")

    assert projection["run_id"] == "run-001"
    assert projection["blocked"] is False
    assert projection["reason"] is None
    assert projection["state"] == "not_started"
    assert projection["legal_next_actions"] == ["start-capture"]
    assert projection["starts_automatically"] is False
    assert "start-capture" in projection["action_registry"]["legal_ids"]


def test_legal_actions_offer_capture_answer_and_finalize_with_no_open_challenges(tmp_path: Path) -> None:
    start_session(tmp_path, "run-001", "Build a planner")

    projection = legal_actions_session(tmp_path, "run-001")

    assert projection["blocked"] is False
    assert projection["state"] == "capture"
    assert projection["legal_next_actions"] == ["capture-answer", "finalize-capture"]
    assert projection["run_identity"]["run_id"] == "run-001"


def test_legal_actions_offer_resolve_challenge_when_one_is_unresolved(tmp_path: Path) -> None:
    start_session(tmp_path, "run-001", "Build a planner")
    append_session_answer(
        tmp_path, "run-001", "goal", "What is the goal?",
        "It must always be zero cost.",
    )

    projection = legal_actions_session(tmp_path, "run-001")

    assert projection["blocked"] is False
    assert projection["state"] == "capture"
    assert projection["legal_next_actions"] == ["resolve-challenge"]


def test_legal_actions_offer_author_review_actions_after_provisional_finalize(tmp_path: Path) -> None:
    start_session(tmp_path, "run-001", "Build a planner")
    append_session_answer(tmp_path, "run-001", "goal", "What is the goal?", "Keep it deterministic")
    finalize_session(tmp_path, "run-001", "provisional")

    projection = legal_actions_session(tmp_path, "run-001")

    assert projection["blocked"] is False
    assert projection["state"] == "intent_provisional"
    assert projection["legal_next_actions"] == ["author-spec", "author-plan", "review-spec", "review-plan"]


def test_legal_actions_block_as_capture_cancelled_after_finalize_cancelled(tmp_path: Path) -> None:
    start_session(tmp_path, "run-001", "Build a planner")

    finalize_session(tmp_path, "run-001", "cancelled")
    projection = legal_actions_session(tmp_path, "run-001")

    assert projection["blocked"] is True
    assert projection["reason"] == "CAPTURE_CANCELLED"
    assert projection["legal_next_actions"] == []


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


def test_legal_actions_reject_orphaned_state_without_journal(tmp_path: Path) -> None:
    start_session(tmp_path, "run-001", "Build a planner")
    (tmp_path / ".factory" / "planning" / "run-001" / "capture" / "events.jsonl").unlink()
    (tmp_path / ".factory" / "planning" / "run-001" / "state.json").unlink()

    projection = legal_actions_session(tmp_path, "run-001")

    assert projection["blocked"] is True
    assert projection["reason"] == "STALE_SESSION_STATE"
    assert projection["legal_next_actions"] == []


def test_legal_actions_accept_matching_legacy_intent_snapshot(tmp_path: Path) -> None:
    start_session(tmp_path, "run-001", "Build a planner")
    intent_path = tmp_path / ".factory" / "planning" / "run-001" / "intent.json"
    legacy_path = tmp_path / ".intent" / "intent.json"
    legacy_path.parent.mkdir()
    legacy_path.write_bytes(intent_path.read_bytes())
    intent_path.unlink()

    projection = legal_actions_session(tmp_path, "run-001")

    assert projection["blocked"] is False
    assert projection["state"] == "capture"
    assert projection["legal_next_actions"] == ["capture-answer", "finalize-capture"]


def test_legal_actions_reject_mismatched_legacy_intent_snapshot(tmp_path: Path) -> None:
    start_session(tmp_path, "run-001", "Build a planner")
    intent_path = tmp_path / ".factory" / "planning" / "run-001" / "intent.json"
    legacy_path = tmp_path / ".intent" / "intent.json"
    legacy_path.parent.mkdir()
    legacy_path.write_text(intent_path.read_text(encoding="utf-8").replace("run-001", "run-002"), encoding="utf-8")
    intent_path.unlink()

    projection = legal_actions_session(tmp_path, "run-001")

    assert projection["blocked"] is True
    assert projection["reason"] == "INTENT_INVALID"
    assert projection["state"] == "capture"
    assert projection["legal_next_actions"] == []


def test_legal_actions_block_on_malformed_intent_snapshot(tmp_path: Path) -> None:
    start_session(tmp_path, "run-001", "Build a planner")
    intent_path = tmp_path / ".factory" / "planning" / "run-001" / "intent.json"
    intent_path.write_text("{malformed", encoding="utf-8")

    projection = legal_actions_session(tmp_path, "run-001")

    assert projection["blocked"] is True
    assert projection["reason"] == "INTENT_INVALID"
    assert projection["state"] == "capture"
    assert projection["legal_next_actions"] == []


def test_legal_actions_block_on_semantically_malformed_intent_snapshot(tmp_path: Path) -> None:
    start_session(tmp_path, "run-001", "Build a planner")
    intent_path = tmp_path / ".factory" / "planning" / "run-001" / "intent.json"
    payload = json.loads(intent_path.read_text(encoding="utf-8"))
    payload["challenges"] = {"not": "a list"}
    intent_path.write_text(json.dumps(payload), encoding="utf-8")

    projection = legal_actions_session(tmp_path, "run-001")

    assert projection["blocked"] is True
    assert projection["reason"] == "INTENT_INVALID"
    assert projection["state"] == "capture"
    assert projection["legal_next_actions"] == []


def test_legal_actions_block_on_invalid_challenge_status(tmp_path: Path) -> None:
    start_session(tmp_path, "run-001", "Build a planner")
    append_session_answer(tmp_path, "run-001", "goal", "What is the goal?", "It must always be safe.")
    intent_path = tmp_path / ".factory" / "planning" / "run-001" / "intent.json"
    payload = json.loads(intent_path.read_text(encoding="utf-8"))
    payload["challenges"][0]["status"] = None
    intent_path.write_text(json.dumps(payload), encoding="utf-8")

    projection = legal_actions_session(tmp_path, "run-001")

    assert projection["blocked"] is True
    assert projection["reason"] == "INTENT_INVALID"
    assert projection["state"] == "capture"
    assert projection["legal_next_actions"] == []


def test_legal_actions_validate_intent_before_provisional_authoring(tmp_path: Path) -> None:
    start_session(tmp_path, "run-001", "Build a planner")
    finalize_session(tmp_path, "run-001", "provisional")
    intent_path = tmp_path / ".factory" / "planning" / "run-001" / "intent.json"
    intent_path.write_text("{malformed", encoding="utf-8")

    projection = legal_actions_session(tmp_path, "run-001")

    assert projection["blocked"] is True
    assert projection["reason"] == "INTENT_INVALID"
    assert projection["state"] == "intent_provisional"
    assert projection["legal_next_actions"] == []


def test_concurrent_runs_do_not_clobber_each_others_intent_snapshot(tmp_path: Path) -> None:
    start_session(tmp_path, "run-001", "First request")
    start_session(tmp_path, "run-002", "Second request")
    append_session_answer(tmp_path, "run-001", "goal", "Q1?", "Answer one")
    append_session_answer(tmp_path, "run-002", "goal", "Q2?", "Answer two")

    intent_one = json.loads(
        (tmp_path / ".factory" / "planning" / "run-001" / "intent.json").read_text(encoding="utf-8")
    )
    intent_two = json.loads(
        (tmp_path / ".factory" / "planning" / "run-002" / "intent.json").read_text(encoding="utf-8")
    )
    assert intent_one["run_id"] == "run-001"
    assert intent_one["answers"][0]["text"] == "Answer one"
    assert intent_two["run_id"] == "run-002"
    assert intent_two["answers"][0]["text"] == "Answer two"
    assert not (tmp_path / ".intent").exists()


def test_plan_status_reports_invalid_intent_snapshot(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    start_session(tmp_path, "run-001", "Build a planner")
    (tmp_path / ".factory" / "planning" / "run-001" / "intent.json").write_text(
        "{malformed", encoding="utf-8"
    )

    assert planning_main(["status", "--project-root", str(tmp_path), "--run-id", "run-001", "--json"]) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["error"] == "intent is invalid"


@pytest.mark.parametrize("terminal_status", ["provisional", "cancelled"])
def test_terminal_capture_status_cannot_be_reopened(
    tmp_path: Path, terminal_status: str
) -> None:
    start_session(tmp_path, "run-001", "Build a planner")
    finalize_session(tmp_path, "run-001", terminal_status)

    with pytest.raises(SessionError, match="terminal"):
        append_session_answer(tmp_path, "run-001", "later", "Later?", "No")
    with pytest.raises(SessionError, match="terminal"):
        finalize_session(tmp_path, "run-001", "needs_user")


def test_legal_actions_reject_valid_but_stale_intent_snapshot(tmp_path: Path) -> None:
    start_session(tmp_path, "run-001", "Build a planner")
    intent_path = tmp_path / ".factory" / "planning" / "run-001" / "intent.json"
    payload = json.loads(intent_path.read_text(encoding="utf-8"))
    payload["prompt"] = "A different request"
    intent_path.write_text(json.dumps(payload), encoding="utf-8")

    projection = legal_actions_session(tmp_path, "run-001")

    assert projection["blocked"] is True
    assert projection["reason"] == "INTENT_INVALID"
    assert projection["legal_next_actions"] == []


def test_legal_actions_reject_orphaned_legacy_intent_without_journal(tmp_path: Path) -> None:
    legacy_path = tmp_path / ".intent" / "intent.json"
    legacy_path.parent.mkdir()
    legacy_path.write_text("{}", encoding="utf-8")

    projection = legal_actions_session(tmp_path, "run-001")

    assert projection["blocked"] is True
    assert projection["reason"] == "STALE_SESSION_STATE"
    assert projection["legal_next_actions"] == []


def test_same_run_concurrent_answers_keep_unique_journal_sequences(tmp_path: Path) -> None:
    start_session(tmp_path, "run-001", "Build a planner")

    def append(index: int) -> None:
        append_session_answer(
            tmp_path, "run-001", f"answer-{index}", f"Question {index}?", f"Answer {index}"
        )

    with ThreadPoolExecutor(max_workers=6) as executor:
        list(executor.map(append, range(6)))

    journal = tmp_path / ".factory" / "planning" / "run-001" / "capture" / "events.jsonl"
    events = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
    assert [event["sequence"] for event in events] == list(range(1, 8))
    assert len({event["payload"].get("id") for event in events[1:]}) == 6
