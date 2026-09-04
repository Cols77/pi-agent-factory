from __future__ import annotations

import json
from pathlib import Path

import pytest

import coherence.planning.intent as planning_intent
from coherence.planning.intent import (
    CaptureEvent,
    append_capture_event,
    materialize_intent,
    read_intent,
    validate_intent,
)
from coherence.planning.model import IntentAnswer

pytestmark = pytest.mark.unit


def _schema_two(**overrides: object) -> dict[str, object]:
    document: dict[str, object] = {
        "schema": 2,
        "run_id": "run-001",
        "prompt": "  Preserve this prompt exactly.\n\n",
        "answers": [
            {
                "id": "goal",
                "question": "What is the goal?",
                "text": "  Preserve this answer exactly.\n",
                "source": "user",
                "sequence": 1,
            }
        ],
        "brief": {
            "goal": ["goal"],
            "scope": ["planning"],
            "constraints": [],
            "non_goals": [],
            "done_when": ["tests pass"],
            "open_questions": ["trade-off"],
        },
        "capture_status": "needs_user",
        "redactions": [],
    }
    document.update(overrides)
    return document


def test_read_schema_two_preserves_verbatim_text_and_structured_brief(tmp_path: Path) -> None:
    path = tmp_path / ".intent" / "intent.json"
    path.parent.mkdir()
    payload = _schema_two()
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    document = read_intent(path, project_root=tmp_path)

    assert document.prompt == payload["prompt"]
    assert document.run_id == "run-001"
    assert document.capture_status == "needs_user"
    assert document.redactions == []
    assert document.brief == payload["brief"]
    assert [(answer.id, answer.question, answer.text, answer.source, answer.sequence) for answer in document.answers] == [
        ("goal", "What is the goal?", "  Preserve this answer exactly.\n", "user", 1)
    ]
    assert validate_intent(document) == ()


def test_read_schema_one_remains_backward_compatible_and_normalized(tmp_path: Path) -> None:
    path = tmp_path / ".intent" / "intent.json"
    path.parent.mkdir()
    path.write_text(
        json.dumps(
            {
                "schema": 1,
                "prompt": "legacy prompt",
                "answers": [{"id": "goal", "text": "legacy answer"}],
            }
        ),
        encoding="utf-8",
    )

    document = read_intent(path, project_root=tmp_path)

    assert document.prompt == "legacy prompt"
    assert [(answer.id, answer.text, answer.sequence) for answer in document.answers] == [("goal", "legacy answer", 1)]
    assert validate_intent(document) == ()


def test_validate_intent_rejects_duplicate_ids_sequences_and_invalid_status(tmp_path: Path) -> None:
    path = tmp_path / ".intent" / "intent.json"
    path.parent.mkdir()
    payload = _schema_two(
        answers=[
            {"id": "goal", "question": "q1", "text": "a1", "source": "user", "sequence": 1},
            {"id": "goal", "question": "q2", "text": "a2", "source": "user", "sequence": 1},
        ],
        capture_status="not-a-status",
    )
    path.write_text(json.dumps(payload), encoding="utf-8")

    document = read_intent(path, project_root=tmp_path)
    rendered = " ".join(str(finding) for finding in validate_intent(document))

    assert "answer id" in rendered.lower()
    assert "sequence" in rendered.lower()
    assert "capture_status" in rendered.lower()


def test_capture_events_are_append_only_and_duplicate_sequences_fail(tmp_path: Path) -> None:
    started = CaptureEvent(
        run_id="run-001",
        sequence=1,
        kind="capture_started",
        payload={"prompt": "exact\nrequest"},
    )
    answer = CaptureEvent(
        run_id="run-001",
        sequence=2,
        kind="answer_captured",
        payload={
            "id": "goal",
            "question": "What?",
            "text": "exact\nanswer",
            "source": "user",
        },
    )
    journal = append_capture_event(tmp_path, "run-001", started)
    append_capture_event(tmp_path, "run-001", answer)
    before = journal.read_bytes()

    with pytest.raises(ValueError, match="sequence"):
        append_capture_event(tmp_path, "run-001", answer)

    assert journal.read_bytes() == before
    assert journal == tmp_path / ".factory" / "planning" / "run-001" / "capture" / "events.jsonl"


def test_capture_events_reject_invalid_transition_before_start(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="start"):
        append_capture_event(
            tmp_path,
            "run-001",
            CaptureEvent(
                run_id="run-001",
                sequence=1,
                kind="answer_captured",
                payload={"id": "goal", "question": "q", "text": "a", "source": "user"},
            ),
        )


def test_materialize_intent_replays_capture_events_verbatim(tmp_path: Path) -> None:
    append_capture_event(
        tmp_path,
        "run-001",
        CaptureEvent(
            run_id="run-001",
            sequence=1,
            kind="capture_started",
            payload={"prompt": "  exact prompt\n"},
        ),
    )
    append_capture_event(
        tmp_path,
        "run-001",
        CaptureEvent(
            run_id="run-001",
            sequence=2,
            kind="answer_captured",
            payload={
                "id": "goal",
                "question": "Exact question?",
                "text": "  exact answer\n",
                "source": "user",
            },
        ),
    )
    append_capture_event(
        tmp_path,
        "run-001",
        CaptureEvent(
            run_id="run-001",
            sequence=3,
            kind="capture_status",
            payload={"status": "provisional"},
        ),
    )
    destination = tmp_path / ".intent" / "intent.json"

    materialize_intent(tmp_path, "run-001", destination)
    document = read_intent(destination, project_root=tmp_path)

    assert document.prompt == "  exact prompt\n"
    assert document.capture_status == "provisional"
    assert [(answer.question, answer.text) for answer in document.answers] == [("Exact question?", "  exact answer\n")]


