from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from coherence.planning.intent import (
    CaptureEvent,
    IntentError,
    append_capture_event,
    detect_challenges,
    materialize_intent,
    read_intent,
    resolve_capture_challenge,
)
from coherence.planning.paths import safe_resolve, safe_root
from coherence.planning.serialization import strict_json_dumps, strict_json_loads

_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class SessionError(ValueError):
    """A planning session is invalid, stale, or cannot progress."""


@dataclass(frozen=True)
class PlanningSession:
    project_root: Path
    run_id: str
    state: str
    next_sequence: int
    journal_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": 1,
            "run_id": self.run_id,
            "state": self.state,
            "next_sequence": self.next_sequence,
            "journal_sha256": self.journal_sha256,
        }


def _root(project_root: Path) -> Path:
    resolved = safe_root(project_root)
    if resolved is None:
        raise SessionError("project_root is unsafe")
    return resolved


def _validate_run_id(run_id: str) -> None:
    if not isinstance(run_id, str) or _RUN_ID.fullmatch(run_id) is None:
        raise SessionError("run_id must be a safe path component")


def _inside(root: Path, *parts: str) -> Path:
    candidate = root.joinpath(*parts)
    resolved = safe_resolve(root, candidate)
    if resolved is None:
        raise SessionError("session path is outside project_root")
    return resolved


def _journal(root: Path, run_id: str) -> Path:
    return _inside(root, ".factory", "planning", run_id, "capture", "events.jsonl")


def _state_path(root: Path, run_id: str) -> Path:
    return _inside(root, ".factory", "planning", run_id, "state.json")


def _intent_path(root: Path) -> Path:
    return _inside(root, ".intent", "intent.json")


def _materialize(root: Path, run_id: str) -> None:
    """Materialize the journal without replacing the last good snapshot on failure."""
    try:
        materialize_intent(root, run_id, _intent_path(root))
    except IntentError as exc:
        raise SessionError(str(exc)) from exc


def _events(path: Path, run_id: str) -> list[CaptureEvent]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise SessionError("capture journal is unreadable") from exc
    events: list[CaptureEvent] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            value = strict_json_loads(line)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise SessionError("capture journal is malformed") from exc
        if not isinstance(value, dict) or value.get("run_id") != run_id:
            raise SessionError("capture journal run_id does not match")
        sequence = value.get("sequence")
        kind = value.get("kind")
        payload = value.get("payload")
        if type(sequence) is not int or not isinstance(kind, str) or not isinstance(payload, dict):
            raise SessionError("capture journal event is malformed")
        events.append(CaptureEvent(run_id, sequence, kind, payload))
    sequences = [event.sequence for event in events]
    if sequences != sorted(sequences) or sequences != list(range(1, len(sequences) + 1)):
        raise SessionError("capture journal sequences are contradictory")
    return events


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes() if path.exists() else b"").hexdigest()


