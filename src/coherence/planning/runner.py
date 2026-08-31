"""Parent-owned deterministic planning workflow state machine."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from coherence.planning.paths import safe_resolve, safe_root


class RunnerError(ValueError):
    """Raised when a planning-runner contract is invalid."""


class RunnerBlocked(RunnerError):
    """Raised when a run must remain blocked until a new attempt or decision."""


class PlanningStage(str, Enum):
    CAPTURE = "capture"
    PROVISIONAL_SPEC = "provisional_spec"
    SPEC_ALIGNMENT = "spec_alignment"
    CANDIDATE_SR = "candidate_sr"
    IMPLEMENTATION_PLAN = "implementation_plan"
    TASK_MATERIALIZATION = "task_materialization"
    PLAN_TASK_ALIGNMENT = "plan_task_alignment"
    HUMAN_BOUNDARIES = "human_boundaries"
    FINAL_GATES = "final_gates"
    HANDOFF = "handoff"


@dataclass(frozen=True)
class AgentInvocation:
    schema: int
    run_id: str
    stage: PlanningStage
    revision: int
    attempt: int
    role: str
    input_hashes: dict[str, str]
    output_path: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "run_id": self.run_id,
            "stage": self.stage.value,
            "revision": self.revision,
            "attempt": self.attempt,
            "role": self.role,
            "input_hashes": dict(sorted(self.input_hashes.items())),
            "output_path": self.output_path,
        }


@dataclass(frozen=True)
class AgentResultRecord:
    schema: int
    run_id: str
    stage: PlanningStage
    revision: int
    attempt: int
    ok: bool
    payload: dict[str, object]
    payload_sha256: str
    session_id: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "run_id": self.run_id,
            "stage": self.stage.value,
            "revision": self.revision,
            "attempt": self.attempt,
            "ok": self.ok,
            "payload": self.payload,
            "payload_sha256": self.payload_sha256,
            "session_id": self.session_id,
            "error": self.error,
        }


@dataclass(frozen=True)
class GateRecord:
    schema: int
    run_id: str
    stage: PlanningStage
    revision: int
    attempt: int
    gate_id: str
    status: str
    detail: str
    evidence_sha256: str
    invocation_sha256: str = ""
    result_sha256: str = ""
    evidence: dict[str, object] | None = None

    @property
    def passed(self) -> bool:
        return self.status == "pass"

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "run_id": self.run_id,
            "stage": self.stage.value,
            "revision": self.revision,
            "attempt": self.attempt,
            "gate_id": self.gate_id,
            "status": self.status,
            "detail": self.detail,
            "evidence_sha256": self.evidence_sha256,
            "invocation_sha256": self.invocation_sha256,
            "result_sha256": self.result_sha256,
            "evidence": self.evidence if self.evidence is not None else {},
        }


@dataclass(frozen=True)
class WorkflowState:
    schema: int
    run_id: str
    current_stage: str | None
    blocked: bool
    reason: str | None
    completed_stages: tuple[str, ...]
    attempts: dict[str, int]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "run_id": self.run_id,
            "current_stage": self.current_stage,
            "blocked": self.blocked,
            "reason": self.reason,
            "completed_stages": list(self.completed_stages),
            "attempts": dict(sorted(self.attempts.items())),
        }


@dataclass
class _AttemptState:
    begin: dict[str, object]
    result: dict[str, object] | None = None
    gate: dict[str, object] | None = None
    blocked: bool = False
    block_reason: str | None = None
    advanced: bool = False
    invocation: AgentInvocation | None = None
    result_record: AgentResultRecord | None = None
    gate_record: GateRecord | None = None


_Identity = tuple[str, int, int]
_STAGE_ORDER = tuple(PlanningStage)
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_RESULT_KEYS = {"ok", "payload", "session_id", "error"}
_ALLOWED_ACTIONS = {"begin", "result", "gate", "advance", "block"}
_EVENT_BASE_KEYS = {"schema", "action", "run_id", "sequence"}
_EVENT_KEYS = {
    "begin": _EVENT_BASE_KEYS | {"stage", "revision", "attempt", "role", "input_hashes", "output_path"},
    "result": _EVENT_BASE_KEYS | {"stage", "revision", "attempt", "ok", "result_path", "payload_sha256", "result_sha256"},
    "gate": _EVENT_BASE_KEYS
    | {
        "stage",
        "revision",
        "attempt",
        "gate_id",
        "status",
        "detail",
        "evidence_sha256",
        "invocation_sha256",
        "result_sha256",
    },
    "advance": _EVENT_BASE_KEYS | {"stage", "revision", "attempt", "next_stage"},
    "block": _EVENT_BASE_KEYS | {"stage", "revision", "attempt", "reason", "detail"},
}
_INVOCATION_KEYS = {
    "schema",
    "run_id",
    "stage",
    "revision",
    "attempt",
    "role",
    "input_hashes",
    "output_path",
}
_RESULT_KEYS = {
    "schema",
    "run_id",
    "stage",
    "revision",
    "attempt",
    "ok",
    "payload",
    "payload_sha256",
    "session_id",
    "error",
}
_GATE_KEYS = {
    "schema",
    "run_id",
    "stage",
    "revision",
    "attempt",
    "gate_id",
    "status",
    "detail",
    "evidence_sha256",
    "invocation_sha256",
    "result_sha256",
    "evidence",
}


def _reject_constant(value: str) -> object:
    raise ValueError(f"non-standard JSON constant {value!r} is not allowed")


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _reject_nonfinite(value: object) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("non-finite JSON number is not allowed")
    if isinstance(value, list):
        for item in value:
            _reject_nonfinite(item)
    elif isinstance(value, dict):
        for item in value.values():
            _reject_nonfinite(item)


def _strict_json_loads(raw: bytes | str) -> object:
    if isinstance(raw, bytes):
        text = raw.decode("utf-8")
        if len(raw) > 1_048_576:
            raise ValueError("JSON input is oversized")
    elif isinstance(raw, str):
        if len(raw.encode("utf-8")) > 1_048_576:
            raise ValueError("JSON input is oversized")
        text = raw
    else:
        raise TypeError("JSON input must be UTF-8 bytes or text")
    value = json.loads(
        text,
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_constant,
    )
    _reject_nonfinite(value)
    return value


def _validate_json_value(value: object) -> None:
    if value is None or type(value) is bool or type(value) is int:
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise RunnerError("workflow value is not strict JSON")
        return
    if isinstance(value, str):
        return
    if isinstance(value, list):
        for item in value:
            _validate_json_value(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise RunnerError("workflow object keys must be strings")
            _validate_json_value(item)
        return
    raise RunnerError("workflow value is not strict JSON")


def _safe_id(value: object, field: str) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None or len(value) > 128:
        raise RunnerError(f"invalid {field}")
    return value


def _safe_text(value: object, field: str, *, required: bool = True) -> str:
    if not isinstance(value, str) or (required and not value.strip()) or any(ord(char) < 32 for char in value):
        raise RunnerError(f"invalid {field}")
    return value


def _safe_relative(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or any(ord(char) < 32 for char in value):
        raise RunnerError(f"invalid {field}")
    normalized = value.replace("\\", "/")
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
        raise RunnerError(f"invalid {field}")
    parts = normalized.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise RunnerError(f"invalid {field}")
    return normalized


def _positive_int(value: object, field: str) -> int:
    if type(value) is not int or value < 1:
        raise RunnerError(f"invalid {field}")
    return value


def _stage(value: object) -> PlanningStage:
    if not isinstance(value, str):
        raise RunnerError("invalid stage")
    try:
        return PlanningStage(value)
    except ValueError as exc:
        raise RunnerError("invalid stage") from exc


def _validated_input_hashes(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        raise RunnerError("invalid input hashes")
    hashes: dict[str, str] = {}
    for raw_path, raw_hash in value.items():
        relative = _safe_relative(raw_path, "input path")
        if relative != raw_path or not isinstance(raw_hash, str) or _SHA256.fullmatch(raw_hash) is None:
            raise RunnerError("invalid input hashes")
        if relative in hashes:
            raise RunnerError("duplicate input path")
        hashes[relative] = raw_hash
    if list(hashes) != sorted(hashes):
        raise RunnerError("input hashes are not canonical")
    return hashes


def _canonical(value: object) -> bytes:
    _validate_json_value(value)
    try:
        return json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise RunnerError("workflow value is not strict JSON") from exc


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _record_sha(record: AgentResultRecord | GateRecord | AgentInvocation) -> str:
    return _sha(_canonical(record.to_dict()))


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=".runner-", suffix=".tmp", dir=str(path.parent))
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _invocation_from_record(value: object, expected_run_id: str) -> AgentInvocation:
    if not isinstance(value, dict) or set(value) != _INVOCATION_KEYS:
        raise RunnerError("invocation record schema is invalid")
    if type(value.get("schema")) is not int or value.get("schema") != 1:
        raise RunnerError("invocation record schema is invalid")
    run_id = _safe_id(value.get("run_id"), "run_id")
    if run_id != expected_run_id:
        raise RunnerError("invocation identity is invalid")
    stage = _stage(value.get("stage"))
    revision = _positive_int(value.get("revision"), "revision")
    attempt = _positive_int(value.get("attempt"), "attempt")
    role = _safe_id(value.get("role"), "role")
    input_hashes = _validated_input_hashes(value.get("input_hashes"))
    output_path = _safe_relative(value.get("output_path"), "output target")
    if output_path != value.get("output_path"):
        raise RunnerError("invalid output target")
    return AgentInvocation(1, run_id, stage, revision, attempt, role, input_hashes, output_path)


def _result_from_record(value: object, expected_run_id: str) -> AgentResultRecord:
    if not isinstance(value, dict) or set(value) != _RESULT_KEYS:
        raise RunnerError("result record schema is invalid")
    if type(value.get("schema")) is not int or value.get("schema") != 1:
        raise RunnerError("result record schema is invalid")
    run_id = _safe_id(value.get("run_id"), "run_id")
    if run_id != expected_run_id:
        raise RunnerError("result identity is invalid")
    stage = _stage(value.get("stage"))
    revision = _positive_int(value.get("revision"), "revision")
    attempt = _positive_int(value.get("attempt"), "attempt")
    ok = value.get("ok")
    payload = value.get("payload")
    if type(ok) is not bool or not isinstance(payload, dict):
        raise RunnerError("result record schema is invalid")
    _validate_json_value(payload)
    if "output_path" in payload or "path" in payload or "target" in payload:
        raise RunnerError("worker-selected output target is not allowed")
    payload_sha256 = value.get("payload_sha256")
    if not isinstance(payload_sha256, str) or _SHA256.fullmatch(payload_sha256) is None:
        raise RunnerError("result payload hash is invalid")
    if payload_sha256 != _sha(_canonical(payload)):
        raise RunnerError("result payload hash does not match")
    session_id = value.get("session_id")
    if session_id is not None:
        session_id = _safe_id(session_id, "session_id")
    error = value.get("error")
    if error is not None:
        error = _safe_text(error, "agent error", required=False)
    return AgentResultRecord(
        1,
        run_id,
        stage,
        revision,
        attempt,
        ok,
        dict(payload),
        payload_sha256,
        session_id,
        error,
    )


def _gate_evidence_hash(invocation_sha256: str, result_sha256: str, evidence: dict[str, object]) -> str:
    return _sha(
        _canonical(
            {
                "invocation_sha256": invocation_sha256,
                "result_sha256": result_sha256,
                "evidence": evidence,
            }
        )
    )


def _gate_from_record(value: object, expected_run_id: str) -> GateRecord:
    if not isinstance(value, dict) or set(value) != _GATE_KEYS:
        raise RunnerError("gate record schema is invalid")
    if type(value.get("schema")) is not int or value.get("schema") != 1:
        raise RunnerError("gate record schema is invalid")
    run_id = _safe_id(value.get("run_id"), "run_id")
    if run_id != expected_run_id:
        raise RunnerError("gate identity is invalid")
    stage = _stage(value.get("stage"))
    revision = _positive_int(value.get("revision"), "revision")
    attempt = _positive_int(value.get("attempt"), "attempt")
    gate_id = _safe_id(value.get("gate_id"), "gate_id")
    status = value.get("status")
    if not isinstance(status, str) or status not in {"pass", "fail"}:
        raise RunnerError("gate status is invalid")
    detail = _safe_text(value.get("detail"), "gate detail")
    evidence_sha256 = value.get("evidence_sha256")
    invocation_sha256 = value.get("invocation_sha256")
    result_sha256 = value.get("result_sha256")
    if (
        not isinstance(evidence_sha256, str)
        or _SHA256.fullmatch(evidence_sha256) is None
        or not isinstance(invocation_sha256, str)
        or _SHA256.fullmatch(invocation_sha256) is None
        or not isinstance(result_sha256, str)
        or _SHA256.fullmatch(result_sha256) is None
    ):
        raise RunnerError("gate evidence binding is invalid")
    evidence = value.get("evidence")
    if not isinstance(evidence, dict):
        raise RunnerError("gate evidence is invalid")
    _validate_json_value(evidence)
    if evidence_sha256 != _gate_evidence_hash(invocation_sha256, result_sha256, evidence):
        raise RunnerError("gate evidence hash does not match")
    return GateRecord(
        1,
        run_id,
        stage,
        revision,
        attempt,
        gate_id,
        status,
        detail,
        evidence_sha256,
        invocation_sha256,
        result_sha256,
        dict(evidence),
    )


class PlanningRunner:
    """Drive one planning run as a single-writer deterministic state machine."""

    def __init__(self, project_root: Path, run_id: str) -> None:
        safe = safe_root(project_root)
        if safe is None:
            raise RunnerError("project root is unsafe")
        self.project_root = safe
        self.run_id = _safe_id(run_id, "run_id")
        run_dir = safe_resolve(safe, safe / ".factory" / "planning" / self.run_id)
        if run_dir is None:
            raise RunnerError("planning run path is unsafe")
        self.run_dir = run_dir
        self.events_path = self.run_dir / "workflow-events.jsonl"
        self.state_path = self.run_dir / "workflow-state.json"
        self._events()

    def begin(
        self,
        stage: PlanningStage | str,
        *,
        role: str,
        input_paths: Sequence[Path],
        output_path: str,
    ) -> AgentInvocation:
        requested = _stage(stage)
        state = self.status()
        expected = _STAGE_ORDER[len(state.completed_stages)] if len(state.completed_stages) < len(_STAGE_ORDER) else None
        if requested is not expected:
            expected_name = expected.value if expected is not None else "none"
            raise RunnerError(f"expected stage {expected_name}, got {requested.value}")
        role_id = _safe_id(role, "role")
        relative_output = _safe_relative(output_path, "output target")
        if relative_output != output_path:
            raise RunnerError("invalid output target")
        output = self._safe_path(self.project_root / relative_output, "output target")
        if output is None:
            raise RunnerError("output target is outside the project root")

        hashes: dict[str, str] = {}
        for input_path in input_paths:
            safe_input = safe_resolve(self.project_root, input_path)
            if safe_input is None or not safe_input.is_file():
                raise RunnerBlocked("input is missing or unsafe")
            relative = safe_input.relative_to(self.project_root).as_posix()
            if relative in hashes:
                raise RunnerError("duplicate input path")
            try:
                safe_input = safe_resolve(self.project_root, input_path)
                if safe_input is None:
                    raise RunnerBlocked("input is unsafe")
                hashes[relative] = _sha(safe_input.read_bytes())
            except OSError as exc:
                raise RunnerBlocked("input is unreadable") from exc
        hashes = dict(sorted(hashes.items()))

        events = self._events()
        _, attempts = self._validate_event_history(events)
        prior_state = attempts.get(requested.value)
        prior = prior_state.begin if prior_state is not None else None
        if prior_state is not None and not (prior_state.blocked or self._attempt_failed(prior_state)):
            raise RunnerError("current attempt is unfinished")
        if prior is None:
            revision, attempt = 1, 1
        else:
            prior_revision = _positive_int(prior.get("revision"), "revision")
            prior_attempt = _positive_int(prior.get("attempt"), "attempt")
            prior_hashes = _validated_input_hashes(prior.get("input_hashes"))
            if prior_hashes == hashes:
                revision, attempt = prior_revision, prior_attempt + 1
            else:
                revision, attempt = prior_revision + 1, 1

        invocation = AgentInvocation(1, self.run_id, requested, revision, attempt, role_id, hashes, relative_output)
        invocation_path = self._record_file(invocation, "invocation.json")
        if invocation_path.exists():
            raise RunnerError("invocation record already exists")
        self._write_json(invocation_path, invocation.to_dict(), "invocation record")
        self._append(
            {
                "action": "begin",
                "run_id": self.run_id,
                "stage": requested.value,
                "revision": revision,
                "attempt": attempt,
                "role": role_id,
                "input_hashes": invocation.input_hashes,
                "output_path": relative_output,
            }
        )
        return invocation

    def record_result(self, invocation: AgentInvocation, result: Mapping[str, object]) -> AgentResultRecord:
        self._validate_invocation(invocation)
        self._assert_current_attempt(invocation, require_no_result=True)
        self._assert_inputs_current(invocation)
        if not isinstance(result, Mapping):
            raise RunnerError("agent result schema is invalid")
        result_data = dict(result)
        if any(not isinstance(key, str) for key in result_data) or set(result_data) - _ALLOWED_RESULT_KEYS or "ok" not in result_data or "payload" not in result_data:
            raise RunnerError("agent result schema is invalid")
        ok = result_data.get("ok")
        payload = result_data.get("payload")
        if type(ok) is not bool or not isinstance(payload, dict):
            raise RunnerError("agent result schema is invalid")
        _validate_json_value(payload)
        if "output_path" in payload or "path" in payload or "target" in payload:
            raise RunnerError("worker-selected output target is not allowed")
        session_id = result_data.get("session_id")
        if session_id is not None:
            session_id = _safe_id(session_id, "session_id")
        error = result_data.get("error")
        if error is not None:
            error = _safe_text(error, "agent error", required=False)
        record = AgentResultRecord(
            1,
            self.run_id,
            invocation.stage,
            invocation.revision,
            invocation.attempt,
            ok,
            dict(payload),
            _sha(_canonical(payload)),
            session_id,
            error,
        )
        result_path = self._record_file(invocation, "result.json")
        if result_path.exists():
            raise RunnerError("result record already exists")
        self._write_json(result_path, record.to_dict(), "result record")
        self._append(
            {
                "action": "result",
                "run_id": self.run_id,
                "stage": invocation.stage.value,
                "revision": invocation.revision,
                "attempt": invocation.attempt,
                "ok": ok,
                "result_path": result_path.relative_to(self.project_root).as_posix(),
                "payload_sha256": record.payload_sha256,
                "result_sha256": _record_sha(record),
            }
        )
        if not ok:
            reason = error or "agent returned a failed result"
            self._block(invocation, "agent_result_failed", reason)
            raise RunnerBlocked(reason)
        return record

    def record_gate(
        self,
        invocation: AgentInvocation,
        *,
        gate_id: str,
        passed: bool,
        detail: str,
        evidence: Mapping[str, object] | None = None,
    ) -> GateRecord:
        self._validate_invocation(invocation)
        self._assert_current_attempt(invocation)
        self._assert_inputs_current(invocation)
        gate = _safe_id(gate_id, "gate_id")
        if type(passed) is not bool:
            raise RunnerError("gate result must be boolean")
        detail_text = _safe_text(detail, "gate detail")
        try:
            result_record = self._read_current_result(invocation)
            if result_record.ok is not True:
                raise RunnerError("failed agent result cannot pass a gate")
        except RunnerBlocked:
            raise
        except RunnerError as exc:
            self._durable_block(invocation, "gate_evidence_invalid", str(exc))
            raise RunnerBlocked("agent result is unreadable") from exc
        if evidence is None:
            evidence_payload: dict[str, object] = {"detail": detail_text}
        elif isinstance(evidence, Mapping):
            evidence_payload = dict(evidence)
        else:
            raise RunnerError("gate evidence is invalid")
        _validate_json_value(evidence_payload)
        invocation_sha256 = _record_sha(invocation)
        result_sha256 = _record_sha(result_record)
        evidence_sha256 = _gate_evidence_hash(invocation_sha256, result_sha256, evidence_payload)
        record = GateRecord(
            1,
            self.run_id,
            invocation.stage,
            invocation.revision,
            invocation.attempt,
            gate,
            "pass" if passed else "fail",
            detail_text,
            evidence_sha256,
            invocation_sha256,
            result_sha256,
            evidence_payload,
        )
        gate_path = self._record_file(invocation, "gate.json")
        if gate_path.exists():
            raise RunnerError("gate record already exists")
        self._write_json(gate_path, record.to_dict(), "gate record")
        self._append(
            {
                "action": "gate",
                "run_id": self.run_id,
                "stage": invocation.stage.value,
                "revision": invocation.revision,
                "attempt": invocation.attempt,
                "gate_id": gate,
                "status": record.status,
                "detail": detail_text,
                "evidence_sha256": evidence_sha256,
                "invocation_sha256": invocation_sha256,
                "result_sha256": result_sha256,
            }
        )
        if not passed:
            self._block(invocation, "gate_failed", detail_text)
        return record

    def advance(self, invocation: AgentInvocation) -> PlanningStage | None:
        self._validate_invocation(invocation)
        events = self._events()
        completed, attempts = self._validate_event_history(events)
        current = _STAGE_ORDER[len(completed)] if len(completed) < len(_STAGE_ORDER) else None
        if current is not invocation.stage:
            raise RunnerError("invocation is not for the current stage")
        state = attempts.get(invocation.stage.value)
        if state is None or not self._begin_matches(state, invocation):
            raise RunnerError("invocation is not the current attempt")
        try:
            self._assert_inputs_current(invocation)
        except RunnerBlocked:
            raise
        try:
            result_record = self._read_current_result(invocation)
            gate_record = self._read_current_gate(invocation, result_record)
            if result_record.ok is not True:
                raise RunnerError("agent result did not pass")
            if not gate_record.passed:
                raise RunnerError("gate did not pass")
        except RunnerError as exc:
            self._durable_block(invocation, "advance_evidence_invalid", str(exc))
            raise RunnerBlocked("result and gate evidence are required") from exc
        next_index = _STAGE_ORDER.index(invocation.stage) + 1
        next_stage = _STAGE_ORDER[next_index] if next_index < len(_STAGE_ORDER) else None
        self._append(
            {
                "action": "advance",
                "run_id": self.run_id,
                "stage": invocation.stage.value,
                "revision": invocation.revision,
                "attempt": invocation.attempt,
                "next_stage": next_stage.value if next_stage is not None else None,
            }
        )
        return next_stage

    def status(self) -> WorkflowState:
        events = self._events()
        completed, attempts = self._validate_event_history(events)
        self._validate_history_records(events, attempts)
        current = _STAGE_ORDER[len(completed)].value if len(completed) < len(_STAGE_ORDER) else None
        current_attempt = attempts.get(current) if current is not None else None
        blocked = current_attempt.blocked if current_attempt is not None else False
        reason = current_attempt.block_reason if blocked and current_attempt is not None else None
        latest_attempts = {
            stage: _positive_int(attempt.begin.get("attempt"), "attempt")
            for stage, attempt in attempts.items()
        }
        return WorkflowState(1, self.run_id, current, blocked, reason, tuple(stage.value for stage in _STAGE_ORDER[: len(completed)]), latest_attempts)

    def _safe_path(self, path: Path, label: str) -> Path:
        safe = safe_resolve(self.project_root, path)
        if safe is None:
            raise RunnerError(f"{label} path is unsafe")
        return safe

    def _write_json(self, path: Path, value: object, label: str) -> None:
        self._safe_path(path, label)
        _validate_json_value(value)
        try:
            content = json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
        except (TypeError, ValueError) as exc:
            raise RunnerError(f"{label} is not strict JSON") from exc
        safe = self._safe_path(path, label)
        _atomic_write(safe, content)

    def _read_json(self, path: Path, label: str) -> object:
        safe = self._safe_path(path, label)
        try:
            raw = safe.read_bytes()
            return _strict_json_loads(raw)
        except (OSError, UnicodeError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RunnerError(f"{label} is unreadable") from exc

    def _record_dir_for(self, stage: PlanningStage, revision: int, attempt: int) -> Path:
        path = (
            self.project_root
            / ".factory"
            / "planning"
            / self.run_id
            / "stages"
            / stage.value
            / f"r{revision}"
            / f"a{attempt}"
        )
        return self._safe_path(path, "stage record")

    def _record_dir(self, invocation: AgentInvocation) -> Path:
        return self._record_dir_for(invocation.stage, invocation.revision, invocation.attempt)

    def _record_file(self, invocation: AgentInvocation, filename: str) -> Path:
        return self._safe_path(self._record_dir(invocation) / filename, f"{filename} record")

    def _record_file_from_event(self, event: Mapping[str, object], filename: str) -> Path:
        stage = _stage(event.get("stage"))
        revision = _positive_int(event.get("revision"), "revision")
        attempt = _positive_int(event.get("attempt"), "attempt")
        return self._safe_path(self._record_dir_for(stage, revision, attempt) / filename, f"{filename} record")

    def _validate_invocation(self, invocation: AgentInvocation) -> None:
        if not isinstance(invocation, AgentInvocation):
            raise RunnerError("invocation identity is invalid")
        if type(invocation.schema) is not int or invocation.schema != 1:
            raise RunnerError("invocation identity is invalid")
        run_id = _safe_id(invocation.run_id, "run_id")
        if run_id != self.run_id or not isinstance(invocation.stage, PlanningStage):
            raise RunnerError("invocation identity is invalid")
        _positive_int(invocation.revision, "revision")
        _positive_int(invocation.attempt, "attempt")
        _safe_id(invocation.role, "role")
        _validated_input_hashes(invocation.input_hashes)
        output_path = _safe_relative(invocation.output_path, "output target")
        if output_path != invocation.output_path:
            raise RunnerError("invocation output target is invalid")
        expected = self._record_file(invocation, "invocation.json")
        if not expected.is_file():
            raise RunnerError("invocation record is missing")
        stored = _invocation_from_record(self._read_json(expected, "invocation record"), self.run_id)
        if stored.to_dict() != invocation.to_dict():
            raise RunnerError("invocation record does not match")
        events = self._events()
        expected_event = invocation.to_dict()
        for event in events:
            if event.get("action") == "begin" and self._event_identity(event) == self._identity(invocation):
                if {key: event[key] for key in expected_event} == expected_event:
                    return
        raise RunnerError("invocation journal record is missing")

    def _identity(self, invocation: AgentInvocation) -> _Identity:
        return invocation.stage.value, invocation.revision, invocation.attempt

    def _begin_matches(self, state: _AttemptState, invocation: AgentInvocation) -> bool:
        expected = invocation.to_dict()
        return {key: state.begin[key] for key in expected} == expected

    def _event_identity(self, event: Mapping[str, object]) -> _Identity:
        stage = _stage(event.get("stage"))
        return stage.value, _positive_int(event.get("revision"), "revision"), _positive_int(event.get("attempt"), "attempt")

    def _attempt_failed(self, state: _AttemptState) -> bool:
        if state.result is not None and state.result.get("ok") is False:
            return True
        return state.gate is not None and state.gate.get("status") == "fail"

    def _assert_current_attempt(self, invocation: AgentInvocation, *, require_no_result: bool = False) -> None:
        events = self._events()
        completed, attempts = self._validate_event_history(events)
        current = _STAGE_ORDER[len(completed)] if len(completed) < len(_STAGE_ORDER) else None
        state = attempts.get(invocation.stage.value)
        if current is not invocation.stage or state is None or not self._begin_matches(state, invocation):
            raise RunnerError("invocation is not the current attempt")
        if state.blocked or self._attempt_failed(state):
            raise RunnerBlocked("current attempt is blocked")
        if require_no_result and state.result is not None:
            raise RunnerError("result record already exists")

    def _assert_inputs_current(self, invocation: AgentInvocation) -> None:
        for relative, expected in invocation.input_hashes.items():
            path = self._safe_path(self.project_root / relative, "input")
            if not path.is_file():
                self._block(invocation, "stale_input", "input is missing or unsafe")
                raise RunnerBlocked("stale input")
            try:
                path = self._safe_path(self.project_root / relative, "input")
                actual = _sha(path.read_bytes())
            except OSError as exc:
                self._block(invocation, "stale_input", "input is unreadable")
                raise RunnerBlocked("stale input") from exc
            if actual != expected:
                self._block(invocation, "stale_input", "input hash changed")
                raise RunnerBlocked("stale input")

    def _read_current_result(self, invocation: AgentInvocation) -> AgentResultRecord:
        events = self._events()
        _, attempts = self._validate_event_history(events)
        state = attempts.get(invocation.stage.value)
        if state is None or not self._begin_matches(state, invocation) or state.result is None:
            raise RunnerError("result journal record is missing")
        raw = self._read_json(self._record_file(invocation, "result.json"), "result record")
        record = _result_from_record(raw, self.run_id)
        if record.to_dict() != raw or (
            record.stage is not invocation.stage
            or record.revision != invocation.revision
            or record.attempt != invocation.attempt
        ):
            raise RunnerError("result record identity is invalid")
        event = state.result
        expected_path = self._record_file(invocation, "result.json").relative_to(self.project_root).as_posix()
        if (
            event.get("result_path") != expected_path
            or event.get("ok") is not record.ok
            or event.get("payload_sha256") != record.payload_sha256
            or event.get("result_sha256") != _record_sha(record)
        ):
            raise RunnerError("result journal record does not match")
        return record

    def _read_current_gate(self, invocation: AgentInvocation, result_record: AgentResultRecord) -> GateRecord:
        events = self._events()
        _, attempts = self._validate_event_history(events)
        state = attempts.get(invocation.stage.value)
        if state is None or not self._begin_matches(state, invocation) or state.gate is None:
            raise RunnerError("gate journal record is missing")
        raw = self._read_json(self._record_file(invocation, "gate.json"), "gate record")
        record = _gate_from_record(raw, self.run_id)
        if record.to_dict() != raw:
            raise RunnerError("gate record is not canonical")
        invocation_sha256 = _record_sha(invocation)
        result_sha256 = _record_sha(result_record)
        if (
            record.stage is not invocation.stage
            or record.revision != invocation.revision
            or record.attempt != invocation.attempt
            or record.invocation_sha256 != invocation_sha256
            or record.result_sha256 != result_sha256
            or record.evidence_sha256 != _gate_evidence_hash(invocation_sha256, result_sha256, record.evidence or {})
        ):
            raise RunnerError("gate evidence binding does not match")
        event = state.gate
        if (
            event.get("gate_id") != record.gate_id
            or event.get("status") != record.status
            or event.get("detail") != record.detail
            or event.get("evidence_sha256") != record.evidence_sha256
            or event.get("invocation_sha256") != record.invocation_sha256
            or event.get("result_sha256") != record.result_sha256
        ):
            raise RunnerError("gate journal record does not match")
        return record

    def _durable_block(self, invocation: AgentInvocation, reason: str, detail: str) -> None:
        events = self._events()
        identity = self._identity(invocation)
        if any(event.get("action") == "block" and self._event_identity(event) == identity for event in events):
            return
        self._block(invocation, reason, detail)

    def _block(self, invocation: AgentInvocation, reason: str, detail: str) -> None:
        self._append(
            {
                "action": "block",
                "run_id": self.run_id,
                "stage": invocation.stage.value,
                "revision": invocation.revision,
                "attempt": invocation.attempt,
                "reason": _safe_id(reason, "block reason"),
                "detail": _safe_text(detail, "block detail"),
            }
        )

    def _validate_event_schema(self, event: object, expected_sequence: int) -> dict[str, object]:
        if not isinstance(event, dict) or any(not isinstance(key, str) for key in event):
            raise RunnerError("workflow journal event is invalid")
        action = event.get("action")
        if not isinstance(action, str) or action not in _ALLOWED_ACTIONS or set(event) != _EVENT_KEYS[action]:
            raise RunnerError("workflow journal event schema is invalid")
        if type(event.get("schema")) is not int or event.get("schema") != 1:
            raise RunnerError("workflow journal event schema is invalid")
        if event.get("sequence") != expected_sequence or type(event.get("sequence")) is not int:
            raise RunnerError("workflow journal sequence is invalid")
        run_id = _safe_id(event.get("run_id"), "run_id")
        if run_id != self.run_id:
            raise RunnerError("workflow journal run identity is invalid")
        stage = _stage(event.get("stage"))
        _positive_int(event.get("revision"), "revision")
        _positive_int(event.get("attempt"), "attempt")
        if action == "begin":
            _safe_id(event.get("role"), "role")
            _validated_input_hashes(event.get("input_hashes"))
            output = _safe_relative(event.get("output_path"), "output target")
            if output != event.get("output_path"):
                raise RunnerError("workflow output target is invalid")
        elif action == "result":
            if type(event.get("ok")) is not bool:
                raise RunnerError("workflow result status is invalid")
            result_path = _safe_relative(event.get("result_path"), "result path")
            expected_path = self._record_dir_for(stage, int(event["revision"]), int(event["attempt"])) / "result.json"
            expected_relative = expected_path.relative_to(self.project_root).as_posix()
            if result_path != event.get("result_path") or result_path != expected_relative:
                raise RunnerError("workflow result path is invalid")
            for field in ("payload_sha256", "result_sha256"):
                value = event.get(field)
                if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
                    raise RunnerError("workflow result hash is invalid")
        elif action == "gate":
            _safe_id(event.get("gate_id"), "gate_id")
            status = event.get("status")
            if not isinstance(status, str) or status not in {"pass", "fail"}:
                raise RunnerError("workflow gate status is invalid")
            _safe_text(event.get("detail"), "gate detail")
            for field in ("evidence_sha256", "invocation_sha256", "result_sha256"):
                value = event.get(field)
                if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
                    raise RunnerError("workflow gate hash is invalid")
        elif action == "advance":
            next_stage = event.get("next_stage")
            stage_index = _STAGE_ORDER.index(stage) + 1
            expected_next = _STAGE_ORDER[stage_index].value if stage_index < len(_STAGE_ORDER) else None
            if next_stage != expected_next:
                raise RunnerError("workflow advance target is invalid")
        else:
            _safe_id(event.get("reason"), "block reason")
            _safe_text(event.get("detail"), "block detail")
        return event

    def _validate_event_history(self, events: Sequence[dict[str, object]]) -> tuple[list[PlanningStage], dict[str, _AttemptState]]:
        completed: list[PlanningStage] = []
        attempts: dict[str, _AttemptState] = {}
        identities: dict[_Identity, _AttemptState] = {}
        for event in events:
            action = event["action"]
            stage = _stage(event["stage"])
            if action == "begin":
                expected = _STAGE_ORDER[len(completed)] if len(completed) < len(_STAGE_ORDER) else None
                if stage is not expected:
                    raise RunnerError("workflow stage sequence is invalid")
                previous = attempts.get(stage.value)
                revision = _positive_int(event["revision"], "revision")
                attempt = _positive_int(event["attempt"], "attempt")
                if previous is None:
                    if (revision, attempt) != (1, 1):
                        raise RunnerError("workflow initial attempt is invalid")
                else:
                    if previous.advanced or not (previous.blocked or self._attempt_failed(previous)):
                        raise RunnerError("workflow attempt is unfinished")
                    prior_revision = _positive_int(previous.begin["revision"], "revision")
                    prior_attempt = _positive_int(previous.begin["attempt"], "attempt")
                    prior_hashes = _validated_input_hashes(previous.begin["input_hashes"])
                    current_hashes = _validated_input_hashes(event["input_hashes"])
                    expected_identity = (
                        (prior_revision, prior_attempt + 1)
                        if prior_hashes == current_hashes
                        else (prior_revision + 1, 1)
                    )
                    if (revision, attempt) != expected_identity:
                        raise RunnerError("workflow retry identity is invalid")
                identity = (stage.value, revision, attempt)
                if identity in identities:
                    raise RunnerError("workflow attempt identity is duplicated")
                state = _AttemptState(event)
                attempts[stage.value] = state
                identities[identity] = state
            else:
                identity = self._event_identity(event)
                state = identities.get(identity)
                if state is None or attempts.get(stage.value) is not state:
                    raise RunnerError("workflow event identity is invalid")
                if action == "result":
                    if state.result is not None or state.gate is not None or state.blocked or state.advanced:
                        raise RunnerError("workflow result sequence is invalid")
                    state.result = event
                elif action == "gate":
                    if state.result is None or state.gate is not None or state.blocked or state.advanced:
                        raise RunnerError("workflow gate sequence is invalid")
                    state.gate = event
                elif action == "block":
                    if state.blocked or state.advanced:
                        raise RunnerError("workflow block sequence is invalid")
                    state.blocked = True
                    state.block_reason = str(event["reason"])
                elif action == "advance":
                    expected = _STAGE_ORDER[len(completed)] if len(completed) < len(_STAGE_ORDER) else None
                    if stage is not expected or state.result is None or state.gate is None or state.blocked:
                        raise RunnerError("workflow advance sequence is invalid")
                    if state.result.get("ok") is not True or state.gate.get("status") != "pass":
                        raise RunnerError("workflow advance evidence is invalid")
                    state.advanced = True
                    completed.append(stage)
        return completed, attempts

    def _validate_history_records(self, events: Sequence[dict[str, object]], attempts: dict[str, _AttemptState]) -> None:
        del attempts  # The event identities, not only the latest stage, are authoritative.
        invocations: dict[_Identity, AgentInvocation] = {}
        results: dict[_Identity, AgentResultRecord] = {}
        gates: dict[_Identity, GateRecord] = {}
        blocked: set[_Identity] = set()

        for event in events:
            identity = self._event_identity(event)
            action = event["action"]
            if action == "begin":
                invocation = _invocation_from_record(
                    self._read_json(self._record_file_from_event(event, "invocation.json"), "invocation record"),
                    self.run_id,
                )
                expected = invocation.to_dict()
                begin_fields = {key: event[key] for key in expected}
                if expected != begin_fields:
                    raise RunnerError("invocation journal record does not match")
                invocations[identity] = invocation
            elif action == "block":
                blocked.add(identity)

        for event in events:
            if event["action"] != "result":
                continue
            identity = self._event_identity(event)
            try:
                invocation = invocations.get(identity)
                if invocation is None:
                    raise RunnerError("invocation record is missing")
                record = _result_from_record(
                    self._read_json(self._record_file_from_event(event, "result.json"), "result record"),
                    self.run_id,
                )
                expected_path = self._record_file_from_event(event, "result.json").relative_to(self.project_root).as_posix()
                if (
                    record.stage is not invocation.stage
                    or record.revision != invocation.revision
                    or record.attempt != invocation.attempt
                    or event["result_path"] != expected_path
                    or event["ok"] is not record.ok
                    or event["payload_sha256"] != record.payload_sha256
                    or event["result_sha256"] != _record_sha(record)
                ):
                    raise RunnerError("result journal record does not match")
                results[identity] = record
            except RunnerError:
                if identity in blocked:
                    continue
                raise

        for event in events:
            if event["action"] != "gate":
                continue
            identity = self._event_identity(event)
            try:
                invocation = invocations.get(identity)
                result_record = results.get(identity)
                if invocation is None or result_record is None:
                    raise RunnerError("result record is missing")
                record = _gate_from_record(
                    self._read_json(self._record_file_from_event(event, "gate.json"), "gate record"),
                    self.run_id,
                )
                if (
                    record.stage is not invocation.stage
                    or record.revision != invocation.revision
                    or record.attempt != invocation.attempt
                    or record.invocation_sha256 != _record_sha(invocation)
                    or record.result_sha256 != _record_sha(result_record)
                    or event["gate_id"] != record.gate_id
                    or event["status"] != record.status
                    or event["detail"] != record.detail
                    or event["evidence_sha256"] != record.evidence_sha256
                    or event["invocation_sha256"] != record.invocation_sha256
                    or event["result_sha256"] != record.result_sha256
                ):
                    raise RunnerError("gate journal record does not match")
                gates[identity] = record
            except RunnerError:
                if identity in blocked:
                    continue
                raise

        for event in events:
            if event["action"] != "advance":
                continue
            identity = self._event_identity(event)
            result_record = results.get(identity)
            gate_record = gates.get(identity)
            if result_record is None or gate_record is None:
                raise RunnerError("advance evidence is missing")
            if not result_record.ok or not gate_record.passed:
                raise RunnerError("advance evidence did not pass")

    def _events(self) -> list[dict[str, object]]:
        path = self._safe_path(self.events_path, "workflow journal")
        if not path.exists():
            return []
        try:
            raw = self._safe_path(self.events_path, "workflow journal").read_bytes()
        except (OSError, UnicodeError) as exc:
            raise RunnerError("workflow journal is unreadable") from exc
        lines = raw.splitlines()
        events: list[dict[str, object]] = []
        for expected, line in enumerate(lines, 1):
            try:
                event = _strict_json_loads(line)
            except (UnicodeError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise RunnerError("workflow journal contains malformed JSON") from exc
            events.append(self._validate_event_schema(event, expected))
        self._validate_event_history(events)
        return events

    def _append(self, payload: Mapping[str, object]) -> None:
        if set(payload) & {"schema", "sequence"}:
            raise RunnerError("workflow event contains reserved fields")
        existing = self._events()
        event = {"schema": 1, **dict(payload), "sequence": len(existing) + 1}
        event = self._validate_event_schema(event, len(existing) + 1)
        run_dir = self._safe_path(self.run_dir, "planning run")
        run_dir.mkdir(parents=True, exist_ok=True)
        events_path = self._safe_path(self.events_path, "workflow journal")
        encoded = _canonical(event).decode("utf-8") + "\n"
        try:
            fd = os.open(events_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8", newline="\n") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
        except (OSError, TypeError, ValueError) as exc:
            raise RunnerError("workflow event could not be appended") from exc
        self._write_json(self.state_path, self.status().to_dict(), "workflow state")


__all__ = [
    "AgentInvocation",
    "AgentResultRecord",
    "GateRecord",
    "PlanningRunner",
    "PlanningStage",
    "RunnerBlocked",
    "RunnerError",
    "WorkflowState",
]
