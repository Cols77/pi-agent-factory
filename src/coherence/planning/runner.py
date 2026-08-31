"""Parent-owned deterministic planning workflow state machine."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
import threading
from contextlib import contextmanager
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from collections.abc import Iterator

if os.name == "nt":
    import msvcrt
else:
    import fcntl

from coherence.planning.paths import safe_resolve, safe_root


class RunnerError(ValueError):
    """Raised when a planning-runner contract is invalid."""


class RunnerBlocked(RunnerError):
    """Raised when a run must remain blocked until a new attempt or decision."""


class _RunnerEncodeError(RunnerError):
    """Raised when a controlled record cannot be encoded for persistence."""


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
    input_hashes: Mapping[str, str]
    output_path: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "input_hashes", _freeze(self.input_hashes))

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "run_id": self.run_id,
            "stage": self.stage.value,
            "revision": self.revision,
            "attempt": self.attempt,
            "role": self.role,
            "input_hashes": {
                key: value for key, value in sorted(self.input_hashes.items())
            },
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
    payload: Mapping[str, object]
    payload_sha256: str
    session_id: str | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", _freeze(self.payload))

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "run_id": self.run_id,
            "stage": self.stage.value,
            "revision": self.revision,
            "attempt": self.attempt,
            "ok": self.ok,
            "payload": _thaw(self.payload),
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
    output_sha256: str = ""
    evidence: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        if self.evidence is not None:
            object.__setattr__(self, "evidence", _freeze(self.evidence))

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
            "output_sha256": self.output_sha256,
            "evidence": _thaw(self.evidence) if self.evidence is not None else {},
        }


@dataclass(frozen=True)
class GateVerification:
    """A parent-owned, invocation/result-bound gate attestation."""

    gate_id: str
    passed: bool
    detail: str
    evidence: Mapping[str, object]
    invocation_sha256: str
    result_sha256: str
    output_sha256: str
    _capability: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", _freeze(self.evidence))


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
_EVENT_BASE_KEYS = {
    "schema",
    "action",
    "run_id",
    "sequence",
    "previous_sha256",
    "event_sha256",
}
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
        "output_sha256",
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
    "output_sha256",
    "evidence",
}
_RECOVERY_KEYS = {
    "schema",
    "run_id",
    "stage",
    "revision",
    "attempt",
    "reason",
    "detail",
}
_MAX_JSON_BYTES = 1_048_576
_MAX_JSON_DEPTH = 64
_MAX_JSON_NODES = 100_000
_MAX_WORKFLOW_JOURNAL_BYTES = 8 * _MAX_JSON_BYTES
_MAX_STRING_BYTES = 64 * 1024
_MAX_TEXT_BYTES = 16 * 1024
_MAX_PAYLOAD_BYTES = 64 * 1024
_MAX_EVIDENCE_BYTES = 64 * 1024
_GENESIS_SHA256 = "0" * 64
_OUTPUT_TARGET_KEYS = frozenset({"output_path", "output_target", "path", "target"})
_RUNNER_CONTROL_NAMES = frozenset(
    {
        ".runner-writer.lock",
        "workflow-events.jsonl",
        "workflow-integrity.json",
        "workflow-state.json",
        "workflow-recovery.json",
        "invocation.json",
        "result.json",
        "gate.json",
    }
)
_WINDOWS_RESERVED_NAMES = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "CLOCK$",
        *(f"COM{number}" for number in range(1, 10)),
        *(f"LPT{number}" for number in range(1, 10)),
        "COM¹",
        "COM²",
        "COM³",
        "LPT¹",
        "LPT²",
        "LPT³",
    }
)
_WRITER_LOCKS: dict[str, threading.RLock] = {}
_WRITER_LOCKS_GUARD = threading.Lock()
_WRITER_LOCK_STATE = threading.local()


@contextmanager
def _platform_file_lock(fd: int) -> Iterator[None]:
    """Hold one byte of a lock file across processes on the host platform."""
    if os.name == "nt":
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
    else:
        fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        yield
    finally:
        if os.name == "nt":
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(fd, fcntl.LOCK_UN)


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
    pending = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, float) and not math.isfinite(current):
            raise ValueError("non-finite JSON number is not allowed")
        if isinstance(current, Mapping):
            pending.extend(current.values())
        elif isinstance(current, (list, tuple)):
            pending.extend(current)


def _check_json_depth(text: str) -> None:
    depth = 0
    maximum = 0
    in_string = False
    escaped = False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
            maximum = max(maximum, depth)
            if maximum > _MAX_JSON_DEPTH:
                raise ValueError("JSON nesting is too deep")
        elif char in "]}":
            depth -= 1
    if depth != 0 or in_string:
        raise ValueError("JSON structure is incomplete")


def _strict_json_loads(raw: bytes | str) -> object:
    if isinstance(raw, bytes):
        if len(raw) > _MAX_JSON_BYTES:
            raise ValueError("JSON input is oversized")
        text = raw.decode("utf-8")
    elif isinstance(raw, str):
        if len(raw.encode("utf-8")) > _MAX_JSON_BYTES:
            raise ValueError("JSON input is oversized")
        text = raw
    else:
        raise TypeError("JSON input must be UTF-8 bytes or text")
    _check_json_depth(text)
    try:
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except RecursionError as exc:
        raise ValueError("JSON nesting is too deep") from exc
    _reject_nonfinite(value)
    return value


def _validate_json_value(value: object) -> None:
    pending: list[tuple[object, int]] = [(value, 0)]
    nodes = 0
    while pending:
        current, depth = pending.pop()
        nodes += 1
        if nodes > _MAX_JSON_NODES:
            raise RunnerError("workflow JSON value is oversized")
        if depth > _MAX_JSON_DEPTH:
            raise RunnerError("workflow JSON nesting is too deep")
        if current is None or type(current) is bool or type(current) is int:
            continue
        if type(current) is float:
            if not math.isfinite(current):
                raise RunnerError("workflow value is not strict JSON")
            continue
        if isinstance(current, str):
            if len(current.encode("utf-8")) > _MAX_STRING_BYTES:
                raise RunnerError("workflow string is oversized")
            continue
        if isinstance(current, Mapping):
            for key, item in current.items():
                if not isinstance(key, str):
                    raise RunnerError("workflow object keys must be strings")
                pending.append((item, depth + 1))
            continue
        if isinstance(current, (list, tuple)):
            pending.extend((item, depth + 1) for item in current)
            continue
        raise RunnerError("workflow value is not strict JSON")


def _freeze(value: object) -> object:
    _validate_json_value(value)
    return _freeze_unchecked(value)


def _freeze_unchecked(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze_unchecked(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_unchecked(item) for item in value)
    return value


def _thaw(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _reject_output_target_spoof(value: object) -> None:
    pending = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, Mapping):
            if any(key in _OUTPUT_TARGET_KEYS for key in current):
                raise RunnerError("worker-selected output target is not allowed")
            pending.extend(current.values())
        elif isinstance(current, (list, tuple)):
            pending.extend(current)


def _safe_id(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or _ID.fullmatch(value) is None
        or len(value) > 128
        or value.endswith(".")
        or _is_windows_reserved_component(value)
    ):
        raise RunnerError(f"invalid {field}")
    return value


def _safe_text(value: object, field: str, *, required: bool = True) -> str:
    if (
        not isinstance(value, str)
        or (required and not value.strip())
        or any(ord(char) < 32 for char in value)
        or len(value.encode("utf-8")) > _MAX_TEXT_BYTES
    ):
        raise RunnerError(f"invalid {field}")
    return value


def _is_runner_control_target(parts: Sequence[str]) -> bool:
    lowered = [part.casefold() for part in parts]
    return (
        lowered[-1] in _RUNNER_CONTROL_NAMES
        or len(lowered) >= 2 and lowered[0:2] == [".factory", "planning"]
    )


def _is_windows_reserved_component(part: str) -> bool:
    stem = part.rstrip(" .").split(".", 1)[0].upper()
    return stem in _WINDOWS_RESERVED_NAMES


def _safe_relative(value: object, field: str, *, allow_runner_control: bool = False) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or any(ord(char) < 32 for char in value):
        raise RunnerError(f"invalid {field}")
    normalized = value.replace("\\", "/")
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized) or ":" in normalized:
        raise RunnerError(f"invalid {field}")
    parts = normalized.split("/")
    if (
        any(part in {"", ".", ".."} for part in parts)
        or any(part.endswith((".", " ")) for part in parts)
        or any(_is_windows_reserved_component(part) for part in parts)
        or (not allow_runner_control and _is_runner_control_target(parts))
    ):
        raise RunnerError(f"invalid {field}")
    return normalized


def _bounded_json(value: object, field: str, maximum: int) -> bytes:
    _validate_json_value(value)
    encoded = _canonical(value)
    if len(encoded) > maximum:
        raise RunnerError(f"{field} is oversized")
    return encoded


def _read_limited(path: Path, maximum: int, label: str) -> bytes:
    try:
        if path.stat().st_size > maximum:
            raise RunnerError(f"{label} is oversized")
        with path.open("rb") as stream:
            raw = stream.read(maximum + 1)
    except RunnerError:
        raise
    except (OSError, ValueError) as exc:
        raise RunnerError(f"{label} is unreadable") from exc
    if len(raw) > maximum:
        raise RunnerError(f"{label} is oversized")
    return raw


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
    if not isinstance(value, Mapping):
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
        encoded = json.dumps(
            _thaw(value),
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (RecursionError, TypeError, ValueError) as exc:
        raise RunnerError("workflow value is not strict JSON") from exc
    if len(encoded) > _MAX_JSON_BYTES:
        raise RunnerError("workflow JSON value is oversized")
    return encoded


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _record_sha(record: AgentResultRecord | GateRecord | AgentInvocation) -> str:
    return _sha(_canonical(record.to_dict()))


def _event_sha(event: Mapping[str, object]) -> str:
    unsigned = {key: value for key, value in event.items() if key != "event_sha256"}
    return _sha(_canonical(unsigned))


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
    if type(ok) is not bool or not isinstance(payload, Mapping):
        raise RunnerError("result record schema is invalid")
    _reject_output_target_spoof(payload)
    payload_bytes = _bounded_json(payload, "result payload", _MAX_PAYLOAD_BYTES)
    payload_sha256 = value.get("payload_sha256")
    if not isinstance(payload_sha256, str) or _SHA256.fullmatch(payload_sha256) is None:
        raise RunnerError("result payload hash is invalid")
    if payload_sha256 != _sha(payload_bytes):
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


def _output_binding_hash(output_path: str) -> str:
    return _sha(_canonical({"output_path": output_path}))


def _gate_evidence_hash(
    invocation_sha256: str,
    result_sha256: str,
    output_sha256: str,
    evidence: Mapping[str, object],
) -> str:
    return _sha(
        _canonical(
            {
                "invocation_sha256": invocation_sha256,
                "result_sha256": result_sha256,
                "output_sha256": output_sha256,
                "evidence": evidence,
            }
        )
    )


def _gate_from_record(value: object, expected_run_id: str) -> GateRecord:
    if not isinstance(value, Mapping) or set(value) != _GATE_KEYS:
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
    output_sha256 = value.get("output_sha256")
    if (
        not isinstance(evidence_sha256, str)
        or _SHA256.fullmatch(evidence_sha256) is None
        or not isinstance(invocation_sha256, str)
        or _SHA256.fullmatch(invocation_sha256) is None
        or not isinstance(result_sha256, str)
        or _SHA256.fullmatch(result_sha256) is None
        or not isinstance(output_sha256, str)
        or _SHA256.fullmatch(output_sha256) is None
    ):
        raise RunnerError("gate evidence binding is invalid")
    evidence = value.get("evidence")
    if not isinstance(evidence, Mapping):
        raise RunnerError("gate evidence is invalid")
    _reject_output_target_spoof(evidence)
    _bounded_json(evidence, "gate evidence", _MAX_EVIDENCE_BYTES)
    if gate_id != f"gate-{stage.value}":
        raise RunnerError("gate is not in the trusted allowlist")
    if evidence_sha256 != _gate_evidence_hash(invocation_sha256, result_sha256, output_sha256, evidence):
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
        output_sha256,
        dict(evidence),
    )


class ParentGateVerifier:
    """Capability held by the parent workflow to attest one exact gate."""

    __slots__ = ("_runner", "_capability")

    def __init__(self, runner: PlanningRunner, capability: object) -> None:
        self._runner = runner
        self._capability = capability

    def attest(
        self,
        invocation: AgentInvocation,
        *,
        gate_id: str,
        passed: bool,
        detail: str,
        evidence: Mapping[str, object] | None = None,
    ) -> GateVerification:
        runner = self._runner
        try:
            runner._validate_invocation(invocation)
            runner._assert_current_attempt(invocation)
            runner._assert_inputs_current(invocation)
            runner._validate_output_binding(invocation)
        except RunnerBlocked:
            raise
        except RunnerError as exc:
            runner._durable_block(invocation, "gate_path_invalid", str(exc))
            raise RunnerBlocked("gate path is unsafe") from exc
        gate = _safe_id(gate_id, "gate_id")
        if gate != f"gate-{invocation.stage.value}":
            raise RunnerError("gate is not in the trusted allowlist")
        if type(passed) is not bool:
            raise RunnerError("gate result must be boolean")
        detail_text = _safe_text(detail, "gate detail")
        try:
            result_record = runner._read_current_result(invocation)
            if result_record.ok is not True:
                raise RunnerError("failed agent result cannot pass a gate")
            if evidence is None:
                evidence_payload: dict[str, object] = {"detail": detail_text}
            elif isinstance(evidence, Mapping):
                evidence_payload = dict(evidence)
            else:
                raise RunnerError("gate evidence is invalid")
            _reject_output_target_spoof(evidence_payload)
            _bounded_json(evidence_payload, "gate evidence", _MAX_EVIDENCE_BYTES)
            invocation_sha256 = _record_sha(invocation)
            result_sha256 = _record_sha(result_record)
            output_sha256 = _output_binding_hash(invocation.output_path)
            return GateVerification(
                gate,
                passed,
                detail_text,
                evidence_payload,
                invocation_sha256,
                result_sha256,
                output_sha256,
                self._capability,
            )
        except RunnerBlocked:
            raise
        except RunnerError as exc:
            runner._durable_block(invocation, "gate_evidence_invalid", str(exc))
            raise RunnerBlocked("gate evidence is invalid") from exc


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
        self.integrity_path = self.run_dir / "workflow-integrity.json"
        self.state_path = self.run_dir / "workflow-state.json"
        self.recovery_path = self.run_dir / "workflow-recovery.json"
        self.writer_lock_path = self.run_dir / ".runner-writer.lock"
        self._known_attempts: set[_Identity] = set()
        self._pending_invocation: AgentInvocation | None = None
        self._gate_capability = object()
        self._parent_gate_verifier = ParentGateVerifier(self, self._gate_capability)
        recovery = self._read_recovery()
        try:
            self._events(allow_recovery=recovery is not None)
        except RunnerError as exc:
            if recovery is not None:
                raise
            events = self._events(allow_recovery=True)
            identity = self._event_identity(events[-1]) if events else None
            self._fail_closed(None, "integrity_recovery", exc, identity=identity)
        with self._writer_lock():
            self._recover_interrupted_attempts()

    @contextmanager
    def _writer_lock(self) -> Iterator[None]:
        key = str(self.writer_lock_path)
        if os.name == "nt":
            key = key.casefold()
        with _WRITER_LOCKS_GUARD:
            lock = _WRITER_LOCKS.setdefault(key, threading.RLock())
        lock.acquire()
        depths = getattr(_WRITER_LOCK_STATE, "depths", {})
        depth = depths.get(key, 0)
        fd: int | None = None
        try:
            if depth == 0:
                run_dir = self._safe_path(self.run_dir, "planning run")
                run_dir.mkdir(parents=True, exist_ok=True)
                lock_path = self._safe_path(self.writer_lock_path, "writer lock")
                flags = os.O_RDWR | os.O_CREAT
                if hasattr(os, "O_BINARY"):
                    flags |= os.O_BINARY
                fd = os.open(lock_path, flags, 0o600)
                if os.fstat(fd).st_size == 0:
                    os.write(fd, b"\0")
                file_lock = _platform_file_lock(fd)
                file_lock.__enter__()
                depths[key] = 1
                _WRITER_LOCK_STATE.depths = depths
                try:
                    yield
                finally:
                    depths[key] = 0
                    file_lock.__exit__(None, None, None)
            else:
                depths[key] = depth + 1
                _WRITER_LOCK_STATE.depths = depths
                try:
                    yield
                finally:
                    depths[key] = depth
        finally:
            if fd is not None:
                os.close(fd)
            lock.release()

    @property
    def parent_gate_verifier(self) -> ParentGateVerifier:
        return self._parent_gate_verifier

    def begin(
        self,
        stage: PlanningStage | str,
        *,
        role: str,
        input_paths: Sequence[Path],
        output_path: str,
    ) -> AgentInvocation:
        with self._writer_lock():
            try:
                return self._begin_locked(
                    stage,
                    role=role,
                    input_paths=input_paths,
                    output_path=output_path,
                )
            except RunnerBlocked:
                raise
            except _RunnerEncodeError as exc:
                self._fail_closed(self._pending_invocation, "begin_encode_failure", exc)
                raise RunnerBlocked("runner mutation failed closed") from exc
            except RunnerError:
                raise
            except (OSError, UnicodeError, RecursionError, TypeError, ValueError, OverflowError) as exc:
                self._fail_closed(self._pending_invocation, "begin_write_failure", exc)
                raise RunnerBlocked("runner mutation failed closed") from exc
            finally:
                self._pending_invocation = None

    def _begin_locked(
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
        self._pending_invocation = invocation
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
        self._known_attempts.add((requested.value, revision, attempt))
        return invocation

    def record_result(self, invocation: AgentInvocation, result: Mapping[str, object]) -> AgentResultRecord:
        with self._writer_lock():
            try:
                return self._record_result_locked(invocation, result)
            except RunnerBlocked:
                raise
            except _RunnerEncodeError as exc:
                self._fail_closed(invocation, "result_encode_failure", exc)
                raise RunnerBlocked("runner mutation failed closed") from exc
            except RunnerError:
                raise
            except (OSError, UnicodeError, RecursionError, TypeError, ValueError, OverflowError) as exc:
                self._fail_closed(invocation, "result_write_failure", exc)
                raise RunnerBlocked("runner mutation failed closed") from exc

    def _record_result_locked(self, invocation: AgentInvocation, result: Mapping[str, object]) -> AgentResultRecord:
        self._validate_invocation(invocation)
        self._assert_current_attempt(invocation, require_no_result=True)
        self._assert_inputs_current(invocation)
        try:
            if not isinstance(result, Mapping):
                raise RunnerError("agent result schema is invalid")
            result_data = dict(result)
            if (
                any(not isinstance(key, str) for key in result_data)
                or set(result_data) - _ALLOWED_RESULT_KEYS
                or "ok" not in result_data
                or "payload" not in result_data
            ):
                raise RunnerError("agent result schema is invalid")
            ok = result_data.get("ok")
            payload = result_data.get("payload")
            if type(ok) is not bool or not isinstance(payload, Mapping):
                raise RunnerError("agent result schema is invalid")
            _reject_output_target_spoof(payload)
            session_id = result_data.get("session_id")
            if session_id is not None:
                session_id = _safe_id(session_id, "session_id")
            error = result_data.get("error")
            if error is not None:
                error = _safe_text(error, "agent error", required=False)
            payload_data = dict(payload)
            payload_sha256 = _sha(_bounded_json(payload_data, "result payload", _MAX_PAYLOAD_BYTES))
        except RunnerError as exc:
            self._durable_block(invocation, "agent_result_invalid", str(exc))
            raise RunnerBlocked(str(exc)) from exc
        self._assert_inputs_current(invocation)
        self._validate_output_binding(invocation)
        record = AgentResultRecord(
            1,
            self.run_id,
            invocation.stage,
            invocation.revision,
            invocation.attempt,
            ok,
            payload_data,
            payload_sha256,
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
        verification: GateVerification | None = None,
        gate_id: str | None = None,
        passed: bool | None = None,
        detail: str | None = None,
        evidence: Mapping[str, object] | None = None,
    ) -> GateRecord:
        with self._writer_lock():
            try:
                return self._record_gate_locked(
                    invocation,
                    verification=verification,
                    gate_id=gate_id,
                    passed=passed,
                    detail=detail,
                    evidence=evidence,
                )
            except RunnerBlocked:
                raise
            except _RunnerEncodeError as exc:
                self._fail_closed(invocation, "gate_encode_failure", exc)
                raise RunnerBlocked("runner mutation failed closed") from exc
            except RunnerError:
                raise
            except (OSError, UnicodeError, RecursionError, TypeError, ValueError, OverflowError) as exc:
                self._fail_closed(invocation, "gate_write_failure", exc)
                raise RunnerBlocked("runner mutation failed closed") from exc

    def _record_gate_locked(
        self,
        invocation: AgentInvocation,
        *,
        verification: GateVerification | None = None,
        gate_id: str | None = None,
        passed: bool | None = None,
        detail: str | None = None,
        evidence: Mapping[str, object] | None = None,
    ) -> GateRecord:
        del gate_id, passed, detail, evidence
        if verification is None:
            raise RunnerError("trusted parent gate verification is required")
        try:
            self._validate_invocation(invocation)
            self._assert_current_attempt(invocation)
            self._assert_inputs_current(invocation)
            self._validate_output_binding(invocation)
        except RunnerBlocked:
            raise
        except RunnerError as exc:
            self._durable_block(invocation, "gate_path_invalid", str(exc))
            raise RunnerBlocked("gate path is unsafe") from exc
        if not isinstance(verification, GateVerification) or verification._capability is not self._gate_capability:
            raise RunnerError("trusted parent gate verification is invalid")
        gate = _safe_id(verification.gate_id, "gate_id")
        if gate != f"gate-{invocation.stage.value}":
            raise RunnerError("gate is not in the trusted allowlist")
        if type(verification.passed) is not bool:
            raise RunnerError("gate result must be boolean")
        detail_text = _safe_text(verification.detail, "gate detail")
        try:
            result_record = self._read_current_result(invocation)
            if result_record.ok is not True:
                raise RunnerError("failed agent result cannot pass a gate")
        except RunnerBlocked:
            raise
        except RunnerError as exc:
            self._durable_block(invocation, "gate_evidence_invalid", str(exc))
            raise RunnerBlocked("agent result is unreadable") from exc
        evidence_payload = dict(verification.evidence)
        _reject_output_target_spoof(evidence_payload)
        _bounded_json(evidence_payload, "gate evidence", _MAX_EVIDENCE_BYTES)
        invocation_sha256 = _record_sha(invocation)
        result_sha256 = _record_sha(result_record)
        output_sha256 = _output_binding_hash(invocation.output_path)
        if (
            verification.invocation_sha256 != invocation_sha256
            or verification.result_sha256 != result_sha256
            or verification.output_sha256 != output_sha256
        ):
            raise RunnerError("gate verification binding does not match")
        evidence_sha256 = _gate_evidence_hash(
            invocation_sha256,
            result_sha256,
            output_sha256,
            evidence_payload,
        )
        record = GateRecord(
            1,
            self.run_id,
            invocation.stage,
            invocation.revision,
            invocation.attempt,
            gate,
            "pass" if verification.passed else "fail",
            detail_text,
            evidence_sha256,
            invocation_sha256,
            result_sha256,
            output_sha256,
            evidence_payload,
        )
        try:
            self._assert_inputs_current(invocation)
            self._validate_output_binding(invocation)
        except RunnerBlocked:
            raise
        except RunnerError as exc:
            self._durable_block(invocation, "gate_path_invalid", str(exc))
            raise RunnerBlocked("gate path is unsafe") from exc
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
                "output_sha256": output_sha256,
            }
        )
        if not verification.passed:
            self._block(invocation, "gate_failed", detail_text)
        return record

    def advance(self, invocation: AgentInvocation) -> PlanningStage | None:
        with self._writer_lock():
            try:
                return self._advance_locked(invocation)
            except RunnerBlocked:
                raise
            except _RunnerEncodeError as exc:
                self._fail_closed(invocation, "advance_encode_failure", exc)
                raise RunnerBlocked("runner mutation failed closed") from exc
            except RunnerError:
                raise
            except (OSError, UnicodeError, RecursionError, TypeError, ValueError, OverflowError) as exc:
                self._fail_closed(invocation, "advance_write_failure", exc)
                raise RunnerBlocked("runner mutation failed closed") from exc

    def _advance_locked(self, invocation: AgentInvocation) -> PlanningStage | None:
        try:
            self._validate_invocation(invocation)
        except RunnerBlocked:
            raise
        except RunnerError as exc:
            self._durable_block(invocation, "output_binding_invalid", str(exc))
            raise RunnerBlocked("invocation output binding is invalid") from exc
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
            self._validate_output_binding(invocation)
        except RunnerBlocked:
            raise
        except RunnerError as exc:
            self._durable_block(invocation, "advance_path_invalid", str(exc))
            raise RunnerBlocked("advance path is unsafe") from exc
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
        try:
            self._assert_inputs_current(invocation)
            self._validate_output_binding(invocation)
        except RunnerBlocked:
            raise
        except RunnerError as exc:
            self._durable_block(invocation, "advance_path_invalid", str(exc))
            raise RunnerBlocked("advance path is unsafe") from exc
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
        with self._writer_lock():
            recovery = self._read_recovery()
            if recovery is not None:
                return self._blocked_state(recovery)
            return self._status_locked()

    def _status_locked(self) -> WorkflowState:
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

    def _read_recovery(self) -> dict[str, object] | None:
        path = self._safe_path(self.recovery_path, "workflow recovery")
        if not path.exists():
            return None
        value = self._read_json(path, "workflow recovery")
        if not isinstance(value, Mapping) or set(value) != _RECOVERY_KEYS:
            raise RunnerError("workflow recovery record is invalid")
        if type(value.get("schema")) is not int or value.get("schema") != 1:
            raise RunnerError("workflow recovery record is invalid")
        if value.get("run_id") != self.run_id:
            raise RunnerError("workflow recovery run identity is invalid")
        stage_value = value.get("stage")
        if stage_value is not None:
            stage = _stage(stage_value).value
            revision = _positive_int(value.get("revision"), "revision")
            attempt = _positive_int(value.get("attempt"), "attempt")
        else:
            stage = None
            if value.get("revision") is not None or value.get("attempt") is not None:
                raise RunnerError("workflow recovery identity is invalid")
            revision = None
            attempt = None
        reason = _safe_id(value.get("reason"), "recovery reason")
        detail = _safe_text(value.get("detail"), "recovery detail")
        return {
            "schema": 1,
            "run_id": self.run_id,
            "stage": stage,
            "revision": revision,
            "attempt": attempt,
            "reason": reason,
            "detail": detail,
        }

    def _blocked_state(self, recovery: Mapping[str, object]) -> WorkflowState:
        try:
            events = self._events(allow_recovery=True)
            completed, attempts = self._validate_event_history(events)
        except RunnerError:
            completed, attempts = [], {}
        marker_stage = recovery.get("stage")
        current = (
            str(marker_stage)
            if marker_stage is not None
            else _STAGE_ORDER[len(completed)].value if len(completed) < len(_STAGE_ORDER) else None
        )
        latest_attempts = {
            stage: _positive_int(attempt.begin.get("attempt"), "attempt")
            for stage, attempt in attempts.items()
        }
        return WorkflowState(
            1,
            self.run_id,
            current,
            True,
            str(recovery["reason"]),
            tuple(stage.value for stage in _STAGE_ORDER[: len(completed)]),
            latest_attempts,
        )

    def _fail_closed(
        self,
        invocation: AgentInvocation | None,
        reason: str,
        error: BaseException,
        *,
        identity: _Identity | None = None,
    ) -> None:
        detail = str(error).replace("\r", " ").replace("\n", " ")
        if not detail.strip():
            detail = "runner mutation failed"
        detail = detail[: _MAX_TEXT_BYTES]
        payload: dict[str, object] = {
            "schema": 1,
            "run_id": self.run_id,
            "stage": identity[0] if identity is not None else invocation.stage.value if invocation is not None else None,
            "revision": identity[1] if identity is not None else invocation.revision if invocation is not None else None,
            "attempt": identity[2] if identity is not None else invocation.attempt if invocation is not None else None,
            "reason": _safe_id(reason, "recovery reason"),
            "detail": detail,
        }
        try:
            path = self._safe_path(self.recovery_path, "workflow recovery")
            content = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
            if len(content.encode("utf-8")) > _MAX_JSON_BYTES:
                return
            _atomic_write(path, content)
        except (OSError, TypeError, ValueError, RecursionError):
            return

    def _clear_recovery(self) -> None:
        try:
            path = self._safe_path(self.recovery_path, "workflow recovery")
            path.unlink(missing_ok=True)
        except (OSError, ValueError):
            pass

    def _safe_path(self, path: Path, label: str) -> Path:
        safe = safe_resolve(self.project_root, path)
        if safe is None:
            raise RunnerError(f"{label} path is unsafe")
        return safe

    def _validate_output_binding(self, invocation: AgentInvocation) -> Path:
        output_path = _safe_relative(invocation.output_path, "output target")
        if output_path != invocation.output_path:
            raise RunnerError("parent output binding is invalid")
        return self._safe_path(self.project_root / output_path, "output target")

    def _write_json(self, path: Path, value: object, label: str) -> None:
        self._safe_path(path, label)
        _validate_json_value(value)
        try:
            content = json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
        except (RecursionError, TypeError, ValueError) as exc:
            raise _RunnerEncodeError(f"{label} is not strict JSON") from exc
        if len(content.encode("utf-8")) > _MAX_JSON_BYTES:
            raise RunnerError(f"{label} is oversized")
        safe = self._safe_path(path, label)
        _atomic_write(safe, content)

    def _read_json(self, path: Path, label: str) -> object:
        safe = self._safe_path(path, label)
        try:
            raw = _read_limited(safe, _MAX_JSON_BYTES, label)
            return _strict_json_loads(raw)
        except RunnerError:
            raise
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
        self._validate_output_binding(invocation)
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
            try:
                path = self._safe_path(self.project_root / relative, "input")
            except RunnerError as exc:
                self._durable_block(invocation, "stale_input", "input is missing or unsafe")
                raise RunnerBlocked("stale input") from exc
            if not path.is_file():
                self._block(invocation, "stale_input", "input is missing or unsafe")
                raise RunnerBlocked("stale input")
            try:
                actual = _sha(path.read_bytes())
            except (OSError, RunnerError) as exc:
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
        output_sha256 = _output_binding_hash(invocation.output_path)
        if (
            record.stage is not invocation.stage
            or record.revision != invocation.revision
            or record.attempt != invocation.attempt
            or record.invocation_sha256 != invocation_sha256
            or record.result_sha256 != result_sha256
            or record.output_sha256 != output_sha256
            or record.evidence_sha256
            != _gate_evidence_hash(invocation_sha256, result_sha256, output_sha256, record.evidence or {})
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
            or event.get("output_sha256") != record.output_sha256
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

    def _validate_event_schema(
        self,
        event: object,
        expected_sequence: int,
        expected_previous_sha256: str | None = None,
    ) -> dict[str, object]:
        if not isinstance(event, Mapping) or any(not isinstance(key, str) for key in event):
            raise RunnerError("workflow journal event is invalid")
        action = event.get("action")
        if not isinstance(action, str) or action not in _ALLOWED_ACTIONS or set(event) != _EVENT_KEYS[action]:
            raise RunnerError("workflow journal event schema is invalid")
        if type(event.get("schema")) is not int or event.get("schema") != 1:
            raise RunnerError("workflow journal event schema is invalid")
        if event.get("sequence") != expected_sequence or type(event.get("sequence")) is not int:
            raise RunnerError("workflow journal sequence is invalid")
        previous_sha256 = event.get("previous_sha256")
        event_sha256 = event.get("event_sha256")
        expected_previous = _GENESIS_SHA256 if expected_sequence == 1 else expected_previous_sha256
        if (
            not isinstance(previous_sha256, str)
            or _SHA256.fullmatch(previous_sha256) is None
            or previous_sha256 != expected_previous
            or not isinstance(event_sha256, str)
            or _SHA256.fullmatch(event_sha256) is None
            or event_sha256 != _event_sha(event)
        ):
            raise RunnerError("workflow journal integrity is invalid")
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
            result_path = _safe_relative(event.get("result_path"), "result path", allow_runner_control=True)
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
            output_sha256 = event.get("output_sha256")
            if not isinstance(output_sha256, str) or _SHA256.fullmatch(output_sha256) is None:
                raise RunnerError("workflow gate output binding is invalid")
        elif action == "advance":
            next_stage = event.get("next_stage")
            stage_index = _STAGE_ORDER.index(stage) + 1
            expected_next = _STAGE_ORDER[stage_index].value if stage_index < len(_STAGE_ORDER) else None
            if next_stage != expected_next:
                raise RunnerError("workflow advance target is invalid")
        else:
            _safe_id(event.get("reason"), "block reason")
            _safe_text(event.get("detail"), "block detail")
        validated: dict[str, object] = {}
        for key, item in event.items():
            if not isinstance(key, str):
                raise RunnerError("workflow journal event is invalid")
            validated[key] = item
        return validated

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

    def _validate_history_records(
        self,
        events: Sequence[dict[str, object]],
        attempts: dict[str, _AttemptState],
        *,
        collect_errors: bool = False,
    ) -> set[_Identity]:
        del attempts  # The event identities, not only the latest stage, are authoritative.
        invocations: dict[_Identity, AgentInvocation] = {}
        results: dict[_Identity, AgentResultRecord] = {}
        gates: dict[_Identity, GateRecord] = {}
        invalid: set[_Identity] = set()
        blocked: set[_Identity] = {
            self._event_identity(event) for event in events if event["action"] == "block"
        }

        for event in events:
            identity = self._event_identity(event)
            action = event["action"]
            if action == "begin":
                try:
                    invocation = _invocation_from_record(
                        self._read_json(self._record_file_from_event(event, "invocation.json"), "invocation record"),
                        self.run_id,
                    )
                    expected = invocation.to_dict()
                    begin_fields = {key: event[key] for key in expected}
                    if expected != begin_fields:
                        raise RunnerError("invocation journal record does not match")
                    invocations[identity] = invocation
                except RunnerError:
                    if identity not in blocked:
                        if not collect_errors:
                            raise
                        invalid.add(identity)
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
                if not collect_errors:
                    raise
                invalid.add(identity)

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
                    or record.output_sha256 != _output_binding_hash(invocation.output_path)
                    or event["gate_id"] != record.gate_id
                    or event["status"] != record.status
                    or event["detail"] != record.detail
                    or event["evidence_sha256"] != record.evidence_sha256
                    or event["invocation_sha256"] != record.invocation_sha256
                    or event["result_sha256"] != record.result_sha256
                    or event["output_sha256"] != record.output_sha256
                ):
                    raise RunnerError("gate journal record does not match")
                gates[identity] = record
            except RunnerError:
                if identity in blocked:
                    continue
                if not collect_errors:
                    raise
                invalid.add(identity)

        for event in events:
            if event["action"] != "advance":
                continue
            identity = self._event_identity(event)
            result_record = results.get(identity)
            gate_record = gates.get(identity)
            if result_record is None or gate_record is None:
                if not collect_errors:
                    raise RunnerError("advance evidence is missing")
                invalid.add(identity)
                continue
            if not result_record.ok or not gate_record.passed:
                if not collect_errors:
                    raise RunnerError("advance evidence did not pass")
                invalid.add(identity)
        return invalid

    def _events(self, *, allow_recovery: bool = False) -> list[dict[str, object]]:
        path = self._safe_path(self.events_path, "workflow journal")
        if not path.exists():
            integrity_path = self._safe_path(self.integrity_path, "workflow integrity")
            if integrity_path.exists() or self.state_path.exists():
                raise RunnerError("workflow journal history is missing")
            return []
        try:
            raw = _read_limited(
                self._safe_path(self.events_path, "workflow journal"),
                _MAX_WORKFLOW_JOURNAL_BYTES,
                "workflow journal",
            )
        except RunnerError:
            raise
        except (OSError, UnicodeError) as exc:
            raise RunnerError("workflow journal is unreadable") from exc
        lines = raw.splitlines()
        events: list[dict[str, object]] = []
        previous_sha256 = _GENESIS_SHA256
        for expected, line in enumerate(lines, 1):
            try:
                event = _strict_json_loads(line)
            except (UnicodeError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise RunnerError("workflow journal contains malformed JSON") from exc
            validated = self._validate_event_schema(event, expected, previous_sha256)
            events.append(validated)
            previous_sha256 = str(validated["event_sha256"])
        try:
            integrity = self._read_integrity()
        except RunnerError:
            if not allow_recovery or not events and self._read_recovery() is None:
                raise
            self._validate_event_history(events)
            return events
        if integrity is None:
            if allow_recovery and (events or self._read_recovery() is not None):
                self._validate_event_history(events)
                return events
            raise RunnerError("workflow integrity record is missing")
        if (
            integrity["event_count"] != len(events)
            or integrity["head_sha256"] != previous_sha256
        ):
            if allow_recovery and (events or self._read_recovery() is not None):
                self._validate_event_history(events)
                return events
            raise RunnerError("workflow journal integrity record does not match")
        self._validate_event_history(events)
        return events

    def _read_integrity(self) -> dict[str, object] | None:
        path = self._safe_path(self.integrity_path, "workflow integrity")
        if not path.exists():
            return None
        value = self._read_json(path, "workflow integrity")
        if not isinstance(value, Mapping) or set(value) != {"schema", "run_id", "event_count", "head_sha256"}:
            raise RunnerError("workflow integrity record is invalid")
        event_count = value.get("event_count")
        head_sha256 = value.get("head_sha256")
        if (
            type(value.get("schema")) is not int
            or value.get("schema") != 1
            or value.get("run_id") != self.run_id
            or type(event_count) is not int
            or not isinstance(head_sha256, str)
            or _SHA256.fullmatch(head_sha256) is None
        ):
            raise RunnerError("workflow integrity record is invalid")
        if event_count < 1:
            raise RunnerError("workflow integrity record is invalid")
        result: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise RunnerError("workflow integrity record is invalid")
            result[key] = item
        return result

    def _append(self, payload: Mapping[str, object]) -> None:
        with self._writer_lock():
            try:
                self._append_locked(payload)
            except RunnerBlocked:
                raise
            except _RunnerEncodeError as exc:
                self._fail_closed(self._pending_invocation, "journal_encode_failure", exc)
                raise RunnerBlocked("runner mutation failed closed") from exc
            except RunnerError:
                raise
            except (OSError, UnicodeError, RecursionError, TypeError, ValueError, OverflowError) as exc:
                self._fail_closed(self._pending_invocation, "journal_write_failure", exc)
                raise RunnerBlocked("runner mutation failed closed") from exc

    def _append_locked(self, payload: Mapping[str, object]) -> None:
        if set(payload) & {"schema", "sequence"}:
            raise RunnerError("workflow event contains reserved fields")
        existing = self._events(allow_recovery=self._read_recovery() is not None)
        sequence = len(existing) + 1
        previous_sha256 = str(existing[-1]["event_sha256"]) if existing else _GENESIS_SHA256
        event = {
            "schema": 1,
            **dict(payload),
            "sequence": sequence,
            "previous_sha256": previous_sha256,
            "event_sha256": "",
        }
        event["event_sha256"] = _event_sha(event)
        event = self._validate_event_schema(event, sequence, previous_sha256)
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
        except (OSError, TypeError, ValueError):
            raise
        self._write_json(
            self.integrity_path,
            {
                "schema": 1,
                "run_id": self.run_id,
                "event_count": sequence,
                "head_sha256": event["event_sha256"],
            },
            "workflow integrity",
        )
        self._write_json(self.state_path, self.status().to_dict(), "workflow state")

    def _record_identity_from_path(self, path: Path) -> _Identity | None:
        try:
            parts = path.relative_to(self.run_dir / "stages").parts
            if len(parts) != 4:
                return None
            stage_name = parts[0].casefold()
            stage = _stage(stage_name).value
            revision_match = re.fullmatch(r"r([1-9][0-9]*)", parts[1], re.IGNORECASE)
            attempt_match = re.fullmatch(r"a([1-9][0-9]*)", parts[2], re.IGNORECASE)
            if revision_match is None or attempt_match is None:
                return None
            _positive_int(int(revision_match.group(1)), "revision")
            _positive_int(int(attempt_match.group(1)), "attempt")
            return stage, int(revision_match.group(1)), int(attempt_match.group(1))
        except (RunnerError, OSError, ValueError):
            return None

    def _orphan_record_identities(self, events: Sequence[dict[str, object]]) -> set[_Identity]:
        stages_dir = self._safe_path(self.run_dir / "stages", "stage records")
        if not stages_dir.exists():
            return set()
        referenced: set[tuple[_Identity, str]] = set()
        for event in events:
            action = event["action"]
            if not isinstance(action, str) or action not in {"begin", "result", "gate"}:
                continue
            filename = "invocation.json" if action == "begin" else action + ".json"
            referenced.add((self._event_identity(event), filename))
        orphaned: set[_Identity] = set()
        for path in stages_dir.rglob("*"):
            filename = path.name.casefold()
            if filename not in {"invocation.json", "result.json", "gate.json"}:
                continue
            safe = self._safe_path(path, "stage record")
            if not safe.is_file():
                continue
            identity = self._record_identity_from_path(safe)
            if identity is not None and (identity, filename) not in referenced:
                orphaned.add(identity)
        return orphaned

    def _append_recovery_block(self, identity: _Identity, reason: str, detail: str) -> None:
        events = self._events(allow_recovery=self._read_recovery() is not None)
        if any(event["action"] == "block" and self._event_identity(event) == identity for event in events):
            return
        self._append(
            {
                "action": "block",
                "run_id": self.run_id,
                "stage": identity[0],
                "revision": identity[1],
                "attempt": identity[2],
                "reason": _safe_id(reason, "block reason"),
                "detail": _safe_text(detail, "block detail"),
            }
        )

    def _recover_interrupted_attempts(self) -> None:
        recovery = self._read_recovery()
        events = self._events(allow_recovery=recovery is not None)
        _, attempts = self._validate_event_history(events)
        invalid = self._validate_history_records(events, attempts, collect_errors=True)
        orphaned = self._orphan_record_identities(events)
        begin_identities = {
            self._event_identity(event) for event in events if event["action"] == "begin"
        }
        advanced_identities = {
            self._event_identity(event) for event in events if event["action"] == "advance"
        }
        unresolved = recovery is not None and recovery.get("stage") is None
        marker_identity = None
        if recovery is not None and recovery.get("stage") is not None:
            marker_identity = (
                str(recovery["stage"]),
                _positive_int(recovery["revision"], "revision"),
                _positive_int(recovery["attempt"], "attempt"),
            )
            if marker_identity not in begin_identities:
                unresolved = True
            if marker_identity in advanced_identities:
                unresolved = True
        for identity in sorted(invalid | orphaned):
            if identity in advanced_identities:
                unresolved = True
                self._fail_closed(
                    None,
                    "recovery_integrity",
                    RuntimeError("advanced runner evidence could not be reconciled"),
                    identity=identity,
                )
                continue
            if identity in begin_identities:
                self._append_recovery_block(
                    identity,
                    "recovery_integrity",
                    "persisted runner evidence could not be reconciled",
                )
            else:
                unresolved = True
                self._fail_closed(
                    None,
                    "orphan_record",
                    RuntimeError("orphan runner record has no journal begin"),
                )
        events = self._events(allow_recovery=self._read_recovery() is not None)
        _, attempts = self._validate_event_history(events)
        for stage_name, attempt in attempts.items():
            if attempt.blocked or attempt.advanced:
                continue
            identity = (
                stage_name,
                _positive_int(attempt.begin.get("revision"), "revision"),
                _positive_int(attempt.begin.get("attempt"), "attempt"),
            )
            if identity in self._known_attempts:
                continue
            self._append(
                {
                    "action": "block",
                    "run_id": self.run_id,
                    "stage": stage_name,
                    "revision": identity[1],
                    "attempt": identity[2],
                    "reason": "interrupted_attempt",
                    "detail": "begin-only attempt recovered fail-closed",
                }
            )
        if recovery is not None and not unresolved:
            self._clear_recovery()


__all__ = [
    "AgentInvocation",
    "AgentResultRecord",
    "GateVerification",
    "GateRecord",
    "ParentGateVerifier",
    "PlanningRunner",
    "PlanningStage",
    "RunnerBlocked",
    "RunnerError",
    "WorkflowState",
]
