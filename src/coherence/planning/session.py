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
    IntentDocument,
    append_capture_event,
    capture_lock,
    detect_challenges,
    materialize_intent,
    read_capture_events,
    read_intent,
    replay_capture_intent,
    resolve_capture_challenge,
)
from coherence.planning.paths import safe_resolve, safe_root
from coherence.planning.serialization import strict_json_dumps, strict_json_loads

_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_LEGAL_ACTION_IDS = (
    "start-capture",
    "capture-answer",
    "resolve-challenge",
    "finalize-capture",
    "author-spec",
    "author-plan",
    "review-spec",
    "review-plan",
    "inspect-handoff",
    "revalidate-handoff",
    "select-downstream-workflow",
    "create-downstream-session",
    "resolve-blocking-input",
)
_ACTION_REGISTRY_HASH = hashlib.sha256("\n".join(_LEGAL_ACTION_IDS).encode()).hexdigest()


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


def _intent_path(root: Path, run_id: str) -> Path:
    return _inside(root, ".factory", "planning", run_id, "intent.json")


def _legacy_intent_path(root: Path) -> Path:
    return _inside(root, ".intent", "intent.json")


def read_session_intent(root: Path, run_id: str) -> IntentDocument:
    root = _root(root)
    _validate_run_id(run_id)
    with capture_lock(root, run_id):
        try:
            path = _intent_path(root, run_id)
            if path.is_symlink() or path.exists():
                if not path.is_file():
                    raise SessionError("intent is invalid")
            else:
                legacy_path = _legacy_intent_path(root)
                if not legacy_path.is_file():
                    raise SessionError("intent could not be read")
                path = legacy_path
            intent = read_intent(path, project_root=root)
            canonical = replay_capture_intent(root, run_id)
        except (SessionError, IntentError) as exc:
            raise SessionError("intent is invalid") from exc
        if intent.run_id != run_id:
            raise SessionError("intent run_id does not match session run_id")
        if intent != canonical:
            raise SessionError("intent does not match capture journal")
        return intent


def _materialize(root: Path, run_id: str) -> None:
    """Materialize the journal without replacing the last good snapshot on failure."""
    try:
        materialize_intent(root, run_id, _intent_path(root, run_id))
    except IntentError as exc:
        raise SessionError(str(exc)) from exc


def _events(root: Path, run_id: str) -> list[CaptureEvent]:
    try:
        return read_capture_events(root, run_id)
    except IntentError as exc:
        raise SessionError(str(exc)) from exc


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
    with capture_lock(root, run_id):
        if journal.exists():
            raise SessionError("planning session already exists")
        append_capture_event(
            root,
            run_id,
            CaptureEvent(run_id, 1, "capture_started", {"prompt": prompt}),
            _lock_held=True,
        )
        _materialize(root, run_id)
        session = _project(root, run_id, _events(root, run_id))
        _write_state(root, session)
        return session


def resume_session(project_root: Path, run_id: str) -> PlanningSession:
    root = _root(project_root)
    _validate_run_id(run_id)
    with capture_lock(root, run_id):
        _materialize(root, run_id)
        session = _project(root, run_id, _events(root, run_id))
        _write_state(root, session)
        return session


def status_session(project_root: Path, run_id: str) -> PlanningSession:
    root = _root(project_root)
    _validate_run_id(run_id)
    expected = _project(root, run_id, _events(root, run_id))
    path = _state_path(root, run_id)
    try:
        payload = strict_json_loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SessionError("state is stale or missing") from exc
    if not isinstance(payload, dict) or payload != expected.to_dict():
        raise SessionError("state is stale or contradictory")
    return expected


def _run_identity(session: PlanningSession) -> dict[str, object]:
    return {
        "run_id": session.run_id,
        "next_sequence": session.next_sequence,
        "journal_sha256": session.journal_sha256,
    }


