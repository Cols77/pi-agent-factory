from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

from coherence.planning.model import CaptureEvent, IntentAnswer, IntentDocument, PlanningFinding
from coherence.planning.paths import safe_resolve, safe_root
from coherence.planning.serialization import strict_json_dumps, strict_json_loads

_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_SECRET_RE = re.compile(
    r"(?i)\b(?:api[_-]?key|secret|password|passwd|token)\b\s*[:=]\s*[^\s,;]+"
)
_BRIEF_FIELDS = ("goal", "scope", "constraints", "non_goals", "done_when", "open_questions")
_STATUSES = {"provisional", "needs_user", "cancelled"}
_EVENT_KINDS = {"capture_started", "answer_captured", "capture_status", "question_deferred"}


class IntentError(ValueError):
    """Raised when a planning intent or capture journal is unsafe or malformed."""


def _redact(value: object) -> str:
    return _SECRET_RE.sub("[REDACTED]", str(value))


def _safe_project_root(project_root: Path) -> Path:
    root = safe_root(project_root)
    if root is None:
        raise IntentError("project_root is not a safe project path")
    return root


def _safe_path(root: Path, path: Path) -> Path:
    resolved = safe_resolve(root, path)
    if resolved is None:
        raise IntentError("path must remain inside the safe project root")
    return resolved


def _validate_run_id(run_id: str) -> None:
    if not isinstance(run_id, str) or _RUN_ID_RE.fullmatch(run_id) is None:
        raise IntentError("run id is invalid")


def _journal_path(root: Path, run_id: str) -> Path:
    _validate_run_id(run_id)
    return _safe_path(root, root / ".factory" / "planning" / run_id / "capture" / "events.jsonl")


