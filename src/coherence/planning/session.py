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
    _replay_events,
    append_capture_event,
    capture_lock,
    detect_challenges,
    materialize_intent,
    propose_capture_challenge,
    read_capture_events,
    read_intent,
    replay_capture_intent,
    resolve_capture_challenge,
)
from coherence.planning.paths import safe_resolve, safe_root
from coherence.planning.lifecycle import (
    EvidenceStatus,
    LifecycleEvidence,
    action_registry,
    project_lifecycle,
)
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


def _intent_path(root: Path, run_id: str) -> Path:
    return _inside(root, ".factory", "planning", run_id, "intent.json")


def _legacy_intent_path(root: Path) -> Path:
    return _inside(root, ".intent", "intent.json")


def read_session_intent(root: Path, run_id: str) -> IntentDocument:
    root = _root(root)
    _validate_run_id(run_id)
    with capture_lock(root, run_id):
        try:
            canonical_path = _intent_path(root, run_id)
            legacy_path = _legacy_intent_path(root)
            path = canonical_path if canonical_path.is_file() else legacy_path
            intent = read_intent(path, project_root=root)
            canonical = replay_capture_intent(root, run_id)
            if canonical_path.is_file() and legacy_path.is_file():
                legacy = read_intent(legacy_path, project_root=root)
                if legacy != intent:
                    raise SessionError("legacy intent mirror is stale")
        except (OSError, IntentError, ValueError, TypeError) as exc:
            raise SessionError("intent is invalid") from exc
        if intent.run_id != run_id or intent != canonical:
            raise SessionError("intent is stale or invalid")
        return intent


def _materialize(root: Path, run_id: str) -> None:
    """Materialize the journal without replacing the last good snapshot on failure."""
    try:
        materialize_intent(root, run_id, _intent_path(root, run_id))
        materialize_intent(root, run_id, _legacy_intent_path(root))
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
    with capture_lock(root, run_id):
        expected = _project(root, run_id, _events(root, run_id))
        path = _state_path(root, run_id)
        try:
            payload = strict_json_loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise SessionError("state is stale or missing") from exc
        if not isinstance(payload, dict) or payload != expected.to_dict():
            raise SessionError("state is stale or contradictory")
        return expected


def _lifecycle_evidence(root: Path, session: PlanningSession) -> LifecycleEvidence:
    """Load current durable evidence without deriving lifecycle actions."""
    manifest_status: EvidenceStatus = "missing"
    artifact_kinds: frozenset[str] = frozenset()
    manifest_path = _inside(root, ".factory", "planning", session.run_id, "artifacts.json")
    if manifest_path.exists():
        try:
            from coherence.planning.artifacts import read_artifact_manifest

            manifest = read_artifact_manifest(root, session.run_id)
            artifacts = manifest["artifacts"]
            if not isinstance(artifacts, list):
                raise ValueError("artifact manifest entries must be a list")
            artifact_kinds = frozenset(
                item["kind"] for item in artifacts
                if isinstance(item, dict) and isinstance(item.get("kind"), str)
            )
            manifest_status = "valid"
        except (OSError, ValueError, TypeError):
            manifest_status = "invalid"

    unresolved_challenges = False
    intent_status: EvidenceStatus = "valid"
    try:
        intent = read_session_intent(root, session.run_id)
        expected_intent = _replay_events(
            _events(root, session.run_id), session.run_id
        )
        if intent != expected_intent:
            intent_status = "stale"
        unresolved_challenges = any(
            challenge.status == "unresolved" for challenge in expected_intent.challenges
        )
    except (IntentError, SessionError):
        intent_status = "invalid"

    consent_status: EvidenceStatus = "missing"
    if "requirements" in artifact_kinds:
        try:
            from coherence.planning.gates import _current_feature_requirements
            from coherence.planning.consent import validate_sr_decisions

            current, _ = _current_feature_requirements(root)
            valid, detail = validate_sr_decisions(root, session.run_id, current)
            if valid:
                consent_status = "valid"
            elif detail.startswith("missing human consent:"):
                consent_status = "missing"
            elif detail.startswith("stale human consent:"):
                consent_status = "stale"
            else:
                consent_status = "invalid"
        except (OSError, TypeError, ValueError, RuntimeError):
            consent_status = "invalid"

    spec_review_status: EvidenceStatus = "missing"
    plan_review_status: EvidenceStatus = "missing"
    gate_status: EvidenceStatus = "missing"
    run_dir = _inside(root, ".factory", "planning", session.run_id)
    spec_review = run_dir / "spec-review.json"
    plan_review = run_dir / "plan-review.json"

    def review_marker(path: Path) -> EvidenceStatus:
        if not path.exists():
            return "missing"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return "valid" if isinstance(payload, dict) and payload.get("status") == "pass" else "invalid"
        except (OSError, UnicodeError, TypeError, ValueError, json.JSONDecodeError):
            return "invalid"

    spec_review_status = review_marker(spec_review)
    if spec_review_status == "valid":
        plan_review_status = review_marker(plan_review)
    try:
        from coherence.planning.gates import (
            _resolve_human_review,
            compile_planning_gate_pack,
            validate_planning_gate_result,
        )

        review_status, _ = _resolve_human_review(root, session.run_id)
        if review_status != "pass":
            decision_path = run_dir / "review-decision.json"
            if decision_path.exists():
                spec_review_status = "stale"
                plan_review_status = "stale"
            else:
                spec_review_status = "missing"
                plan_review_status = "missing"
        elif spec_review_status == "missing":
            # The reviewed decision is current, but the stage-specific record
            # has not yet been published.
            plan_review_status = "missing"
        result_path = run_dir / "planning-gate-result.json"
        if result_path.exists():
            validate_planning_gate_result(root, session.run_id, compile_planning_gate_pack("FEAT-017", "v1"))
            gate_status = "valid"
    except (OSError, TypeError, ValueError, RuntimeError):
        gate_status = "invalid"

    handoff_status: EvidenceStatus = "missing"
    handoff = _inside(root, ".factory", "planning", session.run_id, "handoff.json")
    if handoff.exists():
        if not handoff.is_file():
            handoff_status = "invalid"
        else:
            try:
                from coherence.planning.handoff import validate_handoff

                validate_handoff(root, handoff)
                handoff_status = "valid"
            except (OSError, ValueError, TypeError, RuntimeError):
                handoff_status = "invalid"
    if handoff_status == "valid" and spec_review_status == "missing":
        # A legacy handoff is itself the durable attestation for both review
        # stages; newer runs persist the explicit stage markers above.
        spec_review_status = "valid"
        plan_review_status = "valid"
    if handoff_status == "valid" and gate_status == "missing":
        gate_status = "valid"

    return LifecycleEvidence(
        run_id=session.run_id,
        state=session.state,
        run_identity={
            "run_id": session.run_id,
            "next_sequence": session.next_sequence,
            "journal_sha256": session.journal_sha256,
        },
        manifest_status=manifest_status,
        artifact_kinds=artifact_kinds,
        consent_status=consent_status,
        spec_review_status=spec_review_status,
        plan_review_status=plan_review_status,
        gate_status=gate_status,
        handoff_status=handoff_status,
        unresolved_challenges=unresolved_challenges,
        intent_status=intent_status,
    )


