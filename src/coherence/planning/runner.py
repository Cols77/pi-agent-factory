"""Parent-owned deterministic planning workflow state machine.

The SQLite run store is authoritative.  The JSON files kept beside it are
compatibility projections for existing readers and are never consulted to
approve a transition.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
import tempfile
import threading
import weakref
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from types import MappingProxyType

from coherence.planning.paths import safe_resolve, safe_root


class RunnerError(ValueError):
    """Raised when a planning-runner contract is invalid."""


class RunnerBlocked(RunnerError):
    """Raised when a run must remain blocked until a new attempt or decision."""


class _RunnerEncodeError(RunnerError):
    """Raised when a controlled projection cannot be encoded."""


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


class _GateAttestationToken:
    """Opaque identity retained by a parent-issued gate attestation."""

    __slots__ = ("__weakref__",)


@dataclass(frozen=True)
class GateVerification:
    """A serialized parent-adapter decision bound to one exact lineage.

    The runner validates this data; it does not decide the meaning of a gate.
    ``_capability`` is an opaque in-process parent authority token and is never
    serialized or accepted from an untrusted mapping.
    """

    gate_id: str
    passed: bool
    detail: str
    evidence: Mapping[str, object]
    invocation_sha256: str
    result_sha256: str
    output_sha256: str
    run_id: str = ""
    stage: PlanningStage | None = None
    revision: int = 0
    attempt: int = 0
    input_hashes: Mapping[str, str] = field(default_factory=dict)
    policy_version: str = "planning-gates-v1"
    resolver_id: str = "resolver-v1"
    evidence_sha256: str = ""
    _capability: object | None = field(default=None, repr=False, compare=False)
    _attestation_token: _GateAttestationToken | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.stage is not None and not isinstance(self.stage, PlanningStage):
            object.__setattr__(self, "stage", _stage(self.stage))
        object.__setattr__(self, "evidence", _freeze(self.evidence))
        object.__setattr__(self, "input_hashes", _freeze(self.input_hashes))
        if not self.evidence_sha256:
            object.__setattr__(
                self,
                "evidence_sha256",
                _gate_evidence_hash(
                    self.invocation_sha256,
                    self.result_sha256,
                    self.output_sha256,
                    self.evidence,
                    input_hashes=self.input_hashes,
                    policy_version=self.policy_version,
                    resolver_id=self.resolver_id,
                ),
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": 1,
            "run_id": self.run_id,
            "stage": self.stage.value if self.stage is not None else None,
            "revision": self.revision,
            "attempt": self.attempt,
            "gate_id": self.gate_id,
            "passed": self.passed,
            "detail": self.detail,
            "input_hashes": {
                key: value for key, value in sorted(self.input_hashes.items())
            },
            "invocation_sha256": self.invocation_sha256,
            "result_sha256": self.result_sha256,
            "output_sha256": self.output_sha256,
            "policy_version": self.policy_version,
            "resolver_id": self.resolver_id,
            "evidence_sha256": self.evidence_sha256,
            "evidence": _thaw(self.evidence),
        }

    @classmethod
    def from_dict(cls, value: object) -> GateVerification:
        if not isinstance(value, Mapping) or set(value) != _VERIFICATION_KEYS:
            raise RunnerError("gate verification schema is invalid")
        if type(value.get("schema")) is not int or value.get("schema") != 1:
            raise RunnerError("gate verification schema is invalid")
        stage_value = value.get("stage")
        stage = _stage(stage_value) if stage_value is not None else None
        evidence = value.get("evidence")
        if not isinstance(evidence, Mapping):
            raise RunnerError("gate verification evidence is invalid")
        passed = value.get("passed")
        if type(passed) is not bool:
            raise RunnerError("gate verification result is invalid")
        return cls(
            _safe_id(value.get("gate_id"), "gate_id"),
            passed,
            _safe_text(value.get("detail"), "gate detail"),
            dict(evidence),
            _hash_string(value.get("invocation_sha256"), "invocation hash"),
            _hash_string(value.get("result_sha256"), "result hash"),
            _hash_string(value.get("output_sha256"), "output hash"),
            _safe_id(value.get("run_id"), "run_id"),
            stage,
            _positive_int(value.get("revision"), "revision"),
            _positive_int(value.get("attempt"), "attempt"),
            _validated_input_hashes(value.get("input_hashes")),
            _safe_text(value.get("policy_version"), "policy version"),
            _safe_text(value.get("resolver_id"), "resolver id"),
            _hash_string(value.get("evidence_sha256"), "evidence hash"),
        )


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
    invocation_sha256: str
    result_sha256: str
    output_sha256: str
    evidence: Mapping[str, object]
    input_hashes: Mapping[str, str] = field(default_factory=dict)
    policy_version: str = "planning-gates-v1"
    resolver_id: str = "resolver-v1"

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", _freeze(self.evidence))
        object.__setattr__(self, "input_hashes", _freeze(self.input_hashes))

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
            "input_hashes": {
                key: value for key, value in sorted(self.input_hashes.items())
            },
            "policy_version": self.policy_version,
            "resolver_id": self.resolver_id,
            "evidence": _thaw(self.evidence),
        }


def _gate_attestation_fingerprint(verification: GateVerification) -> str:
    """Fingerprint all serialized attestation fields, including the decision."""

    return _sha(_canonical(verification.to_dict()))


@dataclass(frozen=True)
class WorkflowState:
    schema: int
    run_id: str
    current_stage: str | None
    blocked: bool
    reason: str | None
    completed_stages: tuple[str, ...]
    attempts: Mapping[str, int]

    def __post_init__(self) -> None:
        object.__setattr__(self, "attempts", MappingProxyType(dict(self.attempts)))

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


_Identity = tuple[str, int, int]
_STAGE_ORDER = tuple(PlanningStage)
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GENESIS_SHA256 = "0" * 64
_MAX_JSON_BYTES = 1_048_576
_MAX_WORKFLOW_JOURNAL_BYTES = 8 * _MAX_JSON_BYTES
_MAX_JSON_DEPTH = 64
_MAX_JSON_NODES = 100_000
_SQLITE_INTEGER_MAX = 2**63 - 1
_MAX_STRING_BYTES = 64 * 1024
_MAX_TEXT_BYTES = 16 * 1024
_MAX_PAYLOAD_BYTES = 64 * 1024
_NON_RETRYABLE_METADATA_BLOCK_REASONS = frozenset(
    {"recovery_integrity", "orphan_record", "durable_unavailable"}
)
_MAX_EVIDENCE_BYTES = 64 * 1024
_MAX_INPUT_FILES = 256
_MAX_INPUT_BYTES = 64 * 1024 * 1024
_MAX_OUTPUT_BYTES = 64 * 1024 * 1024

_OUTPUT_TARGET_KEYS = frozenset({"output_path", "output_target", "path", "target"})
_RUNNER_CONTROL_NAMES = frozenset(
    {
        ".runner-writer.lock",
        "workflow-events.jsonl",
        "workflow-integrity.json",
        "workflow-state.json",
        "workflow-recovery.json",
        "workflow.sqlite3",
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
        "CONIN$",
        "CONOUT$",
    }
)
_INVOCATION_KEYS = {
    "schema", "run_id", "stage", "revision", "attempt", "role", "input_hashes", "output_path"
}
_RESULT_KEYS = {
    "schema", "run_id", "stage", "revision", "attempt", "ok", "payload", "payload_sha256", "session_id", "error"
}
_GATE_KEYS = {
    "schema", "run_id", "stage", "revision", "attempt", "gate_id", "status", "detail",
    "evidence_sha256", "invocation_sha256", "result_sha256", "output_sha256", "input_hashes",
    "policy_version", "resolver_id", "evidence"
}
_VERIFICATION_KEYS = {
    "schema", "run_id", "stage", "revision", "attempt", "gate_id", "passed", "detail",
    "input_hashes", "invocation_sha256", "result_sha256", "output_sha256", "policy_version",
    "resolver_id", "evidence_sha256", "evidence"
}
_EVENT_BASE_KEYS = {"schema", "action", "run_id", "stage", "revision", "attempt", "sequence", "previous_sha256", "event_sha256"}
_EVENT_KEYS = {
    "begin": _EVENT_BASE_KEYS | {"role", "input_hashes", "output_path"},
    "result": _EVENT_BASE_KEYS | {"ok", "result_path", "payload_sha256", "result_sha256"},
    "gate": _EVENT_BASE_KEYS | {
        "gate_id", "status", "detail", "evidence_sha256", "invocation_sha256", "result_sha256",
        "output_sha256", "input_hashes", "policy_version", "resolver_id"
    },
    "advance": _EVENT_BASE_KEYS | {"next_stage"},
    "block": _EVENT_BASE_KEYS | {"reason", "detail"},
}
_ALLOWED_ACTIONS = set(_EVENT_KEYS)

_WRITER_LOCKS: dict[str, threading.RLock] = {}
_WRITER_LOCKS_GUARD = threading.Lock()


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
    visited: set[int] = set()
    while pending:
        current = pending.pop()
        if isinstance(current, float) and not math.isfinite(current):
            raise ValueError("non-finite JSON number is not allowed")
        if isinstance(current, Mapping):
            marker = id(current)
            if marker in visited:
                raise ValueError("cyclic JSON value is not allowed")
            visited.add(marker)
            pending.extend(current.values())
        elif isinstance(current, (list, tuple)):
            marker = id(current)
            if marker in visited:
                raise ValueError("cyclic JSON value is not allowed")
            visited.add(marker)
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
        value = json.loads(text, object_pairs_hook=_reject_duplicate_keys, parse_constant=_reject_constant)
    except RecursionError as exc:
        raise ValueError("JSON nesting is too deep") from exc
    _reject_nonfinite(value)
    _validate_json_value(value)
    return value


def _validate_json_value(value: object) -> None:
    pending: list[tuple[object, int]] = [(value, 0)]
    visited: set[int] = set()
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
            marker = id(current)
            if marker in visited:
                raise RunnerError("workflow JSON value is cyclic")
            visited.add(marker)
            for key, item in current.items():
                if not isinstance(key, str):
                    raise RunnerError("workflow object keys must be strings")
                pending.append((item, depth + 1))
            continue
        if isinstance(current, (list, tuple)):
            marker = id(current)
            if marker in visited:
                raise RunnerError("workflow JSON value is cyclic")
            visited.add(marker)
            pending.extend((item, depth + 1) for item in current)
            continue
        raise RunnerError("workflow value is not strict JSON")


def _freeze_unchecked(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze_unchecked(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_unchecked(item) for item in value)
    return value


def _freeze(value: object) -> object:
    _validate_json_value(value)
    return _freeze_unchecked(value)


def _thaw(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _canonical(value: object) -> bytes:
    _validate_json_value(value)
    try:
        encoded = json.dumps(_thaw(value), sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (RecursionError, TypeError, ValueError) as exc:
        raise RunnerError("workflow value is not strict JSON") from exc
    if len(encoded) > _MAX_JSON_BYTES:
        raise RunnerError("workflow JSON value is oversized")
    return encoded


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _hash_string(value: object, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RunnerError(f"invalid {field}")
    return value


def _record_sha(record: AgentInvocation | AgentResultRecord | GateRecord) -> str:
    return _sha(_canonical(record.to_dict()))


def _event_sha(event: Mapping[str, object]) -> str:
    unsigned = {key: value for key, value in event.items() if key != "event_sha256"}
    return _sha(_canonical(unsigned))


def _gate_evidence_hash(
    invocation_sha256: str,
    result_sha256: str,
    output_sha256: str,
    evidence: Mapping[str, object],
    *,
    input_hashes: Mapping[str, str] | None = None,
    policy_version: str = "",
    resolver_id: str = "",
) -> str:
    return _sha(_canonical({
        "invocation_sha256": invocation_sha256,
        "result_sha256": result_sha256,
        "output_sha256": output_sha256,
        "input_hashes": dict(sorted((input_hashes or {}).items())),
        "policy_version": policy_version,
        "resolver_id": resolver_id,
        "evidence": evidence,
    }))


def _safe_id(value: object, field: str) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None or len(value) > 128 or value.endswith(".") or _is_windows_reserved_component(value):
        raise RunnerError(f"invalid {field}")
    return value


def _safe_text(value: object, field: str, *, required: bool = True) -> str:
    if not isinstance(value, str) or (required and not value.strip()) or any(ord(char) < 32 for char in value):
        raise RunnerError(f"invalid {field}")
    try:
        encoded = value.encode("utf-8")
    except UnicodeError as exc:
        raise RunnerError(f"invalid {field}") from exc
    if len(encoded) > _MAX_TEXT_BYTES:
        raise RunnerError(f"invalid {field}")
    return value


def _is_windows_reserved_component(part: str) -> bool:
    stem = part.rstrip(" .").split(".", 1)[0].upper()
    return stem in _WINDOWS_RESERVED_NAMES


def _is_runner_control_target(parts: Sequence[str]) -> bool:
    lowered = [part.casefold() for part in parts]
    return lowered[-1] in _RUNNER_CONTROL_NAMES or len(lowered) >= 2 and lowered[0:2] == [".factory", "planning"]


def _safe_relative(value: object, field: str, *, allow_runner_control: bool = False) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or any(ord(char) < 32 for char in value):
        raise RunnerError(f"invalid {field}")
    normalized = value.replace("\\", "/")
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized) or ":" in normalized:
        raise RunnerError(f"invalid {field}")
    parts = normalized.split("/")
    if any(part in {"", ".", ".."} for part in parts) or any(part.endswith((".", " ")) for part in parts) or any(any(char in '<>"|?*' for char in part) for part in parts) or any(_is_windows_reserved_component(part) for part in parts) or (not allow_runner_control and _is_runner_control_target(parts)):
        raise RunnerError(f"invalid {field}")
    return normalized


def _positive_int(value: object, field: str) -> int:
    if type(value) is not int or value < 1 or value > _SQLITE_INTEGER_MAX:
        raise RunnerError(f"invalid {field}")
    return value


def _nonnegative_int(value: object, field: str) -> int:
    if type(value) is not int or value < 0 or value > _SQLITE_INTEGER_MAX:
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
    result: dict[str, str] = {}
    for raw_path, raw_hash in value.items():
        relative = _safe_relative(raw_path, "input path")
        if relative != raw_path or not isinstance(raw_hash, str) or _SHA256.fullmatch(raw_hash) is None or relative in result:
            raise RunnerError("invalid input hashes")
        result[relative] = raw_hash
    if list(result) != sorted(result):
        raise RunnerError("input hashes are not canonical")
    return result


def _reject_output_target_spoof(value: object) -> None:
    pending = [value]
    visited: set[int] = set()
    nodes = 0
    while pending:
        current = pending.pop()
        nodes += 1
        if nodes > _MAX_JSON_NODES:
            raise RunnerError("worker output is oversized")
        if isinstance(current, Mapping):
            marker = id(current)
            if marker in visited:
                raise RunnerError("worker output is cyclic")
            visited.add(marker)
            if any(key in _OUTPUT_TARGET_KEYS for key in current):
                raise RunnerError("worker-selected output target is not allowed")
            pending.extend(current.values())
        elif isinstance(current, (list, tuple)):
            marker = id(current)
            if marker in visited:
                raise RunnerError("worker output is cyclic")
            visited.add(marker)
            pending.extend(current)


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
    if not isinstance(value, Mapping) or set(value) != _INVOCATION_KEYS:
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
    if not isinstance(value, Mapping) or set(value) != _RESULT_KEYS:
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
    payload_sha256 = value.get("payload_sha256")
    if not isinstance(payload_sha256, str) or _SHA256.fullmatch(payload_sha256) is None or payload_sha256 != _sha(_bounded_json(payload, "result payload", _MAX_PAYLOAD_BYTES)):
        raise RunnerError("result payload hash does not match")
    session_id = value.get("session_id")
    if session_id is not None:
        session_id = _safe_id(session_id, "session_id")
    error = value.get("error")
    if error is not None:
        error = _safe_text(error, "agent error", required=False)
    return AgentResultRecord(1, run_id, stage, revision, attempt, ok, dict(payload), payload_sha256, session_id, error)


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
    invocation_sha256 = _hash_string(value.get("invocation_sha256"), "invocation hash")
    result_sha256 = _hash_string(value.get("result_sha256"), "result hash")
    output_sha256 = _hash_string(value.get("output_sha256"), "output hash")
    evidence_sha256 = _hash_string(value.get("evidence_sha256"), "evidence hash")
    input_hashes = _validated_input_hashes(value.get("input_hashes"))
    policy_version = _safe_text(value.get("policy_version"), "policy version")
    resolver_id = _safe_text(value.get("resolver_id"), "resolver id")
    evidence = value.get("evidence")
    if not isinstance(evidence, Mapping):
        raise RunnerError("gate evidence is invalid")
    _reject_output_target_spoof(evidence)
    _bounded_json(evidence, "gate evidence", _MAX_EVIDENCE_BYTES)
    if gate_id != f"gate-{stage.value}":
        raise RunnerError("gate is not in the trusted allowlist")
    if evidence_sha256 != _gate_evidence_hash(invocation_sha256, result_sha256, output_sha256, evidence, input_hashes=input_hashes, policy_version=policy_version, resolver_id=resolver_id):
        raise RunnerError("gate evidence hash does not match")
    return GateRecord(1, run_id, stage, revision, attempt, gate_id, status, detail, evidence_sha256, invocation_sha256, result_sha256, output_sha256, dict(evidence), input_hashes, policy_version, resolver_id)


class _ParentGateVerifier:
    """Small parent-adapter test seam for constructing a bound decision."""

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
        policy_version: str = "planning-gates-v1",
        resolver_id: str = "resolver-v1",
    ) -> GateVerification:
        runner = self._runner
        try:
            runner._validate_invocation(invocation)
            runner._assert_current_attempt(invocation)
            runner._assert_inputs_current(invocation)
            runner._validate_output_binding(invocation)
            result_record = runner._read_current_result(invocation)
            if result_record.ok is not True:
                raise RunnerError("failed agent result cannot pass a gate")
            if type(passed) is not bool:
                raise RunnerError("gate result must be boolean")
            detail_text = _safe_text(detail, "gate detail")
            evidence_payload = {"detail": detail_text} if evidence is None else dict(evidence)
            _reject_output_target_spoof(evidence_payload)
            _bounded_json(evidence_payload, "gate evidence", _MAX_EVIDENCE_BYTES)
            token = _GateAttestationToken()
            verification = GateVerification(
                gate_id=_safe_id(gate_id, "gate_id"),
                passed=passed,
                detail=detail_text,
                evidence=evidence_payload,
                invocation_sha256=_record_sha(invocation),
                result_sha256=_record_sha(result_record),
                output_sha256=runner._output_artifact_hash(invocation),
                run_id=runner.run_id,
                stage=invocation.stage,
                revision=invocation.revision,
                attempt=invocation.attempt,
                input_hashes=invocation.input_hashes,
                policy_version=_safe_text(policy_version, "policy version"),
                resolver_id=_safe_text(resolver_id, "resolver id"),
                _capability=self._capability,
                _attestation_token=token,
            )
            runner._register_gate_attestation(verification)
            return verification
        except RunnerBlocked:
            raise
        except RunnerError as exc:
            runner._mutation_failed(runner._identity_if_valid(invocation), "gate_evidence_invalid", exc)
            raise RunnerBlocked("gate evidence is invalid") from exc
        except (OSError, UnicodeError, RecursionError, TypeError, ValueError, OverflowError, sqlite3.Error) as exc:
            runner._mutation_failed(runner._identity_if_valid(invocation), "gate_evidence_invalid", exc)
            raise RunnerBlocked("gate evidence is invalid") from exc


class PlanningRunner:
    """Drive one planning run over one authoritative SQLite store."""

    def __init__(self, project_root: Path, run_id: str, *, recover: bool = False) -> None:
        safe = safe_root(project_root)
        if safe is None:
            raise RunnerError("project root is unsafe")
        self.project_root = safe
        self.run_id = _safe_id(run_id, "run_id")
        run_dir = safe_resolve(safe, safe / ".factory" / "planning" / self.run_id)
        if run_dir is None:
            raise RunnerError("planning run path is unsafe")
        self.run_dir = run_dir
        self.database_path = self.run_dir / "workflow.sqlite3"
        self.store_path = self.database_path
        self.events_path = self.run_dir / "workflow-events.jsonl"
        self.integrity_path = self.run_dir / "workflow-integrity.json"
        self.state_path = self.run_dir / "workflow-state.json"
        self.recovery_path = self.run_dir / "workflow-recovery.json"
        self._known_attempts: set[_Identity] = set()
        self._gate_capability = object()
        self._gate_attestations: weakref.WeakKeyDictionary[_GateAttestationToken, str] = weakref.WeakKeyDictionary()
        self._parent_gate_verifier = _ParentGateVerifier(self, self._gate_capability)
        self._initialize_store()
        if recover:
            with self._writer_lock():
                self._recover_interrupted_attempts()

    @contextmanager
    def _writer_lock(self) -> Iterator[None]:
        key = str(self.database_path).casefold() if os.name == "nt" else str(self.database_path)
        with _WRITER_LOCKS_GUARD:
            lock = _WRITER_LOCKS.setdefault(key, threading.RLock())
        lock.acquire()
        try:
            yield
        finally:
            lock.release()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        run_dir = self._safe_path(self.run_dir, "planning run")
        run_dir.mkdir(parents=True, exist_ok=True)
        database = self._safe_path(self.database_path, "workflow store")
        connection = sqlite3.connect(str(database), timeout=10, isolation_level=None)
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=10000")
        connection.execute("PRAGMA synchronous=FULL")
        connection.row_factory = sqlite3.Row
        return connection

    def _validate_existing_schema(
        self, connection: sqlite3.Connection, tables: set[str]
    ) -> None:
        required_tables = {
            "schema_meta",
            "run_metadata",
            "stage_attempts",
            "invocation_records",
            "result_records",
            "gate_records",
            "transitions",
            "blocks",
            "workflow_events",
        }
        missing_tables = required_tables - tables
        if missing_tables:
            raise RunnerError("workflow store schema is incomplete")
        extra_tables = tables - required_tables - {"sqlite_sequence"}
        if extra_tables:
            raise RunnerError("workflow store schema contains unexpected objects")
        expected_tables = {
            "schema_meta": "create table schema_meta ( key text primary key, value text not null )",
            "run_metadata": "create table run_metadata ( run_id text primary key, schema_version integer not null, sequence integer not null, head_sha256 text not null, blocked integer not null default 0, block_reason text )",
            "stage_attempts": "create table stage_attempts ( run_id text not null, stage text not null, revision integer not null, attempt integer not null, role text not null, input_hashes_json text not null, output_path text not null, result_sha256 text, gate_sha256 text, blocked integer not null default 0, block_reason text, advanced integer not null default 0, primary key (run_id, stage, revision, attempt) )",
            "invocation_records": "create table invocation_records ( run_id text not null, stage text not null, revision integer not null, attempt integer not null, record_json text not null, record_sha256 text not null, primary key (run_id, stage, revision, attempt) )",
            "result_records": "create table result_records ( run_id text not null, stage text not null, revision integer not null, attempt integer not null, record_json text not null, record_sha256 text not null, primary key (run_id, stage, revision, attempt) )",
            "gate_records": "create table gate_records ( run_id text not null, stage text not null, revision integer not null, attempt integer not null, record_json text not null, record_sha256 text not null, primary key (run_id, stage, revision, attempt) )",
            "transitions": "create table transitions ( run_id text not null, sequence integer not null, action text not null, stage text not null, revision integer not null, attempt integer not null, next_stage text, event_sha256 text not null, primary key (run_id, sequence) )",
            "blocks": "create table blocks ( run_id text not null, sequence integer not null, stage text not null, revision integer not null, attempt integer not null, reason text not null, detail text not null, primary key (run_id, sequence) )",
            "workflow_events": "create table workflow_events ( run_id text not null, sequence integer not null, action text not null, stage text not null, revision integer not null, attempt integer not null, event_json text not null, previous_sha256 text not null, event_sha256 text not null, primary key (run_id, sequence), unique (run_id, event_sha256) )",
        }
        for table, expected in expected_tables.items():
            row = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            actual = " ".join(str(row[0]).split()).casefold().rstrip(";") if row else ""
            if actual != expected:
                raise RunnerError("workflow store schema definition is invalid")
        schema_rows = connection.execute(
            "SELECT key, value FROM schema_meta ORDER BY key"
        ).fetchall()
        if len(schema_rows) != 1 or tuple(schema_rows[0]) != ("schema_version", "1"):
            raise RunnerError("workflow schema metadata is invalid")
        required_triggers = {
            "invocation_records_immutable_update",
            "invocation_records_immutable_delete",
            "result_records_immutable_update",
            "result_records_immutable_delete",
            "gate_records_immutable_update",
            "gate_records_immutable_delete",
            "stage_attempts_immutable_update",
            "stage_attempts_immutable_delete",
            "workflow_events_immutable_update",
            "workflow_events_immutable_delete",
            "transitions_immutable_update",
            "transitions_immutable_delete",
            "blocks_immutable_update",
            "blocks_immutable_delete",
        }
        trigger_names = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger'"
            )
        }
        if required_triggers - trigger_names:
            raise RunnerError("workflow store schema is incomplete")
        trigger_contracts = {
            "invocation_records_immutable_update": ("update", "invocation_records", "immutable invocation record"),
            "invocation_records_immutable_delete": ("delete", "invocation_records", "immutable invocation record"),
            "result_records_immutable_update": ("update", "result_records", "immutable result record"),
            "result_records_immutable_delete": ("delete", "result_records", "immutable result record"),
            "gate_records_immutable_update": ("update", "gate_records", "immutable gate record"),
            "gate_records_immutable_delete": ("delete", "gate_records", "immutable gate record"),
            "stage_attempts_immutable_update": ("update", "stage_attempts", "immutable stage attempt"),
            "stage_attempts_immutable_delete": ("delete", "stage_attempts", "immutable stage attempt"),
            "workflow_events_immutable_update": ("update", "workflow_events", "immutable workflow event"),
            "workflow_events_immutable_delete": ("delete", "workflow_events", "immutable workflow event"),
            "transitions_immutable_update": ("update", "transitions", "immutable transition"),
            "transitions_immutable_delete": ("delete", "transitions", "immutable transition"),
            "blocks_immutable_update": ("update", "blocks", "immutable block"),
            "blocks_immutable_delete": ("delete", "blocks", "immutable block"),
        }
        for name, (operation, table, message) in trigger_contracts.items():
            row = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?",
                (name,),
            ).fetchone()
            expected = f"create trigger {name} before {operation} on {table} begin select raise(abort, '{message}'); end"
            actual = " ".join(str(row[0]).split()).casefold().rstrip(";") if row else ""
            if actual != expected:
                raise RunnerError("workflow immutable trigger definition is invalid")
        extra_triggers = trigger_names - set(trigger_contracts)
        if extra_triggers:
            raise RunnerError("workflow store schema contains unexpected objects")
        for object_type, name in connection.execute(
            "SELECT type, name FROM sqlite_master WHERE type IN ('index', 'view')"
        ):
            if object_type == "index" and str(name).startswith("sqlite_autoindex_"):
                continue
            raise RunnerError("workflow store schema contains unexpected objects")
        metadata = connection.execute(
            "SELECT run_id, schema_version, sequence, head_sha256, blocked, block_reason FROM run_metadata"
        ).fetchall()
        if (
            len(metadata) != 1
            or metadata[0][0] != self.run_id
            or metadata[0][1] != 1
            or type(metadata[0][2]) is not int
            or not _SHA256.fullmatch(str(metadata[0][3]))
        ):
            raise RunnerError("workflow run metadata is invalid")

    def _initialize_store(self) -> None:
        with self._writer_lock():
            try:
                with self._transaction() as connection:
                    version = int(connection.execute("PRAGMA user_version").fetchone()[0])
                    if version not in {0, 1}:
                        raise RunnerError("workflow store schema version is unsupported")
                    tables = {
                        str(row[0])
                        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
                    }
                    if version == 1 and "run_metadata" not in tables:
                        raise RunnerError("workflow store schema is incomplete")
                    if version == 0 and tables - {"sqlite_sequence"}:
                        raise RunnerError("workflow store schema is malformed")
                    if version == 1:
                        self._validate_existing_schema(connection, tables)
                        return
                    connection.executescript(
                        """
                        CREATE TABLE IF NOT EXISTS schema_meta (
                            key TEXT PRIMARY KEY,
                            value TEXT NOT NULL
                        );
                        CREATE TABLE IF NOT EXISTS run_metadata (
                            run_id TEXT PRIMARY KEY,
                            schema_version INTEGER NOT NULL,
                            sequence INTEGER NOT NULL,
                            head_sha256 TEXT NOT NULL,
                            blocked INTEGER NOT NULL DEFAULT 0,
                            block_reason TEXT
                        );
                        CREATE TABLE IF NOT EXISTS stage_attempts (
                            run_id TEXT NOT NULL,
                            stage TEXT NOT NULL,
                            revision INTEGER NOT NULL,
                            attempt INTEGER NOT NULL,
                            role TEXT NOT NULL,
                            input_hashes_json TEXT NOT NULL,
                            output_path TEXT NOT NULL,
                            result_sha256 TEXT,
                            gate_sha256 TEXT,
                            blocked INTEGER NOT NULL DEFAULT 0,
                            block_reason TEXT,
                            advanced INTEGER NOT NULL DEFAULT 0,
                            PRIMARY KEY (run_id, stage, revision, attempt)
                        );
                        CREATE TABLE IF NOT EXISTS invocation_records (
                            run_id TEXT NOT NULL,
                            stage TEXT NOT NULL,
                            revision INTEGER NOT NULL,
                            attempt INTEGER NOT NULL,
                            record_json TEXT NOT NULL,
                            record_sha256 TEXT NOT NULL,
                            PRIMARY KEY (run_id, stage, revision, attempt)
                        );
                        CREATE TABLE IF NOT EXISTS result_records (
                            run_id TEXT NOT NULL,
                            stage TEXT NOT NULL,
                            revision INTEGER NOT NULL,
                            attempt INTEGER NOT NULL,
                            record_json TEXT NOT NULL,
                            record_sha256 TEXT NOT NULL,
                            PRIMARY KEY (run_id, stage, revision, attempt)
                        );
                        CREATE TABLE IF NOT EXISTS gate_records (
                            run_id TEXT NOT NULL,
                            stage TEXT NOT NULL,
                            revision INTEGER NOT NULL,
                            attempt INTEGER NOT NULL,
                            record_json TEXT NOT NULL,
                            record_sha256 TEXT NOT NULL,
                            PRIMARY KEY (run_id, stage, revision, attempt)
                        );
                        CREATE TABLE IF NOT EXISTS transitions (
                            run_id TEXT NOT NULL,
                            sequence INTEGER NOT NULL,
                            action TEXT NOT NULL,
                            stage TEXT NOT NULL,
                            revision INTEGER NOT NULL,
                            attempt INTEGER NOT NULL,
                            next_stage TEXT,
                            event_sha256 TEXT NOT NULL,
                            PRIMARY KEY (run_id, sequence)
                        );
                        CREATE TABLE IF NOT EXISTS blocks (
                            run_id TEXT NOT NULL,
                            sequence INTEGER NOT NULL,
                            stage TEXT NOT NULL,
                            revision INTEGER NOT NULL,
                            attempt INTEGER NOT NULL,
                            reason TEXT NOT NULL,
                            detail TEXT NOT NULL,
                            PRIMARY KEY (run_id, sequence)
                        );
                        CREATE TABLE IF NOT EXISTS workflow_events (
                            run_id TEXT NOT NULL,
                            sequence INTEGER NOT NULL,
                            action TEXT NOT NULL,
                            stage TEXT NOT NULL,
                            revision INTEGER NOT NULL,
                            attempt INTEGER NOT NULL,
                            event_json TEXT NOT NULL,
                            previous_sha256 TEXT NOT NULL,
                            event_sha256 TEXT NOT NULL,
                            PRIMARY KEY (run_id, sequence),
                            UNIQUE (run_id, event_sha256)
                        );
                        CREATE TRIGGER IF NOT EXISTS invocation_records_immutable_update
                        BEFORE UPDATE ON invocation_records BEGIN SELECT RAISE(ABORT, 'immutable invocation record'); END;
                        CREATE TRIGGER IF NOT EXISTS invocation_records_immutable_delete
                        BEFORE DELETE ON invocation_records BEGIN SELECT RAISE(ABORT, 'immutable invocation record'); END;
                        CREATE TRIGGER IF NOT EXISTS result_records_immutable_update
                        BEFORE UPDATE ON result_records BEGIN SELECT RAISE(ABORT, 'immutable result record'); END;
                        CREATE TRIGGER IF NOT EXISTS result_records_immutable_delete
                        BEFORE DELETE ON result_records BEGIN SELECT RAISE(ABORT, 'immutable result record'); END;
                        CREATE TRIGGER IF NOT EXISTS gate_records_immutable_update
                        BEFORE UPDATE ON gate_records BEGIN SELECT RAISE(ABORT, 'immutable gate record'); END;
                        CREATE TRIGGER IF NOT EXISTS gate_records_immutable_delete
                        BEFORE DELETE ON gate_records BEGIN SELECT RAISE(ABORT, 'immutable gate record'); END;
                        CREATE TRIGGER IF NOT EXISTS stage_attempts_immutable_update
                        BEFORE UPDATE ON stage_attempts BEGIN SELECT RAISE(ABORT, 'immutable stage attempt'); END;
                        CREATE TRIGGER IF NOT EXISTS stage_attempts_immutable_delete
                        BEFORE DELETE ON stage_attempts BEGIN SELECT RAISE(ABORT, 'immutable stage attempt'); END;
                        CREATE TRIGGER IF NOT EXISTS workflow_events_immutable_update
                        BEFORE UPDATE ON workflow_events BEGIN SELECT RAISE(ABORT, 'immutable workflow event'); END;
                        CREATE TRIGGER IF NOT EXISTS workflow_events_immutable_delete
                        BEFORE DELETE ON workflow_events BEGIN SELECT RAISE(ABORT, 'immutable workflow event'); END;
                        CREATE TRIGGER IF NOT EXISTS transitions_immutable_update
                        BEFORE UPDATE ON transitions BEGIN SELECT RAISE(ABORT, 'immutable transition'); END;
                        CREATE TRIGGER IF NOT EXISTS transitions_immutable_delete
                        BEFORE DELETE ON transitions BEGIN SELECT RAISE(ABORT, 'immutable transition'); END;
                        CREATE TRIGGER IF NOT EXISTS blocks_immutable_update
                        BEFORE UPDATE ON blocks BEGIN SELECT RAISE(ABORT, 'immutable block'); END;
                        CREATE TRIGGER IF NOT EXISTS blocks_immutable_delete
                        BEFORE DELETE ON blocks BEGIN SELECT RAISE(ABORT, 'immutable block'); END;
                        """
                    )
                    connection.execute("PRAGMA user_version=1")
                    connection.execute("INSERT OR IGNORE INTO schema_meta(key, value) VALUES('schema_version', '1')")
                    connection.execute(
                        "INSERT OR IGNORE INTO run_metadata(run_id, schema_version, sequence, head_sha256, blocked) VALUES(?, 1, 0, ?, 0)",
                        (self.run_id, _GENESIS_SHA256),
                    )
                    metadata = connection.execute("SELECT run_id, schema_version, sequence, head_sha256, blocked FROM run_metadata").fetchall()
                    if len(metadata) != 1 or metadata[0][0] != self.run_id or metadata[0][1] != 1:
                        raise RunnerError("workflow run metadata is invalid")
            except RunnerError:
                raise
            except (OSError, sqlite3.Error, ValueError) as exc:
                raise RunnerError("workflow store could not be initialized") from exc


    def begin(
        self,
        stage: PlanningStage | str,
        *,
        role: str,
        input_paths: Sequence[Path],
        output_path: str,
    ) -> AgentInvocation:
        with self._writer_lock():
            identity: _Identity | None = None
            try:
                requested = _stage(stage)
                role_id = _safe_id(role, "role")
                relative_output = _safe_relative(output_path, "output target")
                if relative_output != output_path:
                    raise RunnerError("invalid output target")
                self._safe_path(self.project_root / relative_output, "output target")
                hashes = self._hash_inputs(input_paths)
                with self._transaction() as connection:
                    self._validate_store(connection)
                    metadata = connection.execute(
                        "SELECT blocked, block_reason FROM run_metadata WHERE run_id=?",
                        (self.run_id,),
                    ).fetchone()
                    if (
                        metadata is not None
                        and bool(metadata[0])
                        and str(metadata[1] or "") in _NON_RETRYABLE_METADATA_BLOCK_REASONS
                    ):
                        raise RunnerBlocked(
                            f"run is blocked: {metadata[1] or 'blocked'}"
                        )
                    completed, attempts = self._history(connection)
                    if any(state.blocked and state.advanced for state in attempts.values()):
                        raise RunnerBlocked("workflow run is terminally blocked")
                    expected = _STAGE_ORDER[len(completed)] if len(completed) < len(_STAGE_ORDER) else None
                    if requested is not expected:
                        expected_name = expected.value if expected is not None else "none"
                        raise RunnerError(f"expected stage {expected_name}, got {requested.value}")
                    previous = attempts.get(requested.value)
                    if previous is not None and not (previous.blocked or self._attempt_failed(previous)):
                        raise RunnerError("current attempt is unfinished")
                    if previous is None:
                        revision, attempt = 1, 1
                    else:
                        prior_revision = _positive_int(previous.begin["revision"], "revision")
                        prior_attempt = _positive_int(previous.begin["attempt"], "attempt")
                        prior_hashes = _validated_input_hashes(previous.begin["input_hashes"])
                        revision, attempt = ((prior_revision, prior_attempt + 1) if prior_hashes == hashes else (prior_revision + 1, 1))
                    invocation = AgentInvocation(1, self.run_id, requested, revision, attempt, role_id, hashes, relative_output)
                    identity = self._identity(invocation)
                    self._insert_attempt_and_invocation(connection, invocation)
                    self._append_event(connection, {
                        "action": "begin", "run_id": self.run_id, "stage": requested.value,
                        "revision": revision, "attempt": attempt, "role": role_id,
                        "input_hashes": invocation.input_hashes, "output_path": relative_output,
                    })
                    connection.execute("UPDATE run_metadata SET blocked=0, block_reason=NULL WHERE run_id=?", (self.run_id,))
                self._known_attempts.add(identity)
                self._refresh_projections_or_block(identity, "begin_projection_failure")
                return invocation
            except RunnerBlocked:
                raise
            except RunnerError as exc:
                if identity is not None:
                    self._mutation_failed(identity, "begin_write_failure", exc)
                    raise RunnerBlocked("runner mutation failed closed") from exc
                raise
            except (OSError, UnicodeError, RecursionError, TypeError, ValueError, OverflowError, sqlite3.Error) as exc:
                self._mutation_failed(identity, "begin_write_failure", exc)
                raise RunnerBlocked("runner mutation failed closed") from exc

    def record_result(self, invocation: AgentInvocation, result: Mapping[str, object]) -> AgentResultRecord:
        with self._writer_lock():
            identity = self._identity_if_valid(invocation)
            blocked_reason: str | None = None
            try:
                with self._transaction() as connection:
                    self._validate_store(connection)
                    self._validate_invocation_in_store(connection, invocation)
                    self._require_current_attempt(connection, invocation, no_result=True)
                    stale = self._stale_input_reason(invocation)
                    if stale is not None:
                        self._insert_block(connection, invocation, "stale_input", stale)
                        blocked_reason = "stale input"
                        record = None
                    else:
                        try:
                            record = self._build_result(invocation, result)
                        except RunnerError as exc:
                            self._insert_block(connection, invocation, "agent_result_invalid", str(exc))
                            blocked_reason = str(exc)
                            record = None
                        if record is not None:
                            result_json = _canonical(record.to_dict()).decode("utf-8")
                            self._insert_record(connection, "result_records", invocation, record_json=result_json, record_sha256=_record_sha(record))
                            result_path = self._record_file(invocation, "result.json").relative_to(self.project_root).as_posix()
                            self._append_event(connection, {
                                "action": "result", "run_id": self.run_id, "stage": invocation.stage.value,
                                "revision": invocation.revision, "attempt": invocation.attempt,
                                "ok": record.ok, "result_path": result_path,
                                "payload_sha256": record.payload_sha256, "result_sha256": _record_sha(record),
                            })
                            if not record.ok:
                                blocked_reason = record.error or "agent returned a failed result"
                                self._insert_block(connection, invocation, "agent_result_failed", blocked_reason)
                            else:
                                blocked_reason = None
                if blocked_reason is not None:
                    self._refresh_projections_safely()
                    raise RunnerBlocked(blocked_reason)
                assert record is not None
                self._refresh_projections_or_block(identity, "result_projection_failure")
                return record
            except RunnerBlocked:
                raise
            except RunnerError as exc:
                self._mutation_failed(identity, "result_evidence_invalid", exc)
                raise RunnerBlocked(f"runner mutation failed closed: {exc}") from exc
            except (OSError, UnicodeError, RecursionError, TypeError, ValueError, OverflowError, sqlite3.Error) as exc:
                self._mutation_failed(identity, "result_write_failure", exc)
                raise RunnerBlocked("runner mutation failed closed") from exc

    def record_gate(
        self,
        invocation: AgentInvocation,
        *,
        verification: GateVerification | Mapping[str, object] | None = None,
        gate_id: str | None = None,
        passed: bool | None = None,
        detail: str | None = None,
        evidence: Mapping[str, object] | None = None,
    ) -> GateRecord:
        with self._writer_lock():
            identity = self._identity_if_valid(invocation)
            gate_failed = False
            blocked_reason: str | None = None
            try:
                if (
                    gate_id is not None
                    or passed is not None
                    or detail is not None
                    or evidence is not None
                ):
                    raise RunnerError(
                        "caller gate decision fields are not accepted; trusted parent gate verification is required"
                    )
                if verification is None or isinstance(verification, Mapping):
                    raise RunnerError("trusted parent gate verification is required")
                if not isinstance(verification, GateVerification) or verification._capability is not self._gate_capability:
                    raise RunnerError("trusted parent gate provenance is invalid")
                verification_value = GateVerification.from_dict(verification) if isinstance(verification, Mapping) else verification
                with self._transaction() as connection:
                    self._validate_store(connection)
                    self._validate_invocation_in_store(connection, invocation)
                    self._require_current_attempt(connection, invocation)
                    stale = self._stale_input_reason(invocation)
                    if stale is not None:
                        self._insert_block(connection, invocation, "stale_input", stale)
                        blocked_reason = "stale input"
                        record = None
                    else:
                        try:
                            result_record = self._result_from_store(connection, invocation)
                            record = self._validate_gate_verification(invocation, result_record, verification_value)
                        except RunnerError as exc:
                            self._insert_block(connection, invocation, "gate_evidence_invalid", str(exc))
                            blocked_reason = str(exc)
                            record = None
                        if record is not None:
                            record_sha = _record_sha(record)
                            record_json = _canonical(record.to_dict()).decode("utf-8")
                            self._insert_record(connection, "gate_records", invocation, record_json=record_json, record_sha256=record_sha)
                            self._append_event(connection, {
                                "action": "gate", "run_id": self.run_id, "stage": invocation.stage.value,
                                "revision": invocation.revision, "attempt": invocation.attempt,
                                "gate_id": record.gate_id, "status": record.status, "detail": record.detail,
                                "evidence_sha256": record.evidence_sha256, "invocation_sha256": record.invocation_sha256,
                                "result_sha256": record.result_sha256, "output_sha256": record.output_sha256,
                                "input_hashes": record.input_hashes, "policy_version": record.policy_version,
                                "resolver_id": record.resolver_id,
                            })
                            if not record.passed:
                                blocked_reason = record.detail
                                gate_failed = True
                                self._insert_block(connection, invocation, "gate_failed", record.detail)
                            else:
                                blocked_reason = None
                if blocked_reason is not None and not gate_failed:
                    self._refresh_projections_safely()
                    raise RunnerBlocked(blocked_reason)
                assert record is not None
                self._refresh_projections_or_block(identity, "gate_projection_failure")
                return record
            except RunnerBlocked:
                raise
            except RunnerError as exc:
                self._mutation_failed(identity, "gate_evidence_invalid", exc)
                raise RunnerBlocked(f"runner mutation failed closed: {exc}") from exc
            except (OSError, UnicodeError, RecursionError, TypeError, ValueError, OverflowError, sqlite3.Error) as exc:
                self._mutation_failed(identity, "gate_write_failure", exc)
                raise RunnerBlocked("runner mutation failed closed") from exc

    def advance(self, invocation: AgentInvocation) -> PlanningStage | None:
        with self._writer_lock():
            identity = self._identity_if_valid(invocation)
            try:
                try:
                    self._validate_invocation(invocation)
                except RunnerError as exc:
                    self._mutation_failed(identity, "advance_evidence_invalid", exc)
                    raise RunnerBlocked("invocation evidence is invalid") from exc
                with self._transaction() as connection:
                    self._validate_store(connection)
                    self._validate_invocation_in_store(connection, invocation)
                    self._require_current_attempt(connection, invocation)
                    stale = self._stale_input_reason(invocation)
                    if stale is not None:
                        self._insert_block(connection, invocation, "stale_input", stale)
                        blocked_reason = "stale input"
                        next_stage = None
                    else:
                        try:
                            result_record = self._result_from_store(connection, invocation)
                            gate_record = self._gate_from_store(connection, invocation, result_record)
                        except RunnerError as exc:
                            self._insert_block(connection, invocation, "advance_evidence_invalid", str(exc))
                            blocked_reason = str(exc)
                            next_stage = None
                        else:
                            if not result_record.ok:
                                self._insert_block(connection, invocation, "advance_evidence_invalid", "agent result did not pass")
                                blocked_reason = "result and gate evidence are required"
                                next_stage = None
                            elif not gate_record.passed:
                                self._insert_block(connection, invocation, "advance_evidence_invalid", "gate did not pass")
                                blocked_reason = "result and gate evidence are required"
                                next_stage = None
                            else:
                                next_index = _STAGE_ORDER.index(invocation.stage) + 1
                                next_stage = _STAGE_ORDER[next_index] if next_index < len(_STAGE_ORDER) else None
                                self._append_event(connection, {
                                    "action": "advance", "run_id": self.run_id, "stage": invocation.stage.value,
                                    "revision": invocation.revision, "attempt": invocation.attempt,
                                    "next_stage": next_stage.value if next_stage is not None else None,
                                })
                                blocked_reason = None
                if blocked_reason is not None:
                    self._refresh_projections_safely()
                    raise RunnerBlocked(blocked_reason)
                self._refresh_projections_or_block(identity, "advance_projection_failure")
                return next_stage
            except RunnerBlocked:
                raise
            except RunnerError as exc:
                self._mutation_failed(identity, "advance_evidence_invalid", exc)
                raise RunnerBlocked(f"runner mutation failed closed: {exc}") from exc
            except (OSError, UnicodeError, RecursionError, TypeError, ValueError, OverflowError, sqlite3.Error) as exc:
                self._mutation_failed(identity, "advance_write_failure", exc)
                raise RunnerBlocked("runner mutation failed closed") from exc

    def status(self) -> WorkflowState:
        with self._writer_lock():
            try:
                with self._transaction() as connection:
                    metadata = connection.execute(
                        "SELECT blocked, block_reason FROM run_metadata WHERE run_id=?",
                        (self.run_id,),
                    ).fetchone()
                    if metadata is not None and bool(metadata[0]) and metadata[1] == "durable_unavailable":
                        return WorkflowState(1, self.run_id, None, True, "durable_unavailable", (), {})
                    state = self._status_from_connection(connection)
                if not state.blocked:
                    self._validate_projection_views(state)
                return state
            except RunnerError:
                raise
            except (OSError, UnicodeError, sqlite3.Error, ValueError, TypeError, OverflowError) as exc:
                raise RunnerError("workflow store is unavailable") from exc

    def _initialize_recovery_block(self, reason: str) -> None:
        with self._transaction() as connection:
            connection.execute("UPDATE run_metadata SET blocked=1, block_reason=? WHERE run_id=?", (reason, self.run_id))

    def _recover_interrupted_attempts(self) -> None:
        recovery_identity: _Identity | None = None
        try:
            with self._transaction() as connection:
                self._validate_store(connection)
                projection_intact = self._projection_matches_connection(connection)
                _, attempts = self._history(connection)
                event_count = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM workflow_events WHERE run_id=?",
                        (self.run_id,),
                    ).fetchone()[0]
                )
                candidate: AgentInvocation | None = None
                changed = False
                metadata = connection.execute("SELECT blocked FROM run_metadata WHERE run_id=?", (self.run_id,)).fetchone()
                if metadata is None or not bool(metadata[0]):
                    for stage_name, state in attempts.items():
                        if state.blocked or state.advanced or state.result is not None or state.gate is not None:
                            continue
                        revision = _positive_int(state.begin.get("revision"), "revision")
                        attempt = _positive_int(state.begin.get("attempt"), "attempt")
                        row = connection.execute(
                            "SELECT record_json FROM invocation_records WHERE run_id=? AND stage=? AND revision=? AND attempt=?",
                            (self.run_id, stage_name, revision, attempt),
                        ).fetchone()
                        if row is None:
                            raise RunnerError("invocation record is missing")
                        invocation = _invocation_from_record(_strict_json_loads(str(row[0])), self.run_id)
                        if self._identity(invocation) not in self._known_attempts:
                            candidate = invocation
                            break
                if candidate is not None:
                    recovery_identity = self._identity(candidate)
                    self._insert_recovery_block(
                        connection,
                        candidate,
                        "interrupted_attempt",
                        "begin-only attempt recovered fail-closed",
                    )
                    changed = True
                if (metadata is None or not bool(metadata[0])) and event_count and not projection_intact:
                    anchor = candidate or self._recovery_anchor(connection)
                    recovery_identity = self._identity(anchor)
                    self._insert_recovery_block(
                        connection,
                        anchor,
                        "recovery_integrity",
                        "high-level workflow projection is missing or invalid",
                    )
                    changed = True
                missing = self._missing_projection_record(connection)
                if missing is not None:
                    recovery_identity = self._identity(missing)
                    self._insert_recovery_block(
                        connection,
                        missing,
                        "recovery_integrity",
                        "committed record projection is missing",
                    )
                    changed = True
                if self._orphan_records(connection):
                    anchor = candidate or (self._recovery_anchor(connection) if event_count else None)
                    if anchor is None:
                        connection.execute(
                            "UPDATE run_metadata SET blocked=1, block_reason=? WHERE run_id=?",
                            ("orphan_record", self.run_id),
                        )
                    else:
                        recovery_identity = self._identity(anchor)
                        self._insert_recovery_block(
                            connection,
                            anchor,
                            "orphan_record",
                            "unreferenced stage projection recovered fail-closed",
                        )
                    changed = True
            if changed and (projection_intact or missing is not None):
                self._refresh_projections_safely()
        except RunnerBlocked:
            raise
        except (OSError, RunnerError, sqlite3.Error, ValueError, TypeError, OverflowError) as exc:
            self._mutation_failed(recovery_identity, "recovery_write_failure", exc)
            raise RunnerBlocked("workflow recovery failed closed") from exc

    def _insert_recovery_block(
        self,
        connection: sqlite3.Connection,
        invocation: AgentInvocation,
        reason: str,
        detail: str,
    ) -> None:
        if not self._insert_block(connection, invocation, reason, detail):
            raise RunnerError("recovery block anchor is unavailable")

    def _recovery_anchor(self, connection: sqlite3.Connection) -> AgentInvocation:
        row = connection.execute(
            "SELECT record_json FROM invocation_records WHERE run_id=? ORDER BY stage, revision, attempt LIMIT 1",
            (self.run_id,),
        ).fetchone()
        if row is None:
            raise RunnerError("recovery anchor invocation is missing")
        return _invocation_from_record(_strict_json_loads(str(row[0])), self.run_id)

    def _orphan_records(self, connection: sqlite3.Connection) -> bool:
        stages_dir = self._safe_path(self.run_dir / "stages", "stage records")
        if not stages_dir.exists():
            return False
        if not stages_dir.is_dir():
            return True
        referenced: set[tuple[_Identity, str]] = set()
        for row in connection.execute(
            "SELECT action, stage, revision, attempt FROM workflow_events WHERE run_id=?",
            (self.run_id,),
        ):
            action = str(row[0])
            if action in {"begin", "result", "gate"}:
                revision = _positive_int(row[2], "orphan record revision")
                attempt = _positive_int(row[3], "orphan record attempt")
                referenced.add(
                    (
                        (str(row[1]), revision, attempt),
                        "invocation.json" if action == "begin" else f"{action}.json",
                    )
                )
        control_names = {"invocation.json", "result.json", "gate.json"}
        try:
            for path in stages_dir.rglob("*"):
                safe = self._safe_path(path, "stage record")
                relative = safe.relative_to(stages_dir).parts
                if len(relative) == 1:
                    try:
                        _stage(relative[0])
                    except RunnerError:
                        return True
                    if not safe.is_dir():
                        return True
                    continue
                if len(relative) == 2:
                    if (
                        not safe.is_dir()
                        or re.fullmatch(r"r([1-9][0-9]*)", relative[1], re.IGNORECASE)
                        is None
                    ):
                        return True
                    continue
                if len(relative) == 3:
                    if (
                        not safe.is_dir()
                        or re.fullmatch(r"a([1-9][0-9]*)", relative[2], re.IGNORECASE)
                        is None
                    ):
                        return True
                    continue
                if len(relative) != 4 or relative[3].casefold() not in control_names:
                    return True
                if not safe.is_file():
                    return True
                identity = self._record_identity_from_path(safe)
                if (
                    identity is None
                    or identity[1] > _SQLITE_INTEGER_MAX
                    or identity[2] > _SQLITE_INTEGER_MAX
                    or (identity, relative[3].casefold()) not in referenced
                ):
                    return True
            return False
        except (OSError, RuntimeError, ValueError, RunnerError):
            return True

    def _missing_projection_record(self, connection: sqlite3.Connection) -> AgentInvocation | None:
        for row in connection.execute(
            "SELECT stage, revision, attempt, action FROM workflow_events WHERE run_id=? AND action IN ('begin','result','gate')",
            (self.run_id,),
        ):
            revision = _positive_int(row[1], "projection revision")
            attempt = _positive_int(row[2], "projection attempt")
            identity = (str(row[0]), revision, attempt)
            invocation_row = connection.execute("SELECT record_json FROM invocation_records WHERE run_id=? AND stage=? AND revision=? AND attempt=?", (self.run_id, *identity)).fetchone()
            if invocation_row is None:
                continue
            invocation = _invocation_from_record(_strict_json_loads(str(invocation_row[0])), self.run_id)
            filename = "invocation.json" if row[3] == "begin" else f"{row[3]}.json"
            if not self._record_file(invocation, filename).exists():
                return invocation
        return None

    def _identity_if_valid(self, invocation: object) -> _Identity | None:
        if not isinstance(invocation, AgentInvocation) or not isinstance(invocation.stage, PlanningStage):
            return None
        if invocation.run_id != self.run_id or type(invocation.revision) is not int or type(invocation.attempt) is not int:
            return None
        if not 1 <= invocation.revision <= _SQLITE_INTEGER_MAX or not 1 <= invocation.attempt <= _SQLITE_INTEGER_MAX:
            return None
        return invocation.stage.value, invocation.revision, invocation.attempt

    def _identity(self, invocation: AgentInvocation) -> _Identity:
        return invocation.stage.value, invocation.revision, invocation.attempt

    def _hash_inputs(self, input_paths: Sequence[Path]) -> dict[str, str]:
        if isinstance(input_paths, (str, bytes)):
            raise RunnerError("input paths must be a sequence of paths")
        hashes: dict[str, str] = {}
        total = 0
        count = 0
        for input_path in input_paths:
            count += 1
            if count > _MAX_INPUT_FILES:
                raise RunnerBlocked("too many input files")
            safe_input = safe_resolve(self.project_root, Path(input_path))
            if safe_input is None or not safe_input.is_file():
                raise RunnerBlocked("input is missing or unsafe")
            relative = safe_input.relative_to(self.project_root).as_posix()
            if relative in hashes:
                raise RunnerError("duplicate input path")
            digest = hashlib.sha256()
            try:
                with safe_input.open("rb") as stream:
                    while True:
                        chunk = stream.read(1024 * 1024)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > _MAX_INPUT_BYTES:
                            raise RunnerBlocked("input set is oversized")
                        digest.update(chunk)
            except RunnerBlocked:
                raise
            except (OSError, ValueError) as exc:
                raise RunnerBlocked("input is unreadable") from exc
            hashes[relative] = digest.hexdigest()
        return dict(sorted(hashes.items()))

    def _safe_path(self, path: Path, label: str) -> Path:
        safe = safe_resolve(self.project_root, path)
        if safe is None:
            raise RunnerError(f"{label} path is unsafe")
        return safe

    def _register_gate_attestation(self, verification: GateVerification) -> None:
        token = verification._attestation_token
        if token is None:
            raise RunnerError("gate attestation token is missing")
        self._gate_attestations[token] = _gate_attestation_fingerprint(verification)

    def _validate_output_binding(self, invocation: AgentInvocation) -> Path:
        output_path = _safe_relative(invocation.output_path, "output target")
        if output_path != invocation.output_path:
            raise RunnerError("parent output binding is invalid")
        return self._safe_path(self.project_root / output_path, "output target")

    def _output_artifact_hash(self, invocation: AgentInvocation) -> str:
        path = self._validate_output_binding(invocation)
        try:
            if not path.is_file() or path.stat().st_size > _MAX_OUTPUT_BYTES:
                raise RunnerError("parent output artifact is missing or oversized")
            digest = hashlib.sha256()
            total = 0
            with path.open("rb") as stream:
                while True:
                    chunk = stream.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > _MAX_OUTPUT_BYTES:
                        raise RunnerError("parent output artifact is oversized")
                    digest.update(chunk)
            return digest.hexdigest()
        except RunnerError:
            raise
        except (OSError, ValueError) as exc:
            raise RunnerError("parent output artifact is unreadable") from exc

    def _record_dir_for(self, stage: PlanningStage, revision: int, attempt: int) -> Path:
        return self._safe_path(self.run_dir / "stages" / stage.value / f"r{revision}" / f"a{attempt}", "stage record")

    def _record_dir(self, invocation: AgentInvocation) -> Path:
        return self._record_dir_for(invocation.stage, invocation.revision, invocation.attempt)

    def _record_file(self, invocation: AgentInvocation, filename: str) -> Path:
        return self._safe_path(self._record_dir(invocation) / filename, f"{filename} record")

    def _record_identity_from_path(self, path: Path) -> _Identity | None:
        try:
            parts = path.relative_to(self.run_dir / "stages").parts
            if len(parts) != 4:
                return None
            stage = _stage(parts[0]).value
            revision_match = re.fullmatch(r"r([1-9][0-9]*)", parts[1], re.IGNORECASE)
            attempt_match = re.fullmatch(r"a([1-9][0-9]*)", parts[2], re.IGNORECASE)
            if revision_match is None or attempt_match is None:
                return None
            return stage, int(revision_match.group(1)), int(attempt_match.group(1))
        except (OSError, ValueError, RunnerError):
            return None

    def _write_json(self, path: Path, value: object, label: str) -> None:
        safe = self._safe_path(path, label)
        _validate_json_value(value)
        try:
            content = json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
        except (RecursionError, TypeError, ValueError) as exc:
            raise _RunnerEncodeError(f"{label} is not strict JSON") from exc
        if len(content.encode("utf-8")) > _MAX_JSON_BYTES:
            raise RunnerError(f"{label} is oversized")
        _atomic_write(safe, content)

    def _read_json(self, path: Path, label: str) -> object:
        safe = self._safe_path(path, label)
        try:
            return _strict_json_loads(_read_limited(safe, _MAX_JSON_BYTES, label))
        except RunnerError:
            raise
        except (OSError, UnicodeError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RunnerError(f"{label} is unreadable") from exc

    def _validate_invocation(self, invocation: AgentInvocation) -> None:
        if not isinstance(invocation, AgentInvocation) or invocation.run_id != self.run_id or type(invocation.schema) is not int or invocation.schema != 1:
            raise RunnerError("invocation identity is invalid")
        if not isinstance(invocation.stage, PlanningStage):
            raise RunnerError("invocation stage is invalid")
        _stage(invocation.stage.value)
        _positive_int(invocation.revision, "revision")
        _positive_int(invocation.attempt, "attempt")
        _safe_id(invocation.role, "role")
        _validated_input_hashes(invocation.input_hashes)
        self._validate_output_binding(invocation)
        with self._transaction() as connection:
            self._validate_invocation_in_store(connection, invocation)

    def _assert_current_attempt(self, invocation: AgentInvocation, *, require_no_result: bool = False) -> None:
        with self._transaction() as connection:
            self._validate_store(connection)
            self._require_current_attempt(connection, invocation, no_result=require_no_result)

    def _assert_inputs_current(self, invocation: AgentInvocation) -> None:
        reason = self._stale_input_reason(invocation)
        if reason is None:
            return
        try:
            with self._transaction() as connection:
                self._validate_store(connection)
                self._insert_block(connection, invocation, "stale_input", reason)
        except (OSError, sqlite3.Error, ValueError, TypeError) as exc:
            self._mutation_failed(self._identity_if_valid(invocation), "stale_input", exc)
        raise RunnerBlocked("stale input")

    def _validate_invocation_in_store(self, connection: sqlite3.Connection, invocation: AgentInvocation) -> None:
        if not isinstance(invocation, AgentInvocation) or invocation.run_id != self.run_id or type(invocation.schema) is not int or invocation.schema != 1:
            raise RunnerError("invocation identity is invalid")
        if not isinstance(invocation.stage, PlanningStage):
            raise RunnerError("invocation stage is invalid")
        _positive_int(invocation.revision, "revision")
        _positive_int(invocation.attempt, "attempt")
        _safe_id(invocation.role, "role")
        _validated_input_hashes(invocation.input_hashes)
        self._validate_output_binding(invocation)
        row = connection.execute(
            "SELECT record_json, record_sha256 FROM invocation_records WHERE run_id=? AND stage=? AND revision=? AND attempt=?",
            (self.run_id, invocation.stage.value, invocation.revision, invocation.attempt),
        ).fetchone()
        if row is None:
            raise RunnerError("invocation record is missing")
        stored = _invocation_from_record(_strict_json_loads(str(row[0])), self.run_id)
        if stored.to_dict() != invocation.to_dict() or row[1] != _record_sha(stored):
            raise RunnerError("invocation record does not match")
        self._validate_projection_record(invocation, "invocation.json", stored.to_dict())

    def _validate_projection_record(self, invocation: AgentInvocation, filename: str, expected: object) -> None:
        path = self._record_file(invocation, filename)
        if not path.exists():
            return
        stored = self._read_json(path, f"{filename} record")
        if stored != expected:
            raise RunnerError(f"{filename} projection does not match store")

    def _require_current_attempt(self, connection: sqlite3.Connection, invocation: AgentInvocation, *, no_result: bool = False) -> _AttemptState:
        metadata = connection.execute(
            "SELECT blocked, block_reason FROM run_metadata WHERE run_id=?",
            (self.run_id,),
        ).fetchone()
        if metadata is None:
            raise RunnerError("workflow run metadata is missing")
        if bool(metadata[0]):
            raise RunnerBlocked(f"run is blocked: {metadata[1] or 'blocked'}")
        completed, attempts = self._history(connection)
        current = _STAGE_ORDER[len(completed)] if len(completed) < len(_STAGE_ORDER) else None
        state = attempts.get(invocation.stage.value)
        if current is not invocation.stage or state is None or not self._begin_matches(state, invocation):
            raise RunnerError("invocation is not the current attempt")
        if state.blocked or self._attempt_failed(state):
            raise RunnerBlocked(f"current attempt is blocked: {state.block_reason or 'blocked'}")
        if no_result and state.result is not None:
            raise RunnerError("result record already exists")
        return state

    def _begin_matches(self, state: _AttemptState, invocation: AgentInvocation) -> bool:
        expected = invocation.to_dict()
        return {key: state.begin.get(key) for key in expected} == expected

    def _attempt_failed(self, state: _AttemptState) -> bool:
        return (state.result is not None and state.result.get("ok") is False) or (state.gate is not None and state.gate.get("status") == "fail")

    def _stale_input_reason(self, invocation: AgentInvocation) -> str | None:
        total_bytes = 0
        for relative, expected in invocation.input_hashes.items():
            try:
                path = self._safe_path(self.project_root / relative, "input")
                if not path.is_file():
                    return "input is missing or unsafe"
                remaining = _MAX_INPUT_BYTES - total_bytes
                if remaining <= 0 or path.stat().st_size > remaining:
                    return "input set is oversized"
                digest = hashlib.sha256()
                with path.open("rb") as stream:
                    while chunk := stream.read(min(1024 * 1024, remaining + 1)):
                        total_bytes += len(chunk)
                        if total_bytes > _MAX_INPUT_BYTES:
                            return "input set is oversized"
                        digest.update(chunk)
                if digest.hexdigest() != expected:
                    return "input hash changed"
            except (OSError, ValueError, RunnerError):
                return "input is missing or unsafe"
        return None

    def _build_result(self, invocation: AgentInvocation, result: Mapping[str, object]) -> AgentResultRecord:
        if not isinstance(result, Mapping) or any(not isinstance(key, str) for key in result) or set(result) - {"ok", "payload", "session_id", "error"} or "ok" not in result or "payload" not in result:
            raise RunnerError("agent result schema is invalid")
        ok = result.get("ok")
        payload = result.get("payload")
        if type(ok) is not bool or not isinstance(payload, Mapping):
            raise RunnerError("agent result schema is invalid")
        _reject_output_target_spoof(payload)
        session_id = result.get("session_id")
        if session_id is not None:
            session_id = _safe_id(session_id, "session_id")
        error = result.get("error")
        if error is not None:
            error = _safe_text(error, "agent error", required=False)
        payload_data = dict(payload)
        payload_hash = _sha(_bounded_json(payload_data, "result payload", _MAX_PAYLOAD_BYTES))
        record = AgentResultRecord(1, self.run_id, invocation.stage, invocation.revision, invocation.attempt, ok, payload_data, payload_hash, session_id, error)
        _bounded_json(record.to_dict(), "result record", _MAX_JSON_BYTES)
        return record

    def _read_current_result(self, invocation: AgentInvocation) -> AgentResultRecord:
        with self._transaction() as connection:
            self._validate_store(connection)
            return self._result_from_store(connection, invocation)

    def _result_from_store(self, connection: sqlite3.Connection, invocation: AgentInvocation) -> AgentResultRecord:
        row = connection.execute("SELECT record_json, record_sha256 FROM result_records WHERE run_id=? AND stage=? AND revision=? AND attempt=?", (self.run_id, invocation.stage.value, invocation.revision, invocation.attempt)).fetchone()
        if row is None:
            raise RunnerError("result journal record is missing")
        record = _result_from_record(_strict_json_loads(str(row[0])), self.run_id)
        if record.stage is not invocation.stage or record.revision != invocation.revision or record.attempt != invocation.attempt or row[1] != _record_sha(record):
            raise RunnerError("result record identity is invalid")
        self._validate_projection_record(invocation, "result.json", record.to_dict())
        return record

    def _validate_gate_verification(self, invocation: AgentInvocation, result_record: AgentResultRecord, verification: object) -> GateRecord:
        if not isinstance(verification, GateVerification) or verification._capability is not self._gate_capability:
            raise RunnerError("trusted parent gate verification is invalid")
        token = verification._attestation_token
        if not isinstance(token, _GateAttestationToken) or self._gate_attestations.get(token) != _gate_attestation_fingerprint(verification):
            raise RunnerError("gate verification attestation is invalid")
        if result_record.ok is not True:
            raise RunnerError("failed agent result cannot pass a gate")
        _positive_int(verification.revision, "gate verification revision")
        _positive_int(verification.attempt, "gate verification attempt")
        if verification.run_id != self.run_id or verification.stage is not invocation.stage or verification.revision != invocation.revision or verification.attempt != invocation.attempt:
            raise RunnerError("gate verification lineage does not match")
        if dict(verification.input_hashes) != dict(invocation.input_hashes):
            raise RunnerError("gate verification input binding does not match")
        gate_id = _safe_id(verification.gate_id, "gate_id")
        if gate_id != f"gate-{invocation.stage.value}":
            raise RunnerError("gate is not in the trusted allowlist")
        if type(verification.passed) is not bool:
            raise RunnerError("gate result must be boolean")
        detail = _safe_text(verification.detail, "gate detail")
        policy = _safe_text(verification.policy_version, "policy version")
        resolver = _safe_text(verification.resolver_id, "resolver id")
        evidence = dict(verification.evidence)
        _reject_output_target_spoof(evidence)
        _bounded_json(evidence, "gate evidence", _MAX_EVIDENCE_BYTES)
        invocation_hash = _record_sha(invocation)
        result_hash = _record_sha(result_record)
        output_hash = self._output_artifact_hash(invocation)
        if verification.invocation_sha256 != invocation_hash or verification.result_sha256 != result_hash or verification.output_sha256 != output_hash:
            raise RunnerError("gate verification binding does not match")
        evidence_hash = _gate_evidence_hash(invocation_hash, result_hash, output_hash, evidence, input_hashes=invocation.input_hashes, policy_version=policy, resolver_id=resolver)
        if verification.evidence_sha256 != evidence_hash:
            raise RunnerError("gate verification evidence hash does not match")
        record = GateRecord(1, self.run_id, invocation.stage, invocation.revision, invocation.attempt, gate_id, "pass" if verification.passed else "fail", detail, evidence_hash, invocation_hash, result_hash, output_hash, evidence, dict(invocation.input_hashes), policy, resolver)
        _bounded_json(record.to_dict(), "gate record", _MAX_JSON_BYTES)
        return record

    def _read_current_gate(self, invocation: AgentInvocation, result_record: AgentResultRecord) -> GateRecord:
        with self._transaction() as connection:
            self._validate_store(connection)
            return self._gate_from_store(connection, invocation, result_record)

    def _gate_from_store(self, connection: sqlite3.Connection, invocation: AgentInvocation, result_record: AgentResultRecord) -> GateRecord:
        row = connection.execute("SELECT record_json, record_sha256 FROM gate_records WHERE run_id=? AND stage=? AND revision=? AND attempt=?", (self.run_id, invocation.stage.value, invocation.revision, invocation.attempt)).fetchone()
        if row is None:
            raise RunnerError("gate journal record is missing")
        record = _gate_from_record(_strict_json_loads(str(row[0])), self.run_id)
        if record.stage is not invocation.stage or record.revision != invocation.revision or record.attempt != invocation.attempt or record.input_hashes != invocation.input_hashes or record.invocation_sha256 != _record_sha(invocation) or record.result_sha256 != _record_sha(result_record) or record.output_sha256 != self._output_artifact_hash(invocation) or row[1] != _record_sha(record):
            raise RunnerError("gate evidence binding does not match")
        self._validate_projection_record(invocation, "gate.json", record.to_dict())
        return record

    def _insert_attempt_and_invocation(self, connection: sqlite3.Connection, invocation: AgentInvocation) -> None:
        identity = self._identity(invocation)
        invocation_json = _canonical(invocation.to_dict()).decode("utf-8")
        invocation_hash = _record_sha(invocation)
        _bounded_json(invocation.to_dict(), "invocation record", _MAX_JSON_BYTES)
        try:
            connection.execute("INSERT INTO stage_attempts(run_id, stage, revision, attempt, role, input_hashes_json, output_path) VALUES(?,?,?,?,?,?,?)", (self.run_id, *identity, invocation.role, _canonical(invocation.input_hashes).decode("utf-8"), invocation.output_path))
            connection.execute("INSERT INTO invocation_records(run_id, stage, revision, attempt, record_json, record_sha256) VALUES(?,?,?,?,?,?)", (self.run_id, *identity, invocation_json, invocation_hash))
        except sqlite3.IntegrityError as exc:
            raise RunnerError("duplicate workflow identity") from exc

    def _insert_record(self, connection: sqlite3.Connection, table: str, invocation: AgentInvocation, *, record_json: str, record_sha256: str) -> None:
        try:
            connection.execute(f"INSERT INTO {table}(run_id, stage, revision, attempt, record_json, record_sha256) VALUES(?,?,?,?,?,?)", (self.run_id, invocation.stage.value, invocation.revision, invocation.attempt, record_json, record_sha256))
        except sqlite3.IntegrityError as exc:
            raise RunnerError("duplicate workflow record") from exc

    def _append_event(self, connection: sqlite3.Connection, payload: Mapping[str, object]) -> dict[str, object]:
        if set(payload) & {"schema", "sequence", "previous_sha256", "event_sha256"}:
            raise RunnerError("workflow event contains reserved fields")
        metadata = connection.execute("SELECT sequence, head_sha256 FROM run_metadata WHERE run_id=?", (self.run_id,)).fetchone()
        if metadata is None:
            raise RunnerError("workflow run metadata is missing")
        sequence_value = _nonnegative_int(metadata[0], "workflow sequence")
        if sequence_value == _SQLITE_INTEGER_MAX:
            raise RunnerError("workflow sequence is exhausted")
        sequence = sequence_value + 1
        previous = str(metadata[1])
        event: dict[str, object] = {"schema": 1, **dict(payload), "sequence": sequence, "previous_sha256": previous, "event_sha256": ""}
        event["event_sha256"] = _event_sha(event)
        validated = self._validate_event_schema(event, sequence, previous)
        event_json = _canonical(validated).decode("utf-8")
        existing_bytes = sum(len(_canonical(item)) + 1 for item in self._events_from_connection(connection))
        if existing_bytes + len(event_json.encode("utf-8")) + 1 > _MAX_WORKFLOW_JOURNAL_BYTES:
            raise RunnerError("workflow journal is oversized")
        identity = self._event_identity(validated)
        connection.execute("INSERT INTO workflow_events(run_id, sequence, action, stage, revision, attempt, event_json, previous_sha256, event_sha256) VALUES(?,?,?,?,?,?,?,?,?)", (self.run_id, sequence, str(validated["action"]), identity[0], identity[1], identity[2], event_json, previous, str(validated["event_sha256"])))
        action = str(validated["action"])
        next_stage = validated.get("next_stage") if action == "advance" else None
        connection.execute("INSERT INTO transitions(run_id, sequence, action, stage, revision, attempt, next_stage, event_sha256) VALUES(?,?,?,?,?,?,?,?)", (self.run_id, sequence, action, identity[0], identity[1], identity[2], next_stage, str(validated["event_sha256"])))
        if action == "block":
            connection.execute("INSERT INTO blocks(run_id, sequence, stage, revision, attempt, reason, detail) VALUES(?,?,?,?,?,?,?)", (self.run_id, sequence, identity[0], identity[1], identity[2], str(validated["reason"]), str(validated["detail"])))
        connection.execute("UPDATE run_metadata SET sequence=?, head_sha256=? WHERE run_id=?", (sequence, str(validated["event_sha256"]), self.run_id))
        return validated

    def _insert_block(self, connection: sqlite3.Connection, invocation: AgentInvocation, reason: str, detail: str) -> bool:
        reason_id = _safe_id(reason, "block reason")
        detail_text = _safe_text(detail, "block detail")
        row = connection.execute(
            "SELECT stage, revision, attempt FROM stage_attempts WHERE run_id=? AND stage=? AND revision=? AND attempt=?",
            (self.run_id, invocation.stage.value, invocation.revision, invocation.attempt),
        ).fetchone()
        if row is None:
            connection.execute("UPDATE run_metadata SET blocked=1, block_reason=? WHERE run_id=?", (reason_id, self.run_id))
            return False
        events = self._events_from_connection(connection)
        matching = [event for event in events if self._event_identity(event) == (invocation.stage.value, invocation.revision, invocation.attempt)]
        begin_events = [event for event in matching if event["action"] == "begin"]
        if len(begin_events) != 1:
            connection.execute("UPDATE run_metadata SET blocked=1, block_reason=? WHERE run_id=?", (reason_id, self.run_id))
            return False
        state = _AttemptState(dict(begin_events[0]))
        state.result = next((dict(event) for event in matching if event["action"] == "result"), None)
        state.gate = next((dict(event) for event in matching if event["action"] == "gate"), None)
        block_event = next((event for event in matching if event["action"] == "block"), None)
        state.blocked = block_event is not None
        state.block_reason = str(block_event["reason"]) if block_event is not None else None
        state.advanced = any(event["action"] == "advance" for event in matching)
        if not self._begin_matches(state, invocation):
            connection.execute("UPDATE run_metadata SET blocked=1, block_reason=? WHERE run_id=?", (reason_id, self.run_id))
            return False
        if state.blocked:
            return True
        if state.advanced:
            self._append_event(
                connection,
                {
                    "action": "block",
                    "run_id": self.run_id,
                    "stage": invocation.stage.value,
                    "revision": invocation.revision,
                    "attempt": invocation.attempt,
                    "reason": reason_id,
                    "detail": detail_text,
                },
            )
            connection.execute("UPDATE run_metadata SET blocked=1, block_reason=? WHERE run_id=?", (reason_id, self.run_id))
            return True
        self._append_event(connection, {"action": "block", "run_id": self.run_id, "stage": invocation.stage.value, "revision": invocation.revision, "attempt": invocation.attempt, "reason": reason_id, "detail": detail_text})
        connection.execute("UPDATE run_metadata SET blocked=1, block_reason=? WHERE run_id=?", (reason_id, self.run_id))
        return True

    def _mutation_failed(self, identity: _Identity | None, reason: str, error: BaseException) -> None:
        try:
            rendered = str(error)
        except Exception:
            rendered = "runner mutation failed"
        rendered = "".join(
            char if ord(char) >= 32 and ord(char) != 127 else " "
            for char in rendered
        )
        detail_bytes = rendered.encode("utf-8", errors="replace")[:_MAX_TEXT_BYTES]
        detail = detail_bytes.decode("utf-8", errors="ignore").strip() or "runner mutation failed"
        durable = False
        try:
            with self._transaction() as connection:
                if identity is not None:
                    row = connection.execute("SELECT 1 FROM stage_attempts WHERE run_id=? AND stage=? AND revision=? AND attempt=?", (self.run_id, *identity)).fetchone()
                    if row is not None:
                        invocation_row = connection.execute("SELECT record_json FROM invocation_records WHERE run_id=? AND stage=? AND revision=? AND attempt=?", (self.run_id, *identity)).fetchone()
                        if invocation_row is not None:
                            invocation = _invocation_from_record(_strict_json_loads(str(invocation_row[0])), self.run_id)
                            durable = self._insert_block(connection, invocation, reason, detail)
                if not durable:
                    connection.execute(
                        "UPDATE run_metadata SET blocked=1, block_reason=? WHERE run_id=?",
                        ("durable_unavailable", self.run_id),
                    )
        except (OSError, RunnerError, sqlite3.Error, ValueError, TypeError, OverflowError):
            try:
                with self._transaction() as connection:
                    connection.execute(
                        "UPDATE run_metadata SET blocked=1, block_reason=? WHERE run_id=?",
                        ("durable_unavailable", self.run_id),
                    )
            except (OSError, RunnerError, sqlite3.Error, ValueError, TypeError, OverflowError) as durable_exc:
                raise RunnerBlocked(
                    f"runner mutation failed closed; durable block unavailable: {reason}"
                ) from durable_exc
            raise RunnerBlocked(
                f"runner mutation failed closed; durable block unavailable: {reason}"
            )
        if not durable:
            raise RunnerBlocked(
                f"runner mutation failed closed; durable block unavailable: {reason}"
            )

    def _refresh_projections_safely(self) -> None:
        try:
            self._refresh_projections()
        except (OSError, UnicodeError, RecursionError, TypeError, ValueError, RunnerError):
            pass

    def _refresh_projections_or_block(self, identity: _Identity | None, reason: str) -> None:
        try:
            self._refresh_projections()
        except (OSError, UnicodeError, RecursionError, TypeError, ValueError, OverflowError, sqlite3.Error, RunnerError) as exc:
            self._mutation_failed(identity, reason, exc)
            raise RunnerBlocked(f"runner mutation failed closed: {reason}") from exc

    def _refresh_projections(self) -> None:
        for _ in range(3):
            with self._transaction() as connection:
                state = self._status_from_connection(connection)
                events = self._events_from_connection(connection)
                metadata = connection.execute("SELECT sequence, head_sha256 FROM run_metadata WHERE run_id=?", (self.run_id,)).fetchone()
                if metadata is None:
                    raise RunnerError("workflow run metadata is missing")
                generation = (int(metadata[0]), str(metadata[1]))
                event_content = "".join(_canonical(event).decode("utf-8") + "\n" for event in events)
                if len(event_content.encode("utf-8")) > _MAX_WORKFLOW_JOURNAL_BYTES:
                    raise RunnerError("workflow journal is oversized")
            run_dir = self._safe_path(self.run_dir, "planning run")
            run_dir.mkdir(parents=True, exist_ok=True)
            _atomic_write(self._safe_path(self.events_path, "workflow journal"), event_content)
            self._write_json(self.integrity_path, {"schema": 1, "run_id": self.run_id, "event_count": generation[0], "head_sha256": generation[1]}, "workflow integrity")
            self._write_record_projections()
            self._write_json(self.state_path, state.to_dict(), "workflow state")
            with self._transaction() as connection:
                current = connection.execute("SELECT sequence, head_sha256 FROM run_metadata WHERE run_id=?", (self.run_id,)).fetchone()
            if current is not None and (int(current[0]), str(current[1])) == generation:
                return
        raise RunnerError("workflow projections changed during refresh")

    def _write_record_projections(self) -> None:
        with self._transaction() as connection:
            for table, filename in (("invocation_records", "invocation.json"), ("result_records", "result.json"), ("gate_records", "gate.json")):
                rows = connection.execute(f"SELECT stage, revision, attempt, record_json FROM {table} WHERE run_id=? ORDER BY stage, revision, attempt", (self.run_id,)).fetchall()
                for row in rows:
                    invocation = AgentInvocation(
                        1,
                        self.run_id,
                        _stage(row[0]),
                        _positive_int(row[1], "projection revision"),
                        _positive_int(row[2], "projection attempt"),
                        "projection",
                        {},
                        ".projection",
                    )
                    value = _strict_json_loads(str(row[3]))
                    self._write_json(self._record_file(invocation, filename), value, f"{filename} record")

    def _validate_projection_views(self, state: WorkflowState) -> None:
        events_path = self._safe_path(self.events_path, "workflow journal")
        integrity_path = self._safe_path(self.integrity_path, "workflow integrity")
        state_path = self._safe_path(self.state_path, "workflow state")
        with self._transaction() as connection:
            expected_events = self._events_from_connection(connection)
            metadata = connection.execute("SELECT sequence, head_sha256 FROM run_metadata WHERE run_id=?", (self.run_id,)).fetchone()
        if metadata is None:
            raise RunnerError("workflow run metadata is missing")
        if not events_path.exists():
            if expected_events:
                raise RunnerError("workflow journal projection is missing")
            return
        raw_lines = _read_limited(events_path, _MAX_WORKFLOW_JOURNAL_BYTES, "workflow journal").splitlines()
        if not integrity_path.exists() or not state_path.exists():
            raise RunnerError("workflow journal projection is missing")
        projected_events = [_strict_json_loads(line) for line in raw_lines]
        if projected_events != expected_events:
            raise RunnerError("workflow journal projection does not match store")
        integrity = self._read_json(integrity_path, "workflow integrity")
        if integrity != {"schema": 1, "run_id": self.run_id, "event_count": int(metadata[0]), "head_sha256": str(metadata[1])}:
            raise RunnerError("workflow integrity projection does not match store")
        projected_state = self._read_json(state_path, "workflow state")
        if projected_state != state.to_dict():
            raise RunnerError("workflow state projection does not match store")
        with self._transaction() as connection:
            if not self._record_projections_match_connection(connection):
                raise RunnerError("stage record projection does not match store")

    def _record_projections_match_connection(self, connection: sqlite3.Connection) -> bool:
        invocation_rows = connection.execute(
            "SELECT stage, revision, attempt, record_json, record_sha256 FROM invocation_records WHERE run_id=?",
            (self.run_id,),
        ).fetchall()
        invocation_identities: set[_Identity] = set()
        for row in invocation_rows:
            try:
                invocation = _invocation_from_record(
                    _strict_json_loads(str(row[3])), self.run_id
                )
                identity = (
                    str(row[0]),
                    _positive_int(row[1], "invocation revision"),
                    _positive_int(row[2], "invocation attempt"),
                )
                if (
                    identity != self._identity(invocation)
                    or str(row[4]) != _record_sha(invocation)
                    or not self._projection_file_matches(
                        invocation, "invocation.json", invocation.to_dict()
                    )
                ):
                    return False
                invocation_identities.add(identity)
            except (OSError, RunnerError, TypeError, ValueError, sqlite3.Error):
                return False

        result_identities: set[_Identity] = set()
        for row in connection.execute(
            "SELECT stage, revision, attempt, record_json, record_sha256 FROM result_records WHERE run_id=?",
            (self.run_id,),
        ):
            try:
                identity = (
                    str(row[0]),
                    _positive_int(row[1], "result revision"),
                    _positive_int(row[2], "result attempt"),
                )
                invocation = _invocation_from_record(
                    _strict_json_loads(
                        str(
                            connection.execute(
                                "SELECT record_json FROM invocation_records WHERE run_id=? AND stage=? AND revision=? AND attempt=?",
                                (self.run_id, *identity),
                            ).fetchone()[0]
                        )
                    ),
                    self.run_id,
                )
                result = _result_from_record(_strict_json_loads(str(row[3])), self.run_id)
                if (
                    identity not in invocation_identities
                    or result.stage is not invocation.stage
                    or result.revision != invocation.revision
                    or result.attempt != invocation.attempt
                    or str(row[4]) != _record_sha(result)
                    or not self._projection_file_matches(
                        invocation, "result.json", result.to_dict()
                    )
                ):
                    return False
                result_identities.add(identity)
            except (OSError, RunnerError, TypeError, ValueError, sqlite3.Error, IndexError):
                return False

        for row in connection.execute(
            "SELECT stage, revision, attempt, record_json, record_sha256 FROM gate_records WHERE run_id=?",
            (self.run_id,),
        ):
            try:
                identity = (
                    str(row[0]),
                    _positive_int(row[1], "gate revision"),
                    _positive_int(row[2], "gate attempt"),
                )
                invocation_row = connection.execute(
                    "SELECT record_json FROM invocation_records WHERE run_id=? AND stage=? AND revision=? AND attempt=?",
                    (self.run_id, *identity),
                ).fetchone()
                invocation = _invocation_from_record(
                    _strict_json_loads(str(invocation_row[0])), self.run_id
                ) if invocation_row is not None else None
                gate = _gate_from_record(_strict_json_loads(str(row[3])), self.run_id)
                if (
                    invocation is None
                    or identity not in result_identities
                    or gate.stage is not invocation.stage
                    or gate.revision != invocation.revision
                    or gate.attempt != invocation.attempt
                    or gate.input_hashes != invocation.input_hashes
                    or gate.invocation_sha256 != _record_sha(invocation)
                    or str(row[4]) != _record_sha(gate)
                    or not self._projection_file_matches(
                        invocation, "gate.json", gate.to_dict()
                    )
                ):
                    return False
            except (OSError, RunnerError, TypeError, ValueError, sqlite3.Error):
                return False
        return True

    def _projection_file_matches(
        self, invocation: AgentInvocation, filename: str, expected: object
    ) -> bool:
        path = self._record_file(invocation, filename)
        if not path.is_file():
            return False
        return self._read_json(path, f"{filename} record") == expected

    def _projection_matches_connection(self, connection: sqlite3.Connection) -> bool:
        try:
            events = self._events_from_connection(connection)
            events_path = self._safe_path(self.events_path, "workflow journal")
            integrity_path = self._safe_path(self.integrity_path, "workflow integrity")
            state_path = self._safe_path(self.state_path, "workflow state")
            if not events_path.exists() or not integrity_path.exists() or not state_path.exists():
                return False
            projected = [_strict_json_loads(line) for line in _read_limited(events_path, _MAX_WORKFLOW_JOURNAL_BYTES, "workflow journal").splitlines()]
            if projected != events:
                return False
            state = self._status_from_connection(connection)
            metadata = connection.execute(
                "SELECT sequence, head_sha256 FROM run_metadata WHERE run_id=?",
                (self.run_id,),
            ).fetchone()
            if metadata is None:
                return False
            integrity = self._read_json(integrity_path, "workflow integrity")
            if integrity != {
                "schema": 1,
                "run_id": self.run_id,
                "event_count": int(metadata[0]),
                "head_sha256": str(metadata[1]),
            }:
                return False
            if self._read_json(state_path, "workflow state") != state.to_dict():
                return False
            return self._record_projections_match_connection(connection)
        except (OSError, UnicodeError, RunnerError, TypeError, ValueError, sqlite3.Error):
            return False

    def _events_from_connection(self, connection: sqlite3.Connection) -> list[dict[str, object]]:
        rows = connection.execute("SELECT sequence, event_json, previous_sha256, event_sha256, action, stage, revision, attempt FROM workflow_events WHERE run_id=? ORDER BY sequence", (self.run_id,)).fetchall()
        events: list[dict[str, object]] = []
        previous = _GENESIS_SHA256
        for expected, row in enumerate(rows, 1):
            sequence = _positive_int(row[0], "event sequence")
            if sequence != expected or str(row[2]) != previous:
                raise RunnerError("workflow sequence or hash chain is invalid")
            value = _strict_json_loads(str(row[1]))
            validated = self._validate_event_schema(value, expected, previous)
            if _canonical(validated).decode("utf-8") != str(row[1]) or str(row[3]) != str(validated["event_sha256"]) or (str(row[4]), str(row[5]), _positive_int(row[6], "event revision"), _positive_int(row[7], "event attempt")) != (str(validated["action"]), str(validated["stage"]), _positive_int(validated.get("revision"), "revision"), _positive_int(validated.get("attempt"), "attempt")):
                raise RunnerError("workflow event row is inconsistent")
            events.append(validated)
            previous = str(validated["event_sha256"])
        metadata = connection.execute("SELECT sequence, head_sha256 FROM run_metadata WHERE run_id=?", (self.run_id,)).fetchone()
        if (
            metadata is None
            or type(metadata[0]) is not int
            or metadata[0] < 0
            or metadata[0] > _SQLITE_INTEGER_MAX
            or metadata[0] != len(events)
            or str(metadata[1]) != (previous if events else _GENESIS_SHA256)
        ):
            raise RunnerError("workflow store integrity is invalid")
        return events

    def _history(self, connection: sqlite3.Connection) -> tuple[list[PlanningStage], dict[str, _AttemptState]]:
        events = self._events_from_connection(connection)
        completed: list[PlanningStage] = []
        attempts: dict[str, _AttemptState] = {}
        identities: dict[_Identity, _AttemptState] = {}
        terminal_blocked = False
        for event in events:
            action = str(event["action"])
            if terminal_blocked:
                raise RunnerError("workflow event follows terminal block")
            stage = _stage(event["stage"])
            identity = self._event_identity(event)
            if action == "begin":
                expected = _STAGE_ORDER[len(completed)] if len(completed) < len(_STAGE_ORDER) else None
                if stage is not expected:
                    raise RunnerError("workflow stage sequence is invalid")
                previous = attempts.get(stage.value)
                revision = _positive_int(event.get("revision"), "revision")
                attempt = _positive_int(event.get("attempt"), "attempt")
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
                    expected_identity = (prior_revision, prior_attempt + 1) if prior_hashes == current_hashes else (prior_revision + 1, 1)
                    if (revision, attempt) != expected_identity:
                        raise RunnerError("workflow retry identity is invalid")
                if identity in identities:
                    raise RunnerError("workflow attempt identity is duplicated")
                state = _AttemptState(dict(event))
                attempts[stage.value] = state
                identities[identity] = state
            else:
                state = identities.get(identity)
                if state is None or attempts.get(stage.value) is not state:
                    raise RunnerError("workflow event identity is invalid")
                if action == "result":
                    if state.result is not None or state.gate is not None or state.blocked or state.advanced:
                        raise RunnerError("workflow result sequence is invalid")
                    state.result = dict(event)
                elif action == "gate":
                    if state.result is None or state.gate is not None or state.blocked or state.advanced:
                        raise RunnerError("workflow gate sequence is invalid")
                    state.gate = dict(event)
                elif action == "block":
                    if state.blocked:
                        raise RunnerError("workflow block sequence is invalid")
                    state.blocked = True
                    state.block_reason = str(event["reason"])
                    terminal_blocked = state.advanced
                elif action == "advance":
                    expected = _STAGE_ORDER[len(completed)] if len(completed) < len(_STAGE_ORDER) else None
                    if stage is not expected or state.result is None or state.gate is None or state.blocked or state.result.get("ok") is not True or state.gate.get("status") != "pass":
                        raise RunnerError("workflow advance sequence is invalid")
                    state.advanced = True
                    completed.append(stage)
        for state in attempts.values():
            if state.result is not None and state.result.get("ok") is False and not state.blocked:
                raise RunnerError("failed result is not blocked")
            if state.gate is not None and state.gate.get("status") == "fail" and not state.blocked:
                raise RunnerError("failed gate is not blocked")
        return completed, attempts

    def _validate_store(self, connection: sqlite3.Connection) -> None:
        schema_meta = connection.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()
        if schema_meta is None or schema_meta[0] != "1":
            raise RunnerError("workflow schema metadata is invalid")
        metadata = connection.execute("SELECT run_id, schema_version, sequence, head_sha256, blocked, block_reason FROM run_metadata").fetchall()
        if len(metadata) != 1 or metadata[0][0] != self.run_id or metadata[0][1] != 1 or type(metadata[0][2]) is not int or not _SHA256.fullmatch(str(metadata[0][3])):
            raise RunnerError("workflow run metadata is invalid")
        events = self._events_from_connection(connection)
        completed, attempts = self._history(connection)
        del completed
        event_by_identity: dict[_Identity, list[dict[str, object]]] = {}
        for event in events:
            event_by_identity.setdefault(self._event_identity(event), []).append(event)
        for event in events:
            identity = self._event_identity(event)
            action = str(event["action"])
            if action == "begin":
                row = connection.execute("SELECT record_json, record_sha256 FROM invocation_records WHERE run_id=? AND stage=? AND revision=? AND attempt=?", (self.run_id, *identity)).fetchone()
                if row is None:
                    raise RunnerError("invocation record is missing")
                invocation = _invocation_from_record(_strict_json_loads(str(row[0])), self.run_id)
                if invocation.to_dict() != {key: event[key] for key in invocation.to_dict()} or row[1] != _record_sha(invocation):
                    raise RunnerError("invocation store binding is invalid")
            elif action == "result":
                row = connection.execute("SELECT record_json, record_sha256 FROM result_records WHERE run_id=? AND stage=? AND revision=? AND attempt=?", (self.run_id, *identity)).fetchone()
                if row is None:
                    raise RunnerError("result record is missing")
                result = _result_from_record(_strict_json_loads(str(row[0])), self.run_id)
                if result.stage.value != identity[0] or result.revision != identity[1] or result.attempt != identity[2] or event["ok"] is not result.ok or event["payload_sha256"] != result.payload_sha256 or event["result_sha256"] != _record_sha(result) or row[1] != _record_sha(result):
                    raise RunnerError("result store binding is invalid")
            elif action == "gate":
                row = connection.execute("SELECT record_json, record_sha256 FROM gate_records WHERE run_id=? AND stage=? AND revision=? AND attempt=?", (self.run_id, *identity)).fetchone()
                if row is None:
                    raise RunnerError("gate record is missing")
                gate = _gate_from_record(_strict_json_loads(str(row[0])), self.run_id)
                invocation_row = connection.execute("SELECT record_json FROM invocation_records WHERE run_id=? AND stage=? AND revision=? AND attempt=?", (self.run_id, *identity)).fetchone()
                result_row = connection.execute("SELECT record_json FROM result_records WHERE run_id=? AND stage=? AND revision=? AND attempt=?", (self.run_id, *identity)).fetchone()
                if invocation_row is None or result_row is None:
                    raise RunnerError("gate binding records are missing")
                invocation = _invocation_from_record(_strict_json_loads(str(invocation_row[0])), self.run_id)
                result = _result_from_record(_strict_json_loads(str(result_row[0])), self.run_id)
                if gate.stage.value != identity[0] or gate.revision != identity[1] or gate.attempt != identity[2] or gate.input_hashes != invocation.input_hashes or gate.invocation_sha256 != _record_sha(invocation) or gate.result_sha256 != _record_sha(result) or gate.output_sha256 != self._output_artifact_hash(invocation) or any(event[key] != gate.to_dict()[key] for key in ("gate_id", "status", "detail", "evidence_sha256", "invocation_sha256", "result_sha256", "output_sha256", "input_hashes", "policy_version", "resolver_id")) or row[1] != _record_sha(gate):
                    raise RunnerError("gate store binding is invalid")
        stage_rows = connection.execute("SELECT stage, revision, attempt, role, input_hashes_json, output_path, result_sha256, gate_sha256, blocked, block_reason, advanced FROM stage_attempts WHERE run_id=?", (self.run_id,)).fetchall()
        if len(stage_rows) != sum(1 for event in events if event["action"] == "begin"):
            raise RunnerError("stage attempt count is contradictory")
        for row in stage_rows:
            identity = (
                str(row[0]),
                _positive_int(row[1], "stage attempt revision"),
                _positive_int(row[2], "stage attempt attempt"),
            )
            begin_events = [event for event in event_by_identity.get(identity, ()) if event["action"] == "begin"]
            if len(begin_events) != 1:
                raise RunnerError("stage attempt identity is contradictory")
            begin = begin_events[0]
            if row[3] != begin["role"] or _strict_json_loads(str(row[4])) != begin["input_hashes"] or row[5] != begin["output_path"]:
                raise RunnerError("stage attempt binding is invalid")
            if row[6] is not None or row[7] is not None or bool(row[8]) or row[9] is not None or bool(row[10]):
                raise RunnerError("stage attempt derived fields are not immutable")
        transition_rows = connection.execute("SELECT sequence, action, stage, revision, attempt, next_stage, event_sha256 FROM transitions WHERE run_id=? ORDER BY sequence", (self.run_id,)).fetchall()
        if len(transition_rows) != len(events):
            raise RunnerError("transition count is contradictory")
        for event, row in zip(events, transition_rows, strict=True):
            identity = self._event_identity(event)
            if (_positive_int(row[0], "transition sequence"), row[1], row[2], _positive_int(row[3], "transition revision"), _positive_int(row[4], "transition attempt"), row[5], row[6]) != (_positive_int(event.get("sequence"), "sequence"), event["action"], identity[0], identity[1], identity[2], event.get("next_stage"), event["event_sha256"]):
                raise RunnerError("transition binding is invalid")
        block_rows = connection.execute("SELECT sequence, stage, revision, attempt, reason, detail FROM blocks WHERE run_id=? ORDER BY sequence", (self.run_id,)).fetchall()
        block_events = [event for event in events if event["action"] == "block"]
        if len(block_rows) != len(block_events):
            raise RunnerError("block count is contradictory")
        for event, row in zip(block_events, block_rows, strict=True):
            identity = self._event_identity(event)
            if (_positive_int(row[0], "block sequence"), row[1], _positive_int(row[2], "block revision"), _positive_int(row[3], "block attempt"), row[4], row[5]) != (_positive_int(event.get("sequence"), "sequence"), identity[0], identity[1], identity[2], event["reason"], event["detail"]):
                raise RunnerError("block binding is invalid")
        metadata_row = metadata[0]
        if bool(metadata_row[4]) and not metadata_row[5]:
            raise RunnerError("blocked run metadata has no reason")
        if not bool(metadata_row[4]) and metadata_row[5] is not None:
            raise RunnerError("unblocked run metadata has a block reason")
        for stage_name, state in attempts.items():
            if state.blocked:
                metadata_row = connection.execute("SELECT blocked FROM run_metadata WHERE run_id=?", (self.run_id,)).fetchone()
                if metadata_row is None or not bool(metadata_row[0]):
                    raise RunnerError("blocked attempt is not reflected in run metadata")
        for table in ("invocation_records", "result_records", "gate_records"):
            count = int(connection.execute(f"SELECT COUNT(*) FROM {table} WHERE run_id=?", (self.run_id,)).fetchone()[0])
            action = {"invocation_records": "begin", "result_records": "result", "gate_records": "gate"}[table]
            event_count = int(connection.execute("SELECT COUNT(*) FROM workflow_events WHERE run_id=? AND action=?", (self.run_id, action)).fetchone()[0])
            if count != event_count:
                raise RunnerError("workflow record count is contradictory")

    def _status_from_connection(self, connection: sqlite3.Connection) -> WorkflowState:
        self._validate_store(connection)
        completed, attempts = self._history(connection)
        metadata = connection.execute("SELECT blocked, block_reason FROM run_metadata WHERE run_id=?", (self.run_id,)).fetchone()
        if metadata is None:
            raise RunnerError("workflow run metadata is missing")
        current = _STAGE_ORDER[len(completed)].value if len(completed) < len(_STAGE_ORDER) else None
        current_attempt = attempts.get(current) if current is not None else None
        blocked = bool(metadata[0])
        reason = str(metadata[1]) if blocked and metadata[1] is not None else None
        if current_attempt is not None and current_attempt.blocked:
            blocked = True
            reason = current_attempt.block_reason
        latest_attempts = {name: _positive_int(state.begin.get("attempt"), "attempt") for name, state in attempts.items()}
        return WorkflowState(1, self.run_id, current, blocked, reason, tuple(stage.value for stage in _STAGE_ORDER[:len(completed)]), latest_attempts)

    def _event_identity(self, event: Mapping[str, object]) -> _Identity:
        return _stage(event.get("stage")).value, _positive_int(event.get("revision"), "revision"), _positive_int(event.get("attempt"), "attempt")

    def _validate_event_schema(self, event: object, expected_sequence: int, expected_previous_sha256: str) -> dict[str, object]:
        if not isinstance(event, Mapping) or any(not isinstance(key, str) for key in event):
            raise RunnerError("workflow journal event is invalid")
        action = event.get("action")
        if not isinstance(action, str) or action not in _ALLOWED_ACTIONS or set(event) != _EVENT_KEYS[action]:
            raise RunnerError("workflow journal event schema is invalid")
        if event.get("schema") != 1 or type(event.get("schema")) is not int or event.get("sequence") != expected_sequence or type(event.get("sequence")) is not int:
            raise RunnerError("workflow journal sequence or schema is invalid")
        previous = event.get("previous_sha256")
        event_hash = event.get("event_sha256")
        if not isinstance(previous, str) or _SHA256.fullmatch(previous) is None or previous != expected_previous_sha256 or not isinstance(event_hash, str) or _SHA256.fullmatch(event_hash) is None or event_hash != _event_sha(event):
            raise RunnerError("workflow journal integrity is invalid")
        if _safe_id(event.get("run_id"), "run_id") != self.run_id:
            raise RunnerError("workflow journal run identity is invalid")
        stage = _stage(event.get("stage"))
        revision = _positive_int(event.get("revision"), "revision")
        attempt = _positive_int(event.get("attempt"), "attempt")
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
            expected_path = self._record_dir_for(stage, revision, attempt) / "result.json"
            if result_path != event.get("result_path") or result_path != expected_path.relative_to(self.project_root).as_posix():
                raise RunnerError("workflow result path is invalid")
            _hash_string(event.get("payload_sha256"), "payload hash")
            _hash_string(event.get("result_sha256"), "result hash")
        elif action == "gate":
            if _safe_id(event.get("gate_id"), "gate_id") != f"gate-{stage.value}":
                raise RunnerError("workflow gate identity is invalid")
            if event.get("status") not in {"pass", "fail"}:
                raise RunnerError("workflow gate status is invalid")
            _safe_text(event.get("detail"), "gate detail")
            for field_name in ("evidence_sha256", "invocation_sha256", "result_sha256", "output_sha256"):
                _hash_string(event.get(field_name), field_name)
            _validated_input_hashes(event.get("input_hashes"))
            _safe_text(event.get("policy_version"), "policy version")
            _safe_text(event.get("resolver_id"), "resolver id")
        elif action == "advance":
            index = _STAGE_ORDER.index(stage) + 1
            expected_next = _STAGE_ORDER[index].value if index < len(_STAGE_ORDER) else None
            if event.get("next_stage") != expected_next:
                raise RunnerError("workflow advance target is invalid")
        else:
            _safe_id(event.get("reason"), "block reason")
            _safe_text(event.get("detail"), "block detail")
        return {str(key): value for key, value in event.items()}


__all__ = [
    "AgentInvocation",
    "AgentResultRecord",
    "GateVerification",
    "GateRecord",
    "PlanningRunner",
    "PlanningStage",
    "RunnerBlocked",
    "RunnerError",
    "WorkflowState",
]