def _write_state(root: Path, session: PlanningSession) -> None:
    path = _state_path(root, session.run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".state-", suffix=".tmp", dir=str(path.parent))
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(strict_json_dumps(session.to_dict()) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _project(root: Path, run_id: str, events: list[CaptureEvent]) -> PlanningSession:
    if not events:
        state = "capture"
    elif events[0].kind != "capture_started":
        raise SessionError("capture journal must start with capture_started")
    elif events[-1].kind == "capture_status":
        status = events[-1].payload.get("status")
        if status == "provisional":
            state = "intent_provisional"
        elif status == "cancelled":
            state = "blocked"
        else:
            state = "capture"
    else:
        state = "capture"
    journal = _journal(root, run_id)
    return PlanningSession(root, run_id, state, len(events) + 1, _digest(journal))


def start_session(project_root: Path, run_id: str, prompt: str) -> PlanningSession:
    root = _root(project_root)
    _validate_run_id(run_id)
    if not isinstance(prompt, str) or not prompt:
        raise SessionError("prompt must be non-empty text")
    journal = _journal(root, run_id)
    if journal.exists():
        raise SessionError("planning session already exists")
    append_capture_event(
        root,
        run_id,
        CaptureEvent(run_id, 1, "capture_started", {"prompt": prompt}),
    )
    _materialize(root, run_id)
    session = _project(root, run_id, _events(journal, run_id))
    _write_state(root, session)
    return session


def resume_session(project_root: Path, run_id: str) -> PlanningSession:
    root = _root(project_root)
    _validate_run_id(run_id)
    _materialize(root, run_id)
    session = _project(root, run_id, _events(_journal(root, run_id), run_id))
    _write_state(root, session)
    return session


def status_session(project_root: Path, run_id: str) -> PlanningSession:
    root = _root(project_root)
    _validate_run_id(run_id)
    expected = _project(root, run_id, _events(_journal(root, run_id), run_id))
    path = _state_path(root, run_id)
    try:
        payload = strict_json_loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SessionError("state is stale or missing") from exc
    if not isinstance(payload, dict) or payload != expected.to_dict():
        raise SessionError("state is stale or contradictory")
    return expected


def append_session_answer(
    project_root: Path,
    run_id: str,
    answer_id: str,
    question: str,
    text: str,
    *,
    source: str = "user",
    event_run_id: str | None = None,
) -> PlanningSession:
    root = _root(project_root)
    _validate_run_id(run_id)
    if event_run_id is not None and event_run_id != run_id:
        raise SessionError("event run_id does not match session run_id")
    if not all(isinstance(value, str) and value for value in (answer_id, question, text, source)):
        raise SessionError("answer fields must be non-empty text")
    journal = _journal(root, run_id)
    events = _events(journal, run_id)
    if not events:
        raise SessionError("planning session has not started")
    append_capture_event(
        root,
        run_id,
        CaptureEvent(
            run_id,
            len(events) + 1,
            "answer_captured",
            {"id": answer_id, "question": question, "text": text, "source": source},
        ),
    )
    _materialize(root, run_id)
    document = read_intent(_intent_path(root), project_root=root)
    known = {challenge.id for challenge in document.challenges}
    for challenge in detect_challenges(document.answers):
        if challenge.id not in known:
            current_events = _events(journal, run_id)
            append_capture_event(root, run_id, CaptureEvent(
                run_id, len(current_events) + 1, "challenge_raised",
                {"id": challenge.id, "kind": challenge.kind, "claim": challenge.claim,
                 "rationale": challenge.rationale, "provenance": challenge.provenance,
                 "evidence_needed": challenge.evidence_needed},
            ))
    _materialize(root, run_id)
    session = _project(root, run_id, _events(journal, run_id))
    _write_state(root, session)
    return session


def resolve_session_challenge(
    project_root: Path, run_id: str, challenge_id: str, resolution: str,
    response: str, provenance: str = "user",
) -> PlanningSession:
    """Record an explicit human resolution and refresh the durable snapshot."""
    root = _root(project_root)
    _validate_run_id(run_id)
    try:
        resolve_capture_challenge(root, run_id, challenge_id, resolution, response, provenance)
        _materialize(root, run_id)
    except IntentError as exc:
        raise SessionError(str(exc)) from exc
    journal = _journal(root, run_id)
    session = _project(root, run_id, _events(journal, run_id))
    _write_state(root, session)
    return session


def finalize_session(project_root: Path, run_id: str, status: str) -> PlanningSession:
    root = _root(project_root)
    _validate_run_id(run_id)
    if status not in {"provisional", "cancelled", "needs_user"}:
        raise SessionError("unsupported capture status")
    journal = _journal(root, run_id)
    events = _events(journal, run_id)
    if not events:
        raise SessionError("planning session has not started")
    append_capture_event(
        root,
        run_id,
        CaptureEvent(run_id, len(events) + 1, "capture_status", {"status": status}),
    )
    _materialize(root, run_id)
    session = _project(root, run_id, _events(journal, run_id))
    _write_state(root, session)
    return session


__all__ = [
    "PlanningSession",
    "SessionError",
    "append_session_answer",
    "finalize_session",
    "resume_session",
    "resolve_session_challenge",
    "start_session",
    "status_session",
]
