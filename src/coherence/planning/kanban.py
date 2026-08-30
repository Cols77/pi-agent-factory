"""Fail-closed durable transport projection for the FEAT-017 planning lifecycle.

This module stores operational state only.  Coherence artifacts and validation
outputs remain the semantic source of truth; this local projection never
schedules downstream work or claims an external Hermes Kanban integration.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Collection, Iterator, Mapping, Protocol

from coherence.planning.paths import safe_resolve, safe_root

PLANNING_ROOT_STAGE = "planning-run"
PLANNING_STAGES = (
    "capture",
    "provisional-spec-authoring",
    "spec-alignment",
    "candidate-sr-derivation",
    "candidate-sr-alignment",
    "implementation-plan-authoring",
    "task-materialization",
    "cross-artifact-alignment",
    "human-boundaries-and-adoption",
    "final-gates",
    "handoff",
)
_CANONICAL_STAGES = (PLANNING_ROOT_STAGE, *PLANNING_STAGES)
_WRITERS = {
    "capture",
    "provisional-spec-authoring",
    "candidate-sr-derivation",
    "implementation-plan-authoring",
    "task-materialization",
    "human-boundaries-and-adoption",
    "handoff",
}
_STATUSES = {"pending", "ready", "running", "complete", "blocked", "needs_input"}
_RESERVED_DEVICE_NAMES = {
    "aux",
    "clock$",
    "con",
    "nul",
    "prn",
    *(f"com{index}" for index in range(1, 10)),
    *(f"lpt{index}" for index in range(1, 10)),
}
_HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_STATE_SCHEMA = 2
_STATE_AUTH_ENV = "PI_AGENT_FACTORY_KANBAN_STATE_KEY"
_LEASE_TTL_MS = 30_000
_STATE_FIELDS = frozenset(
    {
        "schema",
        "run_id",
        "generation",
        "contract_sha256",
        "cards",
        "edges",
        "state_hmac_sha256",
    }
)
_CARD_FIELDS = frozenset(
    {
        "id",
        "run_id",
        "stage",
        "parents",
        "role",
        "assignee",
        "allowed_paths",
        "prohibited_paths",
        "workspace_mode",
        "workspace",
        "idempotency_key",
        "revision",
        "status",
        "attempt",
        "attempts",
        "gate_passed",
        "gate_detail",
        "blocking_reason",
        "output",
        "lease_token",
        "required_context",
        "lease_owner_pid",
        "lease_started_at",
        "lease_expires_at",
        "fencing_token",
    }
)
_ATTEMPT_FIELDS = {
    "claimed": frozenset({"attempt", "worker", "event"}),
    "heartbeat": frozenset({"attempt", "event"}),
    "completed": frozenset({"attempt", "event", "evidence"}),
    "blocked": frozenset({"attempt", "event", "reason", "needs_input", "evidence"}),
    "resumed": frozenset({"attempt", "event", "evidence"}),
    "reclaimed": frozenset(
        {"attempt", "event", "reason", "revision", "fencing_token", "previous_fencing_token"}
    ),
    "crash_reclaim": frozenset(
        {"attempt", "event", "reason", "revision", "fencing_token", "previous_fencing_token"}
    ),
    "gate_revoked": frozenset({"attempt", "event", "reason"}),
}
_ATTEMPT_EVENTS = frozenset(_ATTEMPT_FIELDS)


class PlanningKanbanError(ValueError):
    """Raised when the durable projection is invalid or cannot be reconciled."""


class StageBlocked(PlanningKanbanError):
    """Raised when a stage cannot safely make the requested transition."""


class WorkspacePolicyError(PlanningKanbanError):
    """Raised when workspace serialization or ownership cannot be proven."""


class AuthoritativeGateVerifier(Protocol):
    """Capability that proves a Coherence gate from an authoritative source."""

    def verify_gate(self, *, card: "StageCard", gate: Mapping[str, Any]) -> Mapping[str, Any] | None:
        """Return canonical verified evidence, or ``None`` to reject it."""


class HumanDecisionVerifier(Protocol):
    """Capability that proves a human decision came from an authorized source."""

    def verify_human_decision(
        self,
        *,
        card: "StageCard",
        decision: Mapping[str, Any],
        context: Mapping[str, Any],
    ) -> Mapping[str, Any] | None:
        """Return canonical verified decision evidence, or ``None`` to reject it."""


class FreshReviewVerifier(Protocol):
    """Capability that proves review evidence is fresh and authoritative."""

    def verify_fresh_review(
        self,
        *,
        card: "StageCard",
        review: Mapping[str, Any],
        context: Mapping[str, Any],
    ) -> Mapping[str, Any] | None:
        """Return canonical verified review evidence, or ``None`` to reject it."""


class _DenyAllGateVerifier:
    def verify_gate(self, *, card: "StageCard", gate: Mapping[str, Any]) -> Mapping[str, Any] | None:
        return None


class _DenyAllHumanDecisionVerifier:
    def verify_human_decision(
        self,
        *,
        card: "StageCard",
        decision: Mapping[str, Any],
        context: Mapping[str, Any],
    ) -> Mapping[str, Any] | None:
        return None


class _DenyAllFreshReviewVerifier:
    def verify_fresh_review(
        self,
        *,
        card: "StageCard",
        review: Mapping[str, Any],
        context: Mapping[str, Any],
    ) -> Mapping[str, Any] | None:
        return None


def _sha(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
    ).hexdigest()


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Reject duplicate JSON members instead of silently choosing one."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PlanningKanbanError("kanban JSON contains a duplicate field")
        result[key] = value
    return result


def _trusted_state_key() -> bytes:
    """Resolve trust from outside the state file; never derive it from mutable state.

    The state JSON is writable by the planning worker, so a digest or key stored
    beside it cannot authenticate anything.  The deployment must provide a
    separate, trusted HMAC key through the process environment (or a future
    trusted provider); missing/weak configuration fails closed.
    """
    value = os.environ.get(_STATE_AUTH_ENV)
    if value is None or len(value.encode("utf-8")) < 32:
        raise WorkspacePolicyError(
            f"authenticated kanban state requires {_STATE_AUTH_ENV} with at least 32 bytes"
        )
    return value.encode("utf-8")


def _state_authentication(payload: Mapping[str, Any]) -> str:
    return hmac.new(
        _trusted_state_key(),
        json.dumps(dict(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        ),
        hashlib.sha256,
    ).hexdigest()


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


def _json_copy(value: Mapping[str, Any], *, what: str) -> dict[str, Any]:
    try:
        copied = json.loads(json.dumps(dict(value), ensure_ascii=False))
    except (TypeError, ValueError) as exc:
        raise PlanningKanbanError(f"{what} must be JSON-serializable") from exc
    if not isinstance(copied, dict):
        raise PlanningKanbanError(f"{what} must be an object")
    return copied


def _contract_card(card: "StageCard") -> dict[str, Any]:
    """Return only immutable graph/card fields used by the contract hash."""
    values = card.to_dict()
    return {
        key: values[key]
        for key in (
            "id",
            "run_id",
            "stage",
            "parents",
            "role",
            "assignee",
            "allowed_paths",
            "prohibited_paths",
            "workspace_mode",
            "workspace",
            "idempotency_key",
        )
    }


def _safe_run(root: Path, run_id: str) -> Path:
    if not isinstance(run_id, str) or not run_id:
        raise PlanningKanbanError("run_id must be a safe path component")
    if run_id in {".", ".."} or run_id != run_id.strip():
        raise PlanningKanbanError("run_id must be a safe path component")
    if any(character.isspace() or ord(character) < 32 or ord(character) == 127 for character in run_id):
        raise PlanningKanbanError("run_id must not contain whitespace or control characters")
    if any(character in run_id for character in '/\\<>:"|?*'):
        raise PlanningKanbanError("run_id contains an unsafe path character")
    if run_id.endswith("."):
        raise PlanningKanbanError("run_id must not end with a dot")
    device_name = run_id.partition(".")[0].casefold()
    if device_name in _RESERVED_DEVICE_NAMES:
        raise PlanningKanbanError("run_id must not be a Windows device name")

    safe = safe_root(root)
    if safe is None:
        raise PlanningKanbanError("project root is unsafe")
    result = safe_resolve(safe, safe / ".factory" / "planning" / run_id)
    if result is None:
        raise PlanningKanbanError("planning run path is unsafe")
    return result


def _safe_state_path(root: Path, run_id: str) -> Path:
    run_path = _safe_run(root, run_id)
    state_path = run_path / "kanban-run.json"
    safe = safe_root(root)
    if safe is None or safe_resolve(safe, state_path) is None:
        raise PlanningKanbanError("kanban state path is unsafe")
    return state_path


def _safe_generation_path(root: Path, run_id: str) -> Path:
    run_path = _safe_run(root, run_id)
    generation_path = run_path / "kanban-high-water.json"
    safe = safe_root(root)
    if safe is None or safe_resolve(safe, generation_path) is None:
        raise PlanningKanbanError("kanban generation path is unsafe")
    return generation_path


def _writer_lock_path(root: Path) -> Path:
    safe = safe_root(root)
    if safe is None:
        raise WorkspacePolicyError("project root is unsafe")
    path = safe / ".factory" / "planning" / ".planning-writer.lock"
    if safe_resolve(safe, path) is None:
        raise WorkspacePolicyError("writer lock path is unsafe")
    return path


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".kanban-", suffix=".tmp", dir=str(path.parent))
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(dict(payload), stream, indent=2, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _generation_payload(run_id: str, generation: int) -> dict[str, Any]:
    return {"schema": 1, "run_id": run_id, "generation": generation}


def _generation_authentication(payload: Mapping[str, Any]) -> str:
    return _state_authentication(payload)


def _read_generation(root: Path, run_id: str) -> int:
    path = _safe_generation_path(root, run_id)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_strict_object)
    except (OSError, json.JSONDecodeError) as exc:
        raise PlanningKanbanError("kanban generation high-water record is unreadable") from exc
    fields = {"schema", "run_id", "generation", "generation_hmac_sha256"}
    if not isinstance(raw, Mapping) or set(raw) != fields:
        raise PlanningKanbanError("kanban generation high-water schema is invalid")
    generation = raw["generation"]
    if (
        raw["schema"] != 1
        or raw["run_id"] != run_id
        or not isinstance(generation, int)
        or isinstance(generation, bool)
        or generation < 1
        or not isinstance(raw["generation_hmac_sha256"], str)
        or not _HEX_SHA256.fullmatch(raw["generation_hmac_sha256"])
    ):
        raise PlanningKanbanError("kanban generation high-water record is invalid")
    expected = _generation_authentication(_generation_payload(run_id, generation))
    if not hmac.compare_digest(raw["generation_hmac_sha256"], expected):
        raise PlanningKanbanError("kanban generation high-water authentication is invalid")
    return generation


def _write_generation(root: Path, run_id: str, generation: int) -> None:
    path = _safe_generation_path(root, run_id)
    if path.exists():
        high_water = _read_generation(root, run_id)
        if generation < high_water:
            raise PlanningKanbanError("kanban generation would move backwards")
    payload = _generation_payload(run_id, generation)
    payload["generation_hmac_sha256"] = _generation_authentication(payload)
    _atomic_json(path, payload)


def _pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return True
    if os.name == "nt":
        try:
            import ctypes

            kernel32 = getattr(ctypes, "WinDLL")("kernel32", use_last_error=True)
            handle = kernel32.OpenProcess(0x1000 | 0x100000, False, pid)
            if not handle:
                # ERROR_FILE_NOT_FOUND, ERROR_PATH_NOT_FOUND, and
                # ERROR_INVALID_PARAMETER all mean no live process for this PID.
                return ctypes.get_last_error() not in {2, 3, 87}
            exit_code = ctypes.c_ulong()
            ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
            kernel32.CloseHandle(handle)
            return not ok or exit_code.value == 259
        except (AttributeError, OSError):
            return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        # An unknown Windows error is not proof that the owner is dead.
        return True
    return True


def _read_lock_record(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_strict_object
        )
    except (OSError, ValueError, json.JSONDecodeError, PlanningKanbanError) as exc:
        raise WorkspacePolicyError("lock file is malformed; refusing recovery") from exc
    fields = {"schema", "pid", "run_id", "card_id", "token"}
    if not isinstance(value, dict) or set(value) != fields:
        raise WorkspacePolicyError("lock file is malformed; refusing recovery")
    if (
        value["schema"] != 1
        or not isinstance(value["pid"], int)
        or isinstance(value["pid"], bool)
        or value["pid"] < 1
        or not isinstance(value["run_id"], str)
        or not value["run_id"]
        or not isinstance(value["card_id"], str)
        or not value["card_id"]
        or not isinstance(value["token"], str)
        or not value["token"]
    ):
        raise WorkspacePolicyError("lock file is malformed; refusing recovery")
    return value


def _try_recover_stale_lock(path: Path) -> bool:
    """Remove only a lock whose recorded owner is provably no longer alive.

    Recovery itself is fenced by an exclusive recovery marker.  If another
    recovery wins the race, this caller does not unlink anything.  A lock is
    never replaced with a new owner by overwriting it.
    """
    recovery = path.with_name(f"{path.name}.recovery")
    try:
        fd = os.open(
            str(recovery),
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0),
            0o600,
        )
    except FileExistsError:
        return False
    try:
        try:
            record = _read_lock_record(path)
        except FileNotFoundError:
            return True
        if _pid_is_alive(record["pid"]):
            return False
        try:
            current = _read_lock_record(path)
        except WorkspacePolicyError as exc:
            raise WorkspacePolicyError("lock changed during recovery") from exc
        if current != record:
            raise WorkspacePolicyError("lock changed during recovery")
        try:
            path.unlink()
        except FileNotFoundError:
            return True
        return True
    finally:
        os.close(fd)
        try:
            recovery.unlink()
        except FileNotFoundError:
            pass


@dataclass
class _ExclusiveLock:
    path: Path
    token: str
    run_id: str
    card_id: str
    released: bool = field(default=False, repr=False, compare=False)

    @classmethod
    def acquire(cls, path: Path, *, run_id: str, card_id: str) -> "_ExclusiveLock":
        path.parent.mkdir(parents=True, exist_ok=True)
        token = secrets.token_hex(24)
        payload = {
            "schema": 1,
            "pid": os.getpid(),
            "run_id": run_id,
            "card_id": card_id,
            "token": token,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        for attempt in range(2):
            try:
                fd = os.open(
                    str(path),
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0),
                    0o600,
                )
            except FileExistsError as exc:
                if attempt == 0 and _try_recover_stale_lock(path):
                    continue
                raise WorkspacePolicyError("workspace is already claimed by a writer") from exc
            try:
                with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                    stream.write(encoded)
                    stream.flush()
                    os.fsync(stream.fileno())
            except BaseException:
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
                raise
            return cls(path, token, run_id, card_id)
        raise WorkspacePolicyError("could not acquire exclusive lock")

    def assert_owned(self) -> None:
        if self.released:
            raise WorkspacePolicyError("writer lock handle is already released")
        record = _read_lock_record(self.path)
        if (
            record["token"] != self.token
            or record["run_id"] != self.run_id
            or record["card_id"] != self.card_id
        ):
            raise WorkspacePolicyError("writer lock ownership changed")

    def release(self) -> None:
        if self.released:
            return
        self.assert_owned()
        try:
            self.path.unlink()
        except FileNotFoundError:
            raise WorkspacePolicyError("writer lock disappeared before release")
        self.released = True


@dataclass
class StageCard:
    id: str
    run_id: str
    stage: str
    parents: tuple[str, ...]
    role: str
    assignee: str
    allowed_paths: tuple[str, ...]
    prohibited_paths: tuple[str, ...]
    workspace_mode: str
    workspace: str
    idempotency_key: str
    revision: int = 1
    status: str = "pending"
    attempt: int = 0
    attempts: list[dict[str, Any]] = field(default_factory=list)
    gate_passed: bool = False
    gate_detail: str | None = None
    blocking_reason: str | None = None
    output: dict[str, Any] = field(default_factory=dict)
    lease_token: str | None = None
    required_context: dict[str, Any] = field(default_factory=dict)
    lease_owner_pid: int | None = None
    lease_started_at: int | None = None
    lease_expires_at: int | None = None
    fencing_token: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "run_id": self.run_id,
            "stage": self.stage,
            "parents": list(self.parents),
            "role": self.role,
            "assignee": self.assignee,
            "allowed_paths": list(self.allowed_paths),
            "prohibited_paths": list(self.prohibited_paths),
            "workspace_mode": self.workspace_mode,
            "workspace": self.workspace,
            "idempotency_key": self.idempotency_key,
            "revision": self.revision,
            "status": self.status,
            "attempt": self.attempt,
            "attempts": self.attempts,
            "gate_passed": self.gate_passed,
            "gate_detail": self.gate_detail,
            "blocking_reason": self.blocking_reason,
            "output": self.output,
            "lease_token": self.lease_token,
            "required_context": self.required_context,
            "lease_owner_pid": self.lease_owner_pid,
            "lease_started_at": self.lease_started_at,
            "lease_expires_at": self.lease_expires_at,
            "fencing_token": self.fencing_token,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "StageCard":
        if not isinstance(value, Mapping):
            raise PlanningKanbanError("kanban card is not an object")
        missing = _CARD_FIELDS.difference(value)
        unknown = set(value).difference(_CARD_FIELDS)
        if missing or unknown:
            detail = ", ".join(
                part
                for part in (
                    f"missing={sorted(missing)}" if missing else "",
                    f"unknown={sorted(unknown)}" if unknown else "",
                )
                if part
            )
            raise PlanningKanbanError(f"kanban card schema fields are invalid ({detail})")

        def string(name: str) -> str:
            result = value[name]
            if not isinstance(result, str) or not result:
                raise PlanningKanbanError(f"kanban card field {name} is invalid")
            return result

        def strings(name: str) -> tuple[str, ...]:
            result = value[name]
            if not isinstance(result, list) or not all(
                isinstance(item, str) and item for item in result
            ):
                raise PlanningKanbanError(f"kanban card field {name} is invalid")
            return tuple(result)

        revision = value["revision"]
        status = value["status"]
        attempt = value["attempt"]
        attempts = value["attempts"]
        gate_passed = value["gate_passed"]
        gate_detail = value["gate_detail"]
        blocking_reason = value["blocking_reason"]
        output = value["output"]
        lease_token = value["lease_token"]
        required_context = value["required_context"]
        lease_owner_pid = value["lease_owner_pid"]
        lease_started_at = value["lease_started_at"]
        lease_expires_at = value["lease_expires_at"]
        fencing_token = value["fencing_token"]

        def valid_timestamp(item: Any) -> bool:
            return isinstance(item, int) and not isinstance(item, bool) and item > 0

        if (
            not isinstance(revision, int)
            or isinstance(revision, bool)
            or revision < 1
            or not isinstance(status, str)
            or status not in _STATUSES
            or not isinstance(attempt, int)
            or isinstance(attempt, bool)
            or attempt < 0
            or not isinstance(attempts, list)
            or not all(isinstance(item, Mapping) for item in attempts)
            or not isinstance(gate_passed, bool)
            or (gate_detail is not None and (not isinstance(gate_detail, str) or not gate_detail))
            or (blocking_reason is not None and (not isinstance(blocking_reason, str) or not blocking_reason))
            or not isinstance(output, dict)
            or (lease_token is not None and (not isinstance(lease_token, str) or not lease_token))
            or not isinstance(required_context, dict)
            or (lease_owner_pid is not None and not valid_timestamp(lease_owner_pid))
            or (lease_started_at is not None and not valid_timestamp(lease_started_at))
            or (lease_expires_at is not None and not valid_timestamp(lease_expires_at))
            or (
                lease_started_at is not None
                and lease_expires_at is not None
                and lease_expires_at < lease_started_at
            )
            or not isinstance(fencing_token, int)
            or isinstance(fencing_token, bool)
            or fencing_token < 0
        ):
            raise PlanningKanbanError("kanban card operational fields are invalid")
        lease_fields = (lease_token, lease_owner_pid, lease_started_at, lease_expires_at)
        if status == "running" and (
            any(item is None for item in lease_fields) or fencing_token < 1
        ):
            raise PlanningKanbanError("running card has incomplete ownership evidence")
        if status != "running" and any(item is not None for item in lease_fields):
            raise PlanningKanbanError("non-running card retains ownership evidence")
        _validate_attempts(
            attempts,
            attempt=attempt,
            status=status,
            output=output,
            required_context=required_context,
            blocking_reason=blocking_reason,
        )
        return cls(
            id=string("id"),
            run_id=string("run_id"),
            stage=string("stage"),
            parents=strings("parents"),
            role=string("role"),
            assignee=string("assignee"),
            allowed_paths=strings("allowed_paths"),
            prohibited_paths=strings("prohibited_paths"),
            workspace_mode=string("workspace_mode"),
            workspace=string("workspace"),
            idempotency_key=string("idempotency_key"),
            revision=revision,
            status=status,
            attempt=attempt,
            attempts=[dict(item) for item in attempts],
            gate_passed=gate_passed,
            gate_detail=gate_detail,
            blocking_reason=blocking_reason,
            output=dict(output),
            lease_token=lease_token,
            required_context=dict(required_context),
            lease_owner_pid=lease_owner_pid,
            lease_started_at=lease_started_at,
            lease_expires_at=lease_expires_at,
            fencing_token=fencing_token,
        )


@dataclass(frozen=True)
class _LeaseCapability:
    """Ephemeral authority for one claim in one PlanningRun instance."""

    instance_id: str
    worker: str
    card_id: str
    revision: int
    attempt: int
    lease_token: str
    fencing_token: int


@dataclass
class PlanningRun:
    root: Path
    run_id: str
    cards: list[StageCard]
    contract_sha256: str
    generation: int = 1
    _coordinator_token: str | None = field(default=None, repr=False, compare=False)
    _writer_lock: _ExclusiveLock | None = field(default=None, repr=False, compare=False)
    _instance_id: str = field(default_factory=lambda: secrets.token_hex(24), repr=False, compare=False)
    _lease_capabilities: dict[str, _LeaseCapability] = field(
        default_factory=dict, repr=False, compare=False
    )
    _gate_verifier: AuthoritativeGateVerifier = field(
        default_factory=_DenyAllGateVerifier, repr=False, compare=False
    )
    _human_decision_verifier: HumanDecisionVerifier = field(
        default_factory=_DenyAllHumanDecisionVerifier, repr=False, compare=False
    )
    _fresh_review_verifier: FreshReviewVerifier = field(
        default_factory=_DenyAllFreshReviewVerifier, repr=False, compare=False
    )

    @property
    def path(self) -> Path:
        return _safe_state_path(self.root, self.run_id)

    def card(self, card_id: str) -> StageCard:
        for card in self.cards:
            if card.id == card_id:
                return card
        raise PlanningKanbanError(f"unknown card: {card_id}")

    def _payload(self) -> dict[str, Any]:
        payload = _state_payload(
            run_id=self.run_id,
            generation=self.generation,
            contract_sha256=self.contract_sha256,
            cards=self.cards,
        )
        payload["state_hmac_sha256"] = _state_authentication(payload)
        return payload

    def _save(self, *, expected_state: str | None = None, lock: _ExclusiveLock | None = None) -> None:
        if lock is not None:
            lock.assert_owned()
        if expected_state is not None:
            current = PlanningKanban.load(self.root, self.run_id)
            if _state_fingerprint(current) != expected_state:
                raise PlanningKanbanError("kanban state changed during mutation")
            self.generation = current.generation + 1
        elif self.generation < 1:
            raise PlanningKanbanError("kanban state generation is invalid")
        _validate_loaded_state(self.cards)
        _safe_state_path(self.root, self.run_id)
        _atomic_json(self.path, self._payload())
        _write_generation(self.root, self.run_id, self.generation)
        if lock is not None:
            lock.assert_owned()

    def reconcile(self) -> "PlanningRun":
        """Reload and validate the persisted projection before dispatch/handoff."""
        loaded = PlanningKanban.load(
            self.root,
            self.run_id,
            gate_verifier=self._gate_verifier,
            human_decision_verifier=self._human_decision_verifier,
            fresh_review_verifier=self._fresh_review_verifier,
        )
        if loaded.contract_sha256 != self.contract_sha256:
            raise PlanningKanbanError("kanban contract hash does not reconcile")
        return loaded

    def _adopt(self, loaded: "PlanningRun") -> None:
        self.cards = loaded.cards
        self.contract_sha256 = loaded.contract_sha256
        self.generation = loaded.generation

    def _owns_lease(self, card_id: str, card: StageCard) -> bool:
        capability = self._lease_capabilities.get(card_id)
        if capability is None or capability.instance_id != self._instance_id:
            return False
        if (
            card.status != "running"
            or capability.card_id != card_id
            or capability.revision != card.revision
            or capability.attempt != card.attempt
            or capability.lease_token != card.lease_token
            or capability.fencing_token != card.fencing_token
            or card.lease_expires_at is None
            or card.lease_expires_at <= _now_ms()
        ):
            return False
        claim = next(
            (
                event
                for event in reversed(card.attempts)
                if event.get("attempt") == capability.attempt
                and event.get("event") == "claimed"
            ),
            None,
        )
        return isinstance(claim, Mapping) and claim.get("worker") == capability.worker

    def _require_lease_capability(self, card_id: str, card: StageCard) -> None:
        if not self._owns_lease(card_id, card):
            raise StageBlocked("stale card ownership or attempt capability; reconcile before mutating")

    def _require_coordinator(self) -> None:
        if self._coordinator_token is None:
            raise StageBlocked("non-running mutation requires coordinator instance authority")

    @contextmanager
    def _mutation(
        self,
        card_id: str,
        *,
        require_owner: bool = False,
        require_running_owner: bool = False,
        require_coordinator: bool = False,
        recovery: bool = False,
    ) -> Iterator[tuple["PlanningRun", StageCard, str, _ExclusiveLock | None]]:
        if require_coordinator:
            self._require_coordinator()
        local = self.card(card_id)
        probe = PlanningKanban.load(self.root, self.run_id)
        persisted = probe.card(card_id)
        if require_coordinator and self.generation != probe.generation:
            raise StageBlocked("stale coordinator instance; reconcile before mutating")
        writer_needed = persisted.workspace_mode == "dir" and persisted.stage in _WRITERS
        if (
            self._writer_lock is not None
            and self._writer_lock.card_id == card_id
            and not writer_needed
        ):
            raise WorkspacePolicyError("persisted workspace policy changed under a writer lease")
        if not recovery and (require_owner or (require_running_owner and persisted.status == "running")):
            if persisted.status == "running":
                self._require_lease_capability(card_id, persisted)
            elif require_owner and local.lease_token != persisted.lease_token:
                raise StageBlocked("stale card ownership or attempt; reconcile before mutating")
        writer_lock = (
            self._writer_lock
            if writer_needed and self._writer_lock is not None and self._writer_lock.card_id == card_id
            else None
        )
        acquired_writer = False
        if writer_lock is not None:
            writer_lock.assert_owned()
        elif writer_needed:
            writer_lock = _ExclusiveLock.acquire(
                _writer_lock_path(self.root),
                run_id=self.run_id,
                card_id=card_id,
            )
            acquired_writer = True
        state_lock: _ExclusiveLock | None = None
        try:
            state_lock = _ExclusiveLock.acquire(
                _safe_run(self.root, self.run_id) / ".kanban-state.lock",
                run_id=self.run_id,
                card_id=card_id,
            )
            loaded = PlanningKanban.load(self.root, self.run_id)
            current = loaded.card(card_id)
            current_needs_writer = current.workspace_mode == "dir" and current.stage in _WRITERS
            if current_needs_writer != writer_needed:
                raise WorkspacePolicyError("workspace policy changed during mutation")
            if recovery:
                if current.status != "running":
                    raise StageBlocked("only running cards can be recovered")
                _validate_recovery_candidate(current)
            elif require_owner or (require_running_owner and current.status == "running"):
                if current.status == "running":
                    self._require_lease_capability(card_id, current)
                elif require_owner and local.lease_token != current.lease_token:
                    raise StageBlocked("stale card ownership or attempt; reconcile before mutating")
            before = _state_fingerprint(loaded)
            yield loaded, current, before, writer_lock
        finally:
            if state_lock is not None:
                state_lock.release()
            if acquired_writer and self._writer_lock is not writer_lock:
                if writer_lock is not None:
                    writer_lock.release()

    @staticmethod
    def _parents_ready(cards: list[StageCard], card: StageCard) -> None:
        for parent_id in card.parents:
            parent = next((item for item in cards if item.id == parent_id), None)
            if parent is None or parent.status != "complete" or not _card_has_valid_gate(parent):
                raise StageBlocked(
                    f"parent {parent_id} is incomplete or lacks valid Coherence gate evidence"
                )

    def claim(self, card_id: str, *, worker: str) -> StageCard:
        if not isinstance(worker, str) or not worker.strip():
            raise PlanningKanbanError("worker must be a non-empty string")
        with self._mutation(card_id) as (loaded, card, before, writer_lock):
            if worker != card.assignee:
                raise StageBlocked("worker is not authorized for the card assignee")
            self._parents_ready(loaded.cards, card)
            if card.status not in {"pending", "ready"}:
                raise StageBlocked(f"card {card_id} is {card.status}")
            card.attempt += 1
            card.status = "running"
            card.fencing_token += 1
            lease_token = writer_lock.token if writer_lock is not None else secrets.token_hex(24)
            card.lease_token = lease_token
            card.lease_owner_pid = os.getpid()
            card.lease_started_at = _now_ms()
            card.lease_expires_at = card.lease_started_at + _LEASE_TTL_MS
            card.attempts.append(
                {"attempt": card.attempt, "worker": worker, "event": "claimed"}
            )
            capability = _LeaseCapability(
                instance_id=self._instance_id,
                worker=worker,
                card_id=card_id,
                revision=card.revision,
                attempt=card.attempt,
                lease_token=lease_token,
                fencing_token=card.fencing_token,
            )
            loaded._save(expected_state=before, lock=writer_lock)
            if writer_lock is not None:
                self._writer_lock = writer_lock
            self._adopt(loaded)
            self._lease_capabilities[card_id] = capability
            return self.card(card_id)

    def heartbeat(self, card_id: str) -> StageCard:
        with self._mutation(card_id, require_owner=True) as (loaded, card, before, writer_lock):
            if card.status != "running":
                raise StageBlocked("heartbeat requires a running card")
            card.lease_expires_at = _now_ms() + _LEASE_TTL_MS
            card.attempts.append({"attempt": card.attempt, "event": "heartbeat"})
            loaded._save(expected_state=before, lock=writer_lock)
            self._adopt(loaded)
            return self.card(card_id)

    def complete(self, card_id: str, *, evidence: Mapping[str, Any]) -> StageCard:
        gate = _validated_completion_gate(evidence)
        with self._mutation(card_id, require_owner=True) as (loaded, card, before, writer_lock):
            if card.status != "running":
                raise StageBlocked("completion requires a claimed card")
            verified_gate = self._gate_verifier.verify_gate(card=card, gate=gate)
            if verified_gate is None:
                raise StageBlocked("completion requires authoritative Coherence gate verification")
            gate = _validated_gate_mapping(verified_gate)
            card.output = _json_copy(evidence, what="completion evidence")
            card.output["gate"] = gate
            card.status = "complete"
            card.gate_passed = True
            card.gate_detail = json.dumps(gate, sort_keys=True, separators=(",", ":"))
            card.lease_token = None
            card.lease_owner_pid = None
            card.lease_started_at = None
            card.lease_expires_at = None
            card.attempts.append(
                {"attempt": card.attempt, "event": "completed", "evidence": card.output}
            )
            for child in loaded.cards:
                if card.id in child.parents and child.status == "pending":
                    child.status = "ready"
            loaded._save(expected_state=before, lock=writer_lock)
            if writer_lock is not None:
                writer_lock.release()
                if self._writer_lock is writer_lock:
                    self._writer_lock = None
            self._adopt(loaded)
            self._lease_capabilities.pop(card_id, None)
            return self.card(card_id)

    def mark_gate(self, card_id: str, *, passed: bool, detail: Any) -> StageCard:
        if passed:
            if not isinstance(detail, Mapping):
                raise StageBlocked("a passing gate requires structured Coherence evidence")
            _validated_gate_mapping(detail)
        with self._mutation(
            card_id,
            require_owner=True,
            require_coordinator=self.card(card_id).status != "running",
        ) as (loaded, card, before, writer_lock):
            release_writer = False
            revoked_descendants: set[str] = set()
            if passed:
                if card.status != "complete":
                    raise StageBlocked("a gate cannot pass an incomplete card")
                verified_gate = self._gate_verifier.verify_gate(card=card, gate=detail)
                if verified_gate is None:
                    raise StageBlocked("passing gate requires authoritative Coherence gate verification")
                detail = _validated_gate_mapping(verified_gate)
                if not _same_json(card.output.get("gate"), dict(detail)):
                    raise StageBlocked("passing gate evidence does not match completion evidence")
                card.gate_passed = True
                card.gate_detail = json.dumps(dict(detail), sort_keys=True, separators=(",", ":"))
            else:
                release_writer = card.status == "running"
                card.gate_passed = False
                card.gate_detail = str(detail)
                card.status = "blocked"
                card.blocking_reason = str(detail)
                card.required_context = {}
                card.lease_token = None
                card.lease_owner_pid = None
                card.lease_started_at = None
                card.lease_expires_at = None
                card.attempts.append(
                    {"attempt": card.attempt, "event": "gate_revoked", "reason": str(detail)}
                )
                revoked_descendants = _revoke_descendants(
                    loaded.cards,
                    card.id,
                    reason=f"ancestor {card.id} gate evidence is no longer valid",
                )
            loaded._save(expected_state=before, lock=writer_lock)
            if not passed and release_writer and writer_lock is not None:
                writer_lock.release()
                if self._writer_lock is writer_lock:
                    self._writer_lock = None
            if not passed and self._writer_lock is not None:
                if self._writer_lock.card_id in revoked_descendants:
                    self._writer_lock.release()
                    self._writer_lock = None
            self._adopt(loaded)
            if not passed and release_writer:
                self._lease_capabilities.pop(card_id, None)
            for descendant_id in revoked_descendants:
                self._lease_capabilities.pop(descendant_id, None)
            return self.card(card_id)

    def block(
        self,
        card_id: str,
        *,
        reason: str,
        needs_input: bool = False,
        evidence: Mapping[str, Any] | None = None,
    ) -> StageCard:
        if not isinstance(reason, str) or not reason.strip():
            raise PlanningKanbanError("blocking reason must be non-empty")
        if needs_input and evidence is None:
            raise StageBlocked("needs_input requires current inputs and finding scope")
        if evidence is not None:
            context = _validated_context(evidence)
            block_evidence = _json_copy(evidence, what="blocking evidence")
        else:
            context = {}
            block_evidence = {}
        with self._mutation(
            card_id,
            require_running_owner=True,
            require_coordinator=self.card(card_id).status != "running",
        ) as (loaded, card, before, writer_lock):
            if card.status in {"complete", "blocked"}:
                raise StageBlocked(f"card {card_id} is {card.status}")
            card.status = "needs_input" if needs_input else "blocked"
            card.blocking_reason = reason
            card.required_context = context if needs_input else {}
            card.output = {"block": block_evidence}
            card.attempts.append(
                {
                    "attempt": card.attempt,
                    "event": "blocked",
                    "reason": reason,
                    "needs_input": needs_input,
                    "evidence": block_evidence,
                }
            )
            card.lease_token = None
            card.lease_owner_pid = None
            card.lease_started_at = None
            card.lease_expires_at = None
            loaded._save(expected_state=before, lock=writer_lock)
            if writer_lock is not None:
                writer_lock.release()
                if self._writer_lock is writer_lock:
                    self._writer_lock = None
            self._adopt(loaded)
            self._lease_capabilities.pop(card_id, None)
            return self.card(card_id)

    def resume(self, card_id: str, *, evidence: Mapping[str, Any] | None = None) -> StageCard:
        with self._mutation(card_id, require_coordinator=True) as (
            loaded,
            card,
            before,
            writer_lock,
        ):
            if card.status != "needs_input":
                raise StageBlocked("only needs_input cards can be resumed")
            if evidence is None:
                raise StageBlocked("resume requires current human-decision and fresh-review evidence")
            validated = _validated_resume_evidence(evidence, card.required_context)
            context = _validated_context(card.required_context)
            verified_decision = self._human_decision_verifier.verify_human_decision(
                card=card,
                decision=validated["human_decision"],
                context=context,
            )
            verified_review = self._fresh_review_verifier.verify_fresh_review(
                card=card,
                review=validated["fresh_review"],
                context=context,
            )
            if verified_decision is None or verified_review is None:
                raise StageBlocked("resume requires authoritative decision and review verification")
            verified_decision = _json_copy(verified_decision, what="verified human decision")
            verified_review = _json_copy(verified_review, what="verified fresh review")
            card.status, card.blocking_reason = "ready", None
            card.required_context = {}
            card.output["resume"] = {
                "human_decision": verified_decision,
                "fresh_review": verified_review,
            }
            card.attempts.append(
                {"attempt": card.attempt, "event": "resumed", "evidence": card.output["resume"]}
            )
            loaded._save(expected_state=before, lock=writer_lock)
            self._adopt(loaded)
            return self.card(card_id)

    def reclaim(
        self,
        card_id: str,
        *,
        reason: str,
        recovery: bool = False,
        revision: int | None = None,
        attempt: int | None = None,
    ) -> StageCard:
        if not isinstance(reason, str) or not reason.strip():
            raise PlanningKanbanError("reclaim reason must be non-empty")
        with self._mutation(
            card_id,
            require_owner=not recovery,
            recovery=recovery,
        ) as (loaded, card, before, writer_lock):
            if card.status != "running":
                raise StageBlocked("only running cards can be reclaimed")
            if revision is not None and revision != card.revision:
                raise StageBlocked("recovery revision does not match the running card")
            if attempt is not None and attempt != card.attempt:
                raise StageBlocked("recovery attempt does not match the running card")
            prior_fencing_token = card.fencing_token
            card.fencing_token += 1
            card.status = "ready"
            card.attempts.append(
                {
                    "attempt": card.attempt,
                    "event": "crash_reclaim" if recovery else "reclaimed",
                    "reason": reason,
                    "revision": card.revision,
                    "fencing_token": card.fencing_token,
                    "previous_fencing_token": prior_fencing_token,
                }
            )
            card.lease_token = None
            card.lease_owner_pid = None
            card.lease_started_at = None
            card.lease_expires_at = None
            loaded._save(expected_state=before, lock=writer_lock)
            if writer_lock is not None:
                writer_lock.release()
                if self._writer_lock is writer_lock:
                    self._writer_lock = None
            self._adopt(loaded)
            self._lease_capabilities.pop(card_id, None)
            return self.card(card_id)

    def recover(
        self,
        card_id: str,
        *,
        reason: str,
        revision: int | None = None,
        attempt: int | None = None,
    ) -> StageCard:
        """Reclaim a dead/expired lease from a fresh instance, same attempt."""
        return self.reclaim(
            card_id,
            reason=reason,
            recovery=True,
            revision=revision,
            attempt=attempt,
        )


class PlanningKanban:
    @staticmethod
    def materialize(
        root: Path,
        run_id: str,
        *,
        assignee: str = "planning-worker",
        workspace_mode: str = "dir",
        authorized_assignees: Collection[str] | None = None,
        gate_verifier: AuthoritativeGateVerifier | None = None,
        human_decision_verifier: HumanDecisionVerifier | None = None,
        fresh_review_verifier: FreshReviewVerifier | None = None,
    ) -> PlanningRun:
        if workspace_mode not in {"dir", "worktree"}:
            raise WorkspacePolicyError("workspace_mode must be dir or worktree")
        if not isinstance(assignee, str) or not assignee.strip():
            raise PlanningKanbanError("assignee must be a non-empty string")
        allowed_assignees = frozenset(
            {"planning-worker"} if authorized_assignees is None else authorized_assignees
        )
        if not allowed_assignees or any(
            not isinstance(item, str) or not item.strip() for item in allowed_assignees
        ):
            raise PlanningKanbanError("authorized assignee allowlist is invalid")
        if assignee not in allowed_assignees:
            raise PlanningKanbanError("assignee is outside the authorized allowlist")
        run_path = _safe_run(root, run_id)
        run_path.mkdir(parents=True, exist_ok=True)
        if _safe_run(root, run_id) != run_path:
            raise PlanningKanbanError("planning run path changed during materialization")
        state_lock = _ExclusiveLock.acquire(
            run_path / ".kanban-state.lock",
            run_id=run_id,
            card_id=f"{run_id}:{PLANNING_ROOT_STAGE}:v1",
        )
        try:
            existing = run_path / "kanban-run.json"
            if existing.exists():
                return PlanningKanban.load(
                    root,
                    run_id,
                    gate_verifier=gate_verifier,
                    human_decision_verifier=human_decision_verifier,
                    fresh_review_verifier=fresh_review_verifier,
                )
            if _safe_run(root, run_id) != run_path:
                raise PlanningKanbanError("planning run path changed during materialization")
            cards = _canonical_cards(root, run_id, assignee, workspace_mode)
            contract = _sha({"run_id": run_id, "cards": [_contract_card(card) for card in cards]})
            result = PlanningRun(
                root=root.resolve(),
                run_id=run_id,
                cards=cards,
                contract_sha256=contract,
                generation=1,
                _coordinator_token=secrets.token_hex(24),
                _gate_verifier=gate_verifier or _DenyAllGateVerifier(),
                _human_decision_verifier=(
                    human_decision_verifier or _DenyAllHumanDecisionVerifier()
                ),
                _fresh_review_verifier=fresh_review_verifier or _DenyAllFreshReviewVerifier(),
            )
            result._save(lock=state_lock)
            return result
        finally:
            state_lock.release()

    @staticmethod
    def load(
        root: Path,
        run_id: str,
        *,
        gate_verifier: AuthoritativeGateVerifier | None = None,
        human_decision_verifier: HumanDecisionVerifier | None = None,
        fresh_review_verifier: FreshReviewVerifier | None = None,
    ) -> PlanningRun:
        path = _safe_state_path(root, run_id)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_strict_object)
        except (OSError, json.JSONDecodeError) as exc:
            raise PlanningKanbanError("kanban graph is unreadable") from exc
        if not isinstance(raw, Mapping):
            raise PlanningKanbanError("kanban graph is not an object")
        missing = _STATE_FIELDS.difference(raw)
        unknown = set(raw).difference(_STATE_FIELDS)
        if missing or unknown:
            detail = ", ".join(
                part
                for part in (
                    f"missing={sorted(missing)}" if missing else "",
                    f"unknown={sorted(unknown)}" if unknown else "",
                )
                if part
            )
            raise PlanningKanbanError(f"kanban state schema fields are invalid ({detail})")
        if raw["schema"] != _STATE_SCHEMA or raw["run_id"] != run_id:
            # Schema-one state used the same-file state_sha256 digest and is
            # intentionally not migrated: accepting it would reintroduce an
            # unauthenticated state format.  A future migration must be
            # atomic and must authenticate before publishing schema two.
            raise PlanningKanbanError("kanban graph header is invalid")
        generation = raw["generation"]
        if not isinstance(generation, int) or isinstance(generation, bool) or generation < 1:
            raise PlanningKanbanError("kanban graph generation is invalid")
        cards_raw = raw["cards"]
        if not isinstance(cards_raw, list):
            raise PlanningKanbanError("kanban graph cards field is invalid")
        cards = [StageCard.from_dict(item) for item in cards_raw]
        state_auth = raw["state_hmac_sha256"]
        contract = raw["contract_sha256"]
        if not isinstance(state_auth, str) or not _HEX_SHA256.fullmatch(state_auth):
            raise PlanningKanbanError("kanban state authentication is invalid")
        if not isinstance(contract, str) or not _HEX_SHA256.fullmatch(contract):
            raise PlanningKanbanError("kanban contract hash is invalid")
        if len(cards) != len(_CANONICAL_STAGES) or [card.stage for card in cards] != list(
            _CANONICAL_STAGES
        ):
            raise PlanningKanbanError("kanban graph does not match the planning lifecycle")
        if len({card.id for card in cards}) != len(cards):
            raise PlanningKanbanError("kanban graph has duplicate card IDs")
        if sum(card.stage == PLANNING_ROOT_STAGE for card in cards) != 1:
            raise PlanningKanbanError("kanban graph must have exactly one root card")
        if any(card.run_id != run_id for card in cards):
            raise PlanningKanbanError("kanban graph contains a foreign run")
        if any(card.status not in _STATUSES for card in cards):
            raise PlanningKanbanError("kanban graph contains an invalid status")
        expected_edges = [
            [cards[index - 1].id, cards[index].id] for index in range(1, len(cards))
        ]
        if raw.get("edges") != expected_edges:
            raise PlanningKanbanError("kanban graph edges do not reconcile")
        for index, card in enumerate(cards):
            expected_parents = () if index == 0 else (cards[index - 1].id,)
            if card.parents != expected_parents:
                raise PlanningKanbanError("kanban graph has an invalid parent edge")
        if any(card.id in card.parents for card in cards):
            raise PlanningKanbanError("kanban graph is cyclic")
        if any(card.workspace_mode not in {"dir", "worktree"} for card in cards):
            raise PlanningKanbanError("kanban graph has an invalid workspace mode")
        if len({card.assignee for card in cards}) != 1:
            raise PlanningKanbanError("kanban graph has inconsistent assignees")
        expected_cards = _canonical_cards(root, run_id, cards[0].assignee, cards[0].workspace_mode)
        if any(_contract_card(actual) != _contract_card(expected) for actual, expected in zip(cards, expected_cards)):
            raise PlanningKanbanError("kanban card contract does not reconcile")
        expected_contract = _sha(
            {"run_id": run_id, "cards": [_contract_card(card) for card in cards]}
        )
        if contract != expected_contract:
            raise PlanningKanbanError("kanban contract hash is invalid")
        expected_state_auth = _state_authentication(
            _state_payload(
                run_id=run_id,
                generation=generation,
                contract_sha256=contract,
                cards=cards,
            )
        )
        if not hmac.compare_digest(state_auth, expected_state_auth):
            raise PlanningKanbanError("kanban state authentication does not reconcile")
        high_water = _read_generation(root, run_id)
        if generation != high_water:
            raise PlanningKanbanError(
                "kanban state replay or generation high-water fence violation"
            )
        _validate_loaded_state(cards)
        return PlanningRun(
            root=root.resolve(),
            run_id=run_id,
            cards=cards,
            contract_sha256=contract,
            generation=generation,
            _gate_verifier=gate_verifier or _DenyAllGateVerifier(),
            _human_decision_verifier=(
                human_decision_verifier or _DenyAllHumanDecisionVerifier()
            ),
            _fresh_review_verifier=fresh_review_verifier or _DenyAllFreshReviewVerifier(),
        )

    @staticmethod
    def resume(
        root: Path,
        run_id: str,
        *,
        gate_verifier: AuthoritativeGateVerifier | None = None,
        human_decision_verifier: HumanDecisionVerifier | None = None,
        fresh_review_verifier: FreshReviewVerifier | None = None,
    ) -> PlanningRun:
        return PlanningKanban.load(
            root,
            run_id,
            gate_verifier=gate_verifier,
            human_decision_verifier=human_decision_verifier,
            fresh_review_verifier=fresh_review_verifier,
        )


def _canonical_cards(root: Path, run_id: str, assignee: str, workspace_mode: str) -> list[StageCard]:
    safe = safe_root(root)
    if safe is None:
        raise PlanningKanbanError("project root is unsafe")
    workspace = str(safe) if workspace_mode == "dir" else f"worktree:{run_id}"
    prohibited = (".env", ".git", "implementation", "FEAT-018", "FEAT-019", "FEAT-020")
    cards: list[StageCard] = []
    for index, stage in enumerate(_CANONICAL_STAGES):
        if stage == PLANNING_ROOT_STAGE:
            allowed = (f".factory/planning/{run_id}",)
        else:
            allowed = {
                "capture": (".intent", f".factory/planning/{run_id}/capture"),
                "provisional-spec-authoring": (
                    "docs/superpowers/specs",
                    f".factory/planning/{run_id}",
                ),
                "implementation-plan-authoring": (
                    "docs/superpowers/plans",
                    f".factory/planning/{run_id}",
                ),
                "task-materialization": ("tasks", f".factory/planning/{run_id}"),
            }.get(stage, (f".factory/planning/{run_id}",))
        parents = () if not cards else (cards[-1].id,)
        cards.append(
            StageCard(
                id=f"{run_id}:{stage}:v1",
                run_id=run_id,
                stage=stage,
                parents=parents,
                role="coordinator" if stage == PLANNING_ROOT_STAGE else "planning-worker",
                assignee=assignee,
                allowed_paths=allowed,
                prohibited_paths=prohibited,
                workspace_mode=workspace_mode,
                workspace=workspace,
                idempotency_key=f"feat17/{run_id}/{stage}/v1",
            )
        )
    return cards


def _state_payload(
    *, run_id: str, generation: int, contract_sha256: str, cards: list[StageCard]
) -> dict[str, Any]:
    return {
        "schema": _STATE_SCHEMA,
        "run_id": run_id,
        "generation": generation,
        "contract_sha256": contract_sha256,
        "cards": [card.to_dict() for card in cards],
        "edges": [[card.parents[0], card.id] for card in cards if card.parents],
    }


def _state_fingerprint(run: PlanningRun) -> str:
    return _sha(
        _state_payload(
            run_id=run.run_id,
            generation=run.generation,
            contract_sha256=run.contract_sha256,
            cards=run.cards,
        )
    )


def _validate_attempts(
    attempts: list[Any],
    *,
    attempt: int,
    status: str,
    output: dict[str, Any],
    required_context: dict[str, Any],
    blocking_reason: str | None,
) -> None:
    if not attempts:
        if attempt != 0 or status not in {"pending", "ready"}:
            raise PlanningKanbanError("card attempt state is inconsistent with its event history")
        return
    highest_attempt = 0
    claimed_attempts: set[int] = set()
    last_event: str | None = None
    for event in attempts:
        if not isinstance(event, dict):
            raise PlanningKanbanError("attempt entries must be strict objects")
        event_name = event.get("event")
        if not isinstance(event_name, str) or event_name not in _ATTEMPT_EVENTS:
            raise PlanningKanbanError("attempt event kind is invalid")
        if set(event) != _ATTEMPT_FIELDS[event_name]:
            raise PlanningKanbanError("attempt event schema fields are invalid")
        event_attempt = event.get("attempt")
        minimum_attempt = (
            0 if event_name in {"blocked", "gate_revoked", "resumed"} and attempt == 0 else 1
        )
        if (
            not isinstance(event_attempt, int)
            or isinstance(event_attempt, bool)
            or event_attempt < minimum_attempt
            or event_attempt > attempt
            or event_attempt < highest_attempt
        ):
            raise PlanningKanbanError("attempt event number is invalid")
        if event_name == "claimed":
            worker = event.get("worker")
            if not isinstance(worker, str) or not worker.strip():
                raise PlanningKanbanError("claimed attempt worker is invalid")
            if event_attempt != highest_attempt + 1:
                raise PlanningKanbanError("claimed attempt sequence is invalid")
            highest_attempt = event_attempt
            claimed_attempts.add(event_attempt)
        elif event_attempt not in claimed_attempts and event_attempt != 0:
            raise PlanningKanbanError("attempt event has no preceding claim")
        if event_name == "heartbeat":
            pass
        elif event_name == "completed":
            if not isinstance(event["evidence"], dict):
                raise PlanningKanbanError("completed attempt evidence is invalid")
            _validated_completion_gate(event["evidence"])
        elif event_name == "blocked":
            if (
                not isinstance(event["reason"], str)
                or not event["reason"].strip()
                or not isinstance(event["needs_input"], bool)
                or not isinstance(event["evidence"], dict)
            ):
                raise PlanningKanbanError("blocked attempt evidence is invalid")
            if event["needs_input"]:
                _validated_context(event["evidence"])
        elif event_name == "resumed":
            if not isinstance(event["evidence"], dict):
                raise PlanningKanbanError("resumed attempt evidence is invalid")
        elif event_name in {"reclaimed", "crash_reclaim"}:
            if (
                not isinstance(event["reason"], str)
                or not event["reason"].strip()
                or not isinstance(event["revision"], int)
                or isinstance(event["revision"], bool)
                or event["revision"] < 1
                or not isinstance(event["fencing_token"], int)
                or isinstance(event["fencing_token"], bool)
                or not isinstance(event["previous_fencing_token"], int)
                or isinstance(event["previous_fencing_token"], bool)
                or event["fencing_token"] != event["previous_fencing_token"] + 1
            ):
                raise PlanningKanbanError("reclaim attempt evidence is invalid")
        elif event_name == "gate_revoked":
            if not isinstance(event["reason"], str) or not event["reason"].strip():
                raise PlanningKanbanError("gate revocation attempt evidence is invalid")
        last_event = event_name
    if highest_attempt != attempt:
        raise PlanningKanbanError("card attempt does not reconcile with its event history")
    if status == "running" and last_event not in {"claimed", "heartbeat"}:
        raise PlanningKanbanError("running card has an invalid final attempt event")
    if status == "complete":
        if last_event != "completed" or not _same_json(attempts[-1]["evidence"], output):
            raise PlanningKanbanError("complete card has an invalid final attempt event")
    if status == "needs_input" and not (
        last_event == "blocked"
        and attempts[-1].get("needs_input") is True
        and _same_json(attempts[-1]["evidence"], required_context)
        and attempts[-1].get("reason") == blocking_reason
    ):
        raise PlanningKanbanError("needs_input card has an invalid final attempt event")
    if status == "blocked":
        if last_event not in {"blocked", "gate_revoked"}:
            raise PlanningKanbanError("blocked card has an invalid final attempt event")
        if attempts[-1].get("reason") != blocking_reason:
            raise PlanningKanbanError("blocked card reason does not reconcile with its event")
    if status == "ready" and last_event not in {"reclaimed", "crash_reclaim", "resumed"}:
        raise PlanningKanbanError("ready card has an invalid final attempt event")
    if status == "pending":
        raise PlanningKanbanError("pending card cannot retain attempt events")


def _validated_gate_mapping(gate: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(gate, Mapping) or not gate:
        raise StageBlocked("completion requires structured Coherence gate evidence")
    if gate.get("kind") != "coherence" or gate.get("passed") is not True:
        raise StageBlocked("completion requires an explicitly passing Coherence gate")
    if "name" in gate and (not isinstance(gate["name"], str) or not gate["name"].strip()):
        raise StageBlocked("Coherence gate name must be non-empty")
    evidence = gate.get("evidence")
    if not isinstance(evidence, Mapping) or not evidence:
        raise StageBlocked("Coherence gate evidence must be a non-empty object")
    return _json_copy(gate, what="Coherence gate evidence")


def _revoke_descendants(cards: list[StageCard], ancestor_id: str, *, reason: str) -> set[str]:
    descendants: set[str] = set()
    changed = True
    while changed:
        changed = False
        for candidate in cards:
            if candidate.id in descendants:
                continue
            if ancestor_id in candidate.parents or any(
                parent_id in descendants for parent_id in candidate.parents
            ):
                descendants.add(candidate.id)
                changed = True
    for candidate in cards:
        if candidate.id not in descendants:
            continue
        candidate.status = "blocked"
        candidate.gate_passed = False
        candidate.gate_detail = reason
        candidate.blocking_reason = reason
        candidate.required_context = {}
        candidate.attempts.append(
            {"attempt": candidate.attempt, "event": "gate_revoked", "reason": reason}
        )
        candidate.lease_token = None
        candidate.lease_owner_pid = None
        candidate.lease_started_at = None
        candidate.lease_expires_at = None
    return descendants


def _validated_completion_gate(evidence: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(evidence, Mapping) or not evidence:
        raise StageBlocked("completion requires structured Coherence gate evidence")
    gate = evidence.get("gate")
    if not isinstance(gate, Mapping):
        raise StageBlocked("completion requires structured Coherence gate evidence")
    return _validated_gate_mapping(gate)


def _card_has_valid_gate(card: StageCard) -> bool:
    if card.status != "complete" or card.gate_passed is not True:
        return False
    try:
        _validated_completion_gate(card.output)
    except PlanningKanbanError:
        return False
    return True


def _validated_context(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise StageBlocked("human-decision evidence requires current inputs and finding scope")
    inputs = value.get("inputs")
    finding_scope = value.get("finding_scope")
    if not isinstance(inputs, Mapping) or not inputs:
        raise StageBlocked("current inputs are required for human resume")
    if (
        not isinstance(finding_scope, (list, tuple))
        or not finding_scope
        or not all(isinstance(item, str) and item for item in finding_scope)
    ):
        raise StageBlocked("current finding scope is required for human resume")
    return _json_copy(
        {"inputs": inputs, "finding_scope": list(finding_scope)},
        what="resume context",
    )


def _same_json(left: Any, right: Any) -> bool:
    return json.dumps(left, sort_keys=True, separators=(",", ":"), ensure_ascii=False) == json.dumps(
        right, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def _validated_resume_evidence(
    evidence: Mapping[str, Any], required_context: Mapping[str, Any]
) -> dict[str, Any]:
    if not required_context:
        raise StageBlocked("resume requires current blocking inputs and finding scope")
    context = _validated_context(required_context)
    if not isinstance(evidence, Mapping):
        raise StageBlocked("resume requires human-decision and fresh-review evidence")
    decision = evidence.get("human_decision")
    review = evidence.get("fresh_review")
    if not isinstance(decision, Mapping) or not isinstance(review, Mapping):
        raise StageBlocked("resume requires human-decision and fresh-review evidence")
    if decision.get("decision") not in {"answer", "revise"} or not isinstance(
        decision.get("response"), str
    ) or not decision["response"].strip():
        raise StageBlocked("human decision evidence is invalid")
    decision_context = _validated_context(decision)
    review_context = _validated_context(review)
    if not _same_json(decision_context, context) or not _same_json(review_context, context):
        raise StageBlocked("resume evidence is not current for the blocked finding scope")
    _validated_gate_mapping(review)
    return _json_copy(evidence, what="resume evidence")


def _validate_recovery_candidate(card: StageCard) -> None:
    """Require durable dead/expired evidence before a fresh-instance reclaim."""
    if card.revision < 1 or card.attempt < 1 or card.fencing_token < 1:
        raise StageBlocked("running card lacks a valid revision, attempt, or fencing token")
    claim = next(
        (
            event
            for event in reversed(card.attempts)
            if event.get("event") == "claimed" and event.get("attempt") == card.attempt
        ),
        None,
    )
    if not isinstance(claim, Mapping):
        raise StageBlocked("running card lacks claim evidence for recovery")
    now = _now_ms()
    expired = card.lease_expires_at is not None and card.lease_expires_at <= now
    dead = card.lease_owner_pid is not None and not _pid_is_alive(card.lease_owner_pid)
    if not (dead or expired):
        raise StageBlocked("running card owner is still live and its lease has not expired")


def _validate_loaded_state(cards: list[StageCard]) -> None:
    for card in cards:
        _validate_attempts(
            card.attempts,
            attempt=card.attempt,
            status=card.status,
            output=card.output,
            required_context=card.required_context,
            blocking_reason=card.blocking_reason,
        )
        if card.status == "running" and not card.lease_token:
            raise PlanningKanbanError("running card has no ownership lease")
        if card.status != "running" and card.lease_token is not None:
            raise PlanningKanbanError("non-running card retains an ownership lease")
        if card.status == "complete":
            if not _card_has_valid_gate(card):
                raise PlanningKanbanError("complete card lacks valid Coherence gate evidence")
            expected_detail = json.dumps(
                card.output["gate"], sort_keys=True, separators=(",", ":")
            )
            if card.gate_detail != expected_detail:
                raise PlanningKanbanError("complete card gate detail does not reconcile")
            if card.attempt < 1 or not card.attempts or card.attempts[-1].get("event") != "completed":
                raise PlanningKanbanError("complete card lacks a completion attempt record")
        elif card.gate_passed:
            raise PlanningKanbanError("non-complete card cannot have a passed gate")
        if card.status == "needs_input":
            if not card.blocking_reason or not card.required_context:
                raise PlanningKanbanError("needs_input card lacks current blocking context")
            _validated_context(card.required_context)
        elif card.required_context:
            raise PlanningKanbanError("non-blocked card retains human blocking context")
        if card.status == "blocked" and not card.blocking_reason:
            raise PlanningKanbanError("blocked card lacks a blocking reason")
    for index, card in enumerate(cards[1:], start=1):
        parent = cards[index - 1]
        if card.status == "ready" and not _card_has_valid_gate(parent):
            raise PlanningKanbanError("ready card has a parent without valid gate evidence")


def materialize_planning_graph(root: Path, run_id: str, **kwargs: Any) -> PlanningRun:
    """Functional entry point for thin host adapters."""
    return PlanningKanban.materialize(root, run_id, **kwargs)


def load_planning_run(root: Path, run_id: str) -> PlanningRun:
    return PlanningKanban.load(root, run_id)


__all__ = [
    "AuthoritativeGateVerifier",
    "FreshReviewVerifier",
    "HumanDecisionVerifier",
    "PLANNING_ROOT_STAGE",
    "PLANNING_STAGES",
    "PlanningKanban",
    "PlanningRun",
    "PlanningKanbanError",
    "StageBlocked",
    "StageCard",
    "WorkspacePolicyError",
    "materialize_planning_graph",
    "load_planning_run",
]