def test_materialize_atomic_replace_failure_preserves_last_known_good_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    append_capture_event(
        tmp_path,
        "run-001",
        CaptureEvent("run-001", 1, "capture_started", {"prompt": "request"}),
    )
    destination = tmp_path / ".intent" / "intent.json"
    materialize_intent(tmp_path, "run-001", destination)
    before = destination.read_bytes()

    append_capture_event(
        tmp_path,
        "run-001",
        CaptureEvent(
            "run-001",
            2,
            "answer_captured",
            {"id": "goal", "question": "Question?", "text": "Answer", "source": "user"},
        ),
    )

    def fail_replace(*args: object) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(planning_intent.os, "replace", fail_replace)
    with pytest.raises(ValueError, match="materialized"):
        materialize_intent(tmp_path, "run-001", destination)

    assert destination.read_bytes() == before


@pytest.mark.parametrize(
    ("relative_run_id", "destination"),
    [("../escape", None), ("run-001", "../outside.json")],
)
def test_intent_persistence_rejects_unsafe_paths(
    tmp_path: Path, relative_run_id: str, destination: str | None
) -> None:
    event = CaptureEvent(run_id=relative_run_id, sequence=1, kind="capture_started", payload={"prompt": "x"})

    if destination is None:
        with pytest.raises(ValueError, match="path|run"):
            append_capture_event(tmp_path, relative_run_id, event)
    else:
        append_capture_event(tmp_path, "run-001", CaptureEvent("run-001", 1, "capture_started", {"prompt": "x"}))
        with pytest.raises(ValueError, match="path|project"):
            materialize_intent(tmp_path, "run-001", tmp_path / destination)


def test_strict_intent_reader_rejects_duplicate_keys_non_finite_and_invalid_utf8(tmp_path: Path) -> None:
    path = tmp_path / ".intent" / "intent.json"
    path.parent.mkdir()

    path.write_text('{"schema": 2, "schema": 2}', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        read_intent(path, project_root=tmp_path)

    path.write_text(json.dumps(_schema_two(), allow_nan=True).replace('"needs_user"', "NaN"), encoding="utf-8")
    with pytest.raises(ValueError, match="finite|number|JSON"):
        read_intent(path, project_root=tmp_path)

    path.write_bytes(b'{"schema": 2, "prompt": "bad\xff"}')
    with pytest.raises((ValueError, UnicodeError)):
        read_intent(path, project_root=tmp_path)


def test_secret_shaped_validation_diagnostics_are_redacted(tmp_path: Path) -> None:
    path = tmp_path / ".intent" / "intent.json"
    path.parent.mkdir()
    path.write_text(
        json.dumps(_schema_two(prompt="api_key=super-secret-value", capture_status="invalid")),
        encoding="utf-8",
    )

    document = read_intent(path, project_root=tmp_path)
    rendered = " ".join(str(finding) for finding in validate_intent(document))

    assert "[REDACTED]" in rendered
    assert "super-secret-value" not in rendered


def test_detect_challenges_flags_contradictory_and_unsupported_claims() -> None:
    from coherence.planning.intent import detect_challenges

    answers = (
        IntentAnswer("scope", "What is in scope?", "It must include the API", "user", 1),
        IntentAnswer("constraint", "What is excluded?", "The API must not change", "user", 2),
        IntentAnswer("reliability", "Why?", "This is always safe and guaranteed", "user", 3),
    )

    challenges = detect_challenges(answers)

    assert {challenge.kind for challenge in challenges} >= {"contradiction", "unsupported_claim"}
    assert all(challenge.status == "unresolved" for challenge in challenges)
    assert all(challenge.provenance == "user" for challenge in challenges)


def test_detect_challenges_surfaces_alternatives_and_tradeoffs() -> None:
    from coherence.planning.intent import detect_challenges

    challenges = detect_challenges((IntentAnswer(
        "storage", "Which storage?", "We must only use SQLite", "user", 1,
    ),))

    assert any(challenge.kind == "tradeoff" for challenge in challenges)
    assert any("alternative" in challenge.evidence_needed.lower() for challenge in challenges)


def test_challenge_resolution_is_preserved_in_materialized_intent(tmp_path: Path) -> None:
    from coherence.planning.intent import resolve_capture_challenge

    append_capture_event(tmp_path, "run-001", CaptureEvent("run-001", 1, "capture_started", {"prompt": "x"}))
    append_capture_event(tmp_path, "run-001", CaptureEvent("run-001", 2, "challenge_raised", {
        "id": "challenge-1", "kind": "unsupported_claim", "claim": "always safe",
        "rationale": "no evidence", "provenance": "user", "evidence_needed": "repository inspection",
    }))
    resolve_capture_challenge(tmp_path, "run-001", "challenge-1", "accept", "Accepted pending evidence", "user:pi")
    materialize_intent(tmp_path, "run-001", tmp_path / ".intent/intent.json")

    document = read_intent(tmp_path / ".intent/intent.json", project_root=tmp_path)
    assert document.challenges[0].status == "accepted"
    assert document.challenges[0].response == "Accepted pending evidence"
    assert document.challenges[0].provenance == "user"
    assert document.challenges[0].response_provenance == "user:pi"