def legal_actions_session(project_root: Path, run_id: str) -> dict[str, object]:
    """Load run evidence and delegate action selection to the pure projector."""
    root = _root(project_root)
    _validate_run_id(run_id)
    base: dict[str, object] = {
        "schema": 2,
        "run_id": run_id,
        "state": "unknown",
        "legal_next_actions": [],
        "starts_automatically": False,
        "run_identity": None,
        "action_registry": dict(action_registry()),
    }
    try:
        session = status_session(root, run_id)
    except SessionError:
        base.update({"blocked": True, "reason": "STALE_SESSION_STATE"})
        return base
    return project_lifecycle(_lifecycle_evidence(root, session)).to_dict()


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
        _materialize(root, run_id)
        document = read_session_intent(root, run_id)
        known = {challenge.id for challenge in document.challenges}
        for challenge in detect_challenges(document.answers):
            if challenge.id not in known:
                current_events = _events(root, run_id)
                append_capture_event(root, run_id, CaptureEvent(
                    run_id, len(current_events) + 1, "challenge_raised",
                    {"id": challenge.id, "kind": challenge.kind, "claim": challenge.claim,
                     "rationale": challenge.rationale, "provenance": challenge.provenance,
                     "evidence_needed": challenge.evidence_needed},
                ), _lock_held=True)
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


def propose_session_challenge(
    project_root: Path, run_id: str, challenge_id: str, kind: str, claim: str,
    rationale: str, evidence_needed: str, provenance: str,
) -> PlanningSession:
    """Persist a host challenge proposal without resolving or approving anything."""
    root = _root(project_root)
    _validate_run_id(run_id)
    if not all(
        isinstance(value, str) and value
        for value in (challenge_id, kind, claim, rationale, evidence_needed, provenance)
    ):
        raise SessionError("semantic challenge proposal fields must be non-empty text")
    if not provenance.startswith("host:"):
        raise SessionError("semantic challenge proposal requires host provenance")
    with capture_lock(root, run_id):
        try:
            propose_capture_challenge(
                root, run_id, challenge_id, kind, claim, rationale, evidence_needed, provenance,
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
        append_capture_event(
            root,
            run_id,
            CaptureEvent(run_id, len(events) + 1, "capture_status", {"status": status}),
            _lock_held=True,
        )
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
    "propose_session_challenge",
    "read_session_intent",
    "resume_session",
    "resolve_session_challenge",
    "start_session",
    "status_session",
]