def _as_text(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise IntentError(f"{field} must be text")
    return value


def _as_string_list(value: object, field: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise IntentError(f"{field} must be a list of text values")
    return list(value)


def _brief(value: object) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        raise IntentError("brief must be an object")
    if set(value) != set(_BRIEF_FIELDS):
        raise IntentError("brief must contain the canonical fields")
    return {field: _as_string_list(value[field], f"brief.{field}") for field in _BRIEF_FIELDS}


def _answer(value: object, index: int, *, schema: int) -> IntentAnswer:
    if not isinstance(value, dict):
        raise IntentError(f"answer {index} must be an object")
    answer_id = _as_text(value.get("id"), f"answer {index}.id")
    text = _as_text(value.get("text"), f"answer {index}.text")
    if schema == 1:
        question = ""
        source = "legacy"
        sequence = index + 1
    else:
        question = _as_text(value.get("question"), f"answer {index}.question")
        source = _as_text(value.get("source"), f"answer {index}.source")
        sequence_value = value.get("sequence")
        if type(sequence_value) is not int or sequence_value < 1:
            raise IntentError(f"answer {index}.sequence must be a positive integer")
        sequence = sequence_value
    return IntentAnswer(
        id=answer_id,
        question=question,
        text=text,
        source=source,
        sequence=sequence,
    )


def read_intent(path: Path, *, project_root: Path) -> IntentDocument:
    """Read schema-one or schema-two intent with strict parsing and safe paths."""
    root = _safe_project_root(project_root)
    safe_path = _safe_path(root, path)
    try:
        text = safe_path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        raise IntentError("intent is not valid UTF-8") from exc
    except OSError as exc:
        raise IntentError("intent could not be read") from exc
    try:
        payload = strict_json_loads(text)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise IntentError(_redact(f"intent JSON is invalid: {exc}")) from exc
    if not isinstance(payload, dict):
        raise IntentError("intent must be a JSON object")
    schema_value = payload.get("schema")
    if type(schema_value) is not int or schema_value not in {1, 2}:
        raise IntentError("intent schema must equal 1 or 2")
    schema = schema_value
    prompt = _as_text(payload.get("prompt"), "prompt")
    answers_value = payload.get("answers")
    if not isinstance(answers_value, list):
        raise IntentError("answers must be a list")
    answers = tuple(_answer(item, index, schema=schema) for index, item in enumerate(answers_value))
    if schema == 1:
        return IntentDocument(
            schema=1,
            run_id=None,
            prompt=prompt,
            answers=answers,
            brief={field: [] for field in _BRIEF_FIELDS},
            capture_status="provisional",
            redactions=[],
        )
    run_id = _as_text(payload.get("run_id"), "run_id")
    _validate_run_id(run_id)
    redactions = _as_string_list(payload.get("redactions"), "redactions")
    capture_status = _as_text(payload.get("capture_status"), "capture_status")
    return IntentDocument(
        schema=2,
        run_id=run_id,
        prompt=prompt,
        answers=answers,
        brief=_brief(payload.get("brief")),
        capture_status=capture_status,
        redactions=redactions,
    )


def _text_values(document: IntentDocument) -> list[str]:
    values = [document.prompt]
    values.extend(answer.question for answer in document.answers)
    values.extend(answer.text for answer in document.answers)
    values.extend(answer.source for answer in document.answers)
    for items in document.brief.values():
        values.extend(items)
    return values


def validate_intent(document: IntentDocument) -> tuple[PlanningFinding, ...]:
    """Return deterministic validation findings without leaking secret-shaped values."""
    findings: list[PlanningFinding] = []
    if not document.prompt.strip():
        findings.append(PlanningFinding("INTENT_INVALID", "error", "intent", "prompt must be non-empty"))
    ids = [answer.id for answer in document.answers]
    sequences = [answer.sequence for answer in document.answers]
    if len(ids) != len(set(ids)):
        findings.append(PlanningFinding("INTENT_INVALID", "error", "intent", "duplicate answer id"))
    if len(sequences) != len(set(sequences)):
        findings.append(PlanningFinding("INTENT_INVALID", "error", "intent", "duplicate answer sequence"))
    if any(sequence < 1 for sequence in sequences):
        findings.append(PlanningFinding("INTENT_INVALID", "error", "intent", "answer sequence must be positive"))
    if document.capture_status not in _STATUSES:
        findings.append(PlanningFinding("INTENT_INVALID", "error", "intent", "capture_status is invalid"))
    if document.schema == 2 and not document.run_id:
        findings.append(PlanningFinding("INTENT_INVALID", "error", "intent", "run_id must be non-empty"))
    if any(_SECRET_RE.search(value) for value in _text_values(document)):
        findings.append(
            PlanningFinding(
                "INTENT_SECRET_REDACTED",
                "error",
                "intent",
                "secret-shaped value was redacted as [REDACTED]",
            )
        )
    return tuple(findings)


def _event_to_dict(event: CaptureEvent) -> dict[str, object]:
    if not isinstance(event, CaptureEvent):
        raise IntentError("capture event has an invalid type")
    _validate_run_id(event.run_id)
    if type(event.sequence) is not int or event.sequence < 1:
        raise IntentError("event sequence must be a positive integer")
    if event.kind not in _EVENT_KINDS:
        raise IntentError("event kind is invalid")
    if not isinstance(event.payload, dict):
        raise IntentError("event payload must be an object")
    return {
        "run_id": event.run_id,
        "sequence": event.sequence,
        "kind": event.kind,
        "payload": event.payload,
    }


def _read_events(journal: Path, run_id: str) -> list[CaptureEvent]:
    if not journal.exists():
        return []
    try:
        lines = journal.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise IntentError("capture journal is not valid UTF-8") from exc
    except OSError as exc:
        raise IntentError("capture journal could not be read") from exc
    events: list[CaptureEvent] = []
    previous = 0
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            raise IntentError(f"capture journal line {line_number} is empty")
        try:
            value = strict_json_loads(line)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise IntentError(_redact(f"capture journal line {line_number} is invalid: {exc}")) from exc
        if not isinstance(value, dict):
            raise IntentError(f"capture journal line {line_number} must be an object")
        event = CaptureEvent(
            run_id=_as_text(value.get("run_id"), "event.run_id"),
            sequence=value.get("sequence"),  # type: ignore[arg-type]
            kind=_as_text(value.get("kind"), "event.kind"),
            payload=value.get("payload"),  # type: ignore[arg-type]
        )
        _event_to_dict(event)
        if event.run_id != run_id:
            raise IntentError("capture event run_id does not match journal run")
        if event.sequence <= previous:
            raise IntentError("capture event sequence must be strictly increasing")
        previous = event.sequence
        events.append(event)
    return events


def append_capture_event(root: Path, run_id: str, event: CaptureEvent) -> Path:
    """Atomically append one validated event to a run-local capture journal."""
    project_root = _safe_project_root(root)
    journal = _journal_path(project_root, run_id)
    event_dict = _event_to_dict(event)
    if event.run_id != run_id:
        raise IntentError("capture event run_id does not match requested run")
    existing = _read_events(journal, run_id)
    expected_sequence = existing[-1].sequence + 1 if existing else 1
    if event.sequence != expected_sequence:
        raise IntentError("capture event sequence must be the next sequence")
    _replay_events([*existing, event], run_id)
    serialized = strict_json_dumps(event_dict) + "\n"
    try:
        journal.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(journal, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(descriptor, "a", encoding="utf-8", newline="") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise IntentError("capture event could not be appended") from exc
    return journal


def _replay_events(events: list[CaptureEvent], run_id: str) -> IntentDocument:
    if not events:
        raise IntentError("capture journal is empty")
    if events[0].kind != "capture_started":
        raise IntentError("capture must start with capture_started")
    started_payload = events[0].payload
    prompt = _as_text(started_payload.get("prompt"), "capture_started.prompt")
    answers: list[IntentAnswer] = []
    answer_ids: set[str] = set()
    brief = {field: [] for field in _BRIEF_FIELDS}
    status = "provisional"
    for event in events[1:]:
        if event.run_id != run_id:
            raise IntentError("capture event run_id does not match requested run")
        payload = event.payload
        if event.kind == "capture_started":
            raise IntentError("capture_started may occur only once")
        if event.kind == "answer_captured":
            answer_id = _as_text(payload.get("id"), "answer_captured.id")
            if answer_id in answer_ids:
                raise IntentError("duplicate answer id in capture journal")
            answer_ids.add(answer_id)
            answers.append(
                IntentAnswer(
                    id=answer_id,
                    question=_as_text(payload.get("question"), "answer_captured.question"),
                    text=_as_text(payload.get("text"), "answer_captured.text"),
                    source=_as_text(payload.get("source"), "answer_captured.source"),
                    sequence=event.sequence,
                )
            )
        elif event.kind == "capture_status":
            status = _as_text(payload.get("status"), "capture_status.status")
            if status not in _STATUSES:
                raise IntentError("capture status is invalid")
        elif event.kind == "question_deferred":
            question_id = _as_text(payload.get("id"), "question_deferred.id")
            brief["open_questions"].append(question_id)
    return IntentDocument(
        schema=2,
        run_id=run_id,
        prompt=prompt,
        answers=tuple(answers),
        brief=brief,
        capture_status=status,
        redactions=[],
    )


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = handle.name
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    except OSError as exc:
        raise IntentError("intent could not be materialized") from exc
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def materialize_intent(root: Path, run_id: str, destination: Path) -> Path:
    """Replay a capture journal into an atomic schema-two intent document."""
    project_root = _safe_project_root(root)
    journal = _journal_path(project_root, run_id)
    target = _safe_path(project_root, destination)
    document = _replay_events(_read_events(journal, run_id), run_id)
    payload = {
        "schema": 2,
        "run_id": document.run_id,
        "prompt": document.prompt,
        "answers": [
            {
                "id": answer.id,
                "question": answer.question,
                "text": answer.text,
                "source": answer.source,
                "sequence": answer.sequence,
            }
            for answer in document.answers
        ],
        "brief": document.brief,
        "capture_status": document.capture_status,
        "redactions": document.redactions,
    }
    _atomic_write(target, strict_json_dumps(payload) + "\n")
    return target


__all__ = [
    "CaptureEvent",
    "IntentAnswer",
    "IntentDocument",
    "IntentError",
    "append_capture_event",
    "materialize_intent",
    "read_intent",
    "validate_intent",
]