def legal_actions_session(project_root: Path, run_id: str) -> dict[str, object]:
    """Return the closed, fail-closed host action projection for a run.

    The persisted session snapshot is the only source of run identity.  This
    function never accepts caller-provided actions and never invokes a menu
    action or starts downstream work.
    """
    root = _root(project_root)
    _validate_run_id(run_id)
    base: dict[str, object] = {
        "schema": 1,
        "run_id": run_id,
        "legal_next_actions": [],
        "selected_downstream_workflow": None,
        "starts_automatically": False,
        "action_registry": {
            "schema": 1,
            "legal_ids": list(_LEGAL_ACTION_IDS),
            "registry_hash": _ACTION_REGISTRY_HASH,
        },
    }

    try:
        journal = _journal(root, run_id)
        state_path = _state_path(root, run_id)
        intent_path = _intent_path(root, run_id)
        handoff_path = _inside(root, ".factory", "planning", run_id, "handoff.json")
        legacy_intent_path = _legacy_intent_path(root)
        lock_path = journal.parent.parent / ".capture.lock"
    except SessionError:
        base.update({"blocked": True, "reason": "STALE_SESSION_STATE"})
        return base
    if not journal.exists():
        if any(path.exists() for path in (
            state_path, intent_path, handoff_path, legacy_intent_path, lock_path,
        )):
            base.update({"blocked": True, "reason": "STALE_SESSION_STATE"})
            return base
        base.update({
            "blocked": False,
            "reason": None,
            "state": "not_started",
            "legal_next_actions": ["start-capture"],
        })
        return base

    try:
        session = status_session(root, run_id)
    except SessionError:
        base.update({"blocked": True, "reason": "STALE_SESSION_STATE"})
        return base

    if session.state == "blocked":
        base.update({
            "blocked": True,
            "reason": "CAPTURE_CANCELLED",
            "state": session.state,
            "run_identity": _run_identity(session),
        })
        return base

    if session.state == "capture":
        try:
            intent = read_session_intent(root, run_id)
            unresolved = any(challenge.status == "unresolved" for challenge in intent.challenges)
        except SessionError:
            base.update({
                "blocked": True,
                "reason": "INTENT_INVALID",
                "state": session.state,
                "run_identity": _run_identity(session),
            })
            return base
        legal = ["resolve-challenge"] if unresolved else ["capture-answer", "finalize-capture"]
        base.update({
            "blocked": False,
            "reason": None,
            "state": session.state,
            "run_identity": _run_identity(session),
            "legal_next_actions": legal,
        })
        return base

    # session.state == "intent_provisional"
    try:
        read_session_intent(root, run_id)
    except SessionError:
        base.update({
            "blocked": True,
            "reason": "INTENT_INVALID",
            "state": session.state,
            "run_identity": _run_identity(session),
        })
        return base

    try:
        handoff = _inside(root, ".factory", "planning", run_id, "handoff.json")
    except SessionError:
        base.update({"blocked": True, "reason": "HANDOFF_INVALID", "state": session.state})
        return base
    if not handoff.is_file():
        base.update({
            "blocked": False,
            "reason": None,
            "state": session.state,
            "run_identity": _run_identity(session),
            "legal_next_actions": ["author-spec", "author-plan", "review-spec", "review-plan"],
        })
        return base
    try:
        # Import lazily to keep session persistence independent of handoff code.
        from coherence.planning.handoff import validate_handoff

        handoff_payload = validate_handoff(root, handoff)
    except (OSError, ValueError, TypeError, RuntimeError):
        base.update({"blocked": True, "reason": "HANDOFF_INVALID", "state": session.state})
        return base
    base.update({
        "blocked": False,
        "reason": None,
        "state": session.state,
        "run_identity": _run_identity(session),
        "selected_downstream_workflow": handoff_payload.get("selected_workflow"),
        "legal_next_actions": ["inspect-handoff", "revalidate-handoff"],
    })
    return base


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
    with capture_lock(root, run_id):
        events = _events(root, run_id)
        if not events:
            raise SessionError("planning session has not started")
        try:
            append_capture_event(
                root,
                run_id,
                CaptureEvent(
                    run_id,
                    len(events) + 1,
                    "answer_captured",
                    {"id": answer_id, "question": question, "text": text, "source": source},
                ),
                _lock_held=True,
            )
        except IntentError as exc:
            raise SessionError(str(exc)) from exc
        _materialize(root, run_id)
        document = read_session_intent(root, run_id)
        known = {challenge.id for challenge in document.challenges}
        for challenge in detect_challenges(document.answers):
            if challenge.id not in known:
                current_events = _events(root, run_id)
                try:
                    append_capture_event(
                        root,
                        run_id,
                        CaptureEvent(
                            run_id, len(current_events) + 1, "challenge_raised",
                            {"id": challenge.id, "kind": challenge.kind, "claim": challenge.claim,
                             "rationale": challenge.rationale, "provenance": challenge.provenance,
                             "evidence_needed": challenge.evidence_needed},
                        ),
                        _lock_held=True,
                    )
                except IntentError as exc:
                    raise SessionError(str(exc)) from exc
        _materialize(root, run_id)
        session = _project(root, run_id, _events(root, run_id))
        _write_state(root, session)
        return session


def resolve_session_challenge(
    project_root: Path, run_id: str, challenge_id: str, resolution: str,
    response: str, provenance: str = "user",
) -> PlanningSession:
    """Record an explicit human resolution and refresh the durable snapshot."""
    root = _root(project_root)
    _validate_run_id(run_id)
    with capture_lock(root, run_id):
        try:
            resolve_capture_challenge(
                root, run_id, challenge_id, resolution, response, provenance,
                _lock_held=True,
            )
            _materialize(root, run_id)
        except IntentError as exc:
            raise SessionError(str(exc)) from exc
        session = _project(root, run_id, _events(root, run_id))
        _write_state(root, session)
        return session


def finalize_session(project_root: Path, run_id: str, status: str) -> PlanningSession:
    root = _root(project_root)
    _validate_run_id(run_id)
    if status not in {"provisional", "cancelled", "needs_user"}:
        raise SessionError("unsupported capture status")
    with capture_lock(root, run_id):
        events = _events(root, run_id)
        if not events:
            raise SessionError("planning session has not started")
        try:
            append_capture_event(
                root,
                run_id,
                CaptureEvent(run_id, len(events) + 1, "capture_status", {"status": status}),
                _lock_held=True,
            )
        except IntentError as exc:
            raise SessionError(str(exc)) from exc
        _materialize(root, run_id)
        session = _project(root, run_id, _events(root, run_id))
        _write_state(root, session)
        return session


__all__ = [
    "PlanningSession",
    "SessionError",
    "append_session_answer",
    "finalize_session",
    "legal_actions_session",
    "read_session_intent",
    "resume_session",
    "resolve_session_challenge",
    "start_session",
    "status_session",
]
