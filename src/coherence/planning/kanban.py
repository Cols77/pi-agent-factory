"""Fail-closed durable transport projection for the FEAT-017 planning lifecycle.

This module stores operational state only.  Coherence artifacts and validation
outputs remain the semantic source of truth; this local projection never
schedules downstream work or claims an external Hermes Kanban integration.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Mapping

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


class PlanningKanbanError(ValueError):
    """Raised when the durable projection is invalid or cannot be reconciled."""


class StageBlocked(PlanningKanbanError):
    """Raised when a stage cannot safely make the requested transition."""


class WorkspacePolicyError(PlanningKanbanError):
    """Raised when workspace serialization or ownership cannot be proven."""


def _sha(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
    ).hexdigest()


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
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise WorkspacePolicyError("lock file is malformed; refusing recovery") from exc
    if not isinstance(value, dict):
        raise WorkspacePolicyError("lock file is malformed; refusing recovery")
    if (
        value.get("schema") != 1
        or not isinstance(value.get("pid"), int)
        or isinstance(value.get("pid"), bool)
        or not isinstance(value.get("run_id"), str)
        or not isinstance(value.get("card_id"), str)
        or not isinstance(value.get("token"), str)
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
    status: str = "pending"
    attempt: int = 0
    attempts: list[dict[str, Any]] = field(default_factory=list)
    gate_passed: bool = False
    gate_detail: str | None = None
    blocking_reason: str | None = None
    output: dict[str, Any] = field(default_factory=dict)
    lease_token: str | None = None
    required_context: dict[str, Any] = field(default_factory=dict)

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
            "status": self.status,
            "attempt": self.attempt,
            "attempts": self.attempts,
            "gate_passed": self.gate_passed,
            "gate_detail": self.gate_detail,
            "blocking_reason": self.blocking_reason,
            "output": self.output,
            "lease_token": self.lease_token,
            "required_context": self.required_context,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "StageCard":
        if not isinstance(value, Mapping):
            raise PlanningKanbanError("kanban card is not an object")

        def string(name: str) -> str:
            result = value.get(name)
            if not isinstance(result, str) or not result:
                raise PlanningKanbanError(f"kanban card field {name} is invalid")
            return result

        def strings(name: str) -> tuple[str, ...]:
            result = value.get(name)
            if not isinstance(result, (list, tuple)) or not all(
                isinstance(item, str) and item for item in result
            ):
                raise PlanningKanbanError(f"kanban card field {name} is invalid")
            return tuple(result)

        status = value.get("status", "pending")
        attempt = value.get("attempt", 0)
        attempts = value.get("attempts", [])
        gate_passed = value.get("gate_passed", False)
        gate_detail = value.get("gate_detail")
        blocking_reason = value.get("blocking_reason")
        output = value.get("output", {})
        lease_token = value.get("lease_token")
        required_context = value.get("required_context", {})
        if (
            not isinstance(status, str)
            or status not in _STATUSES
            or not isinstance(attempt, int)
            or isinstance(attempt, bool)
            or attempt < 0
            or not isinstance(attempts, list)
            or not all(isinstance(item, Mapping) for item in attempts)
            or not isinstance(gate_passed, bool)
            or (gate_detail is not None and not isinstance(gate_detail, str))
            or (blocking_reason is not None and not isinstance(blocking_reason, str))
            or not isinstance(output, Mapping)
            or (lease_token is not None and (not isinstance(lease_token, str) or not lease_token))
            or not isinstance(required_context, Mapping)
        ):
            raise PlanningKanbanError("kanban card operational fields are invalid")
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
            status=status,
            attempt=attempt,
            attempts=[dict(item) for item in attempts],
            gate_passed=gate_passed,
            gate_detail=gate_detail,
            blocking_reason=blocking_reason,
            output=dict(output),
            lease_token=lease_token,
            required_context=dict(required_context),
        )


@dataclass(frozen=True)
class _LeaseCapability:
    """Ephemeral authority for one claim in one PlanningRun instance."""

    instance_id: str
    worker: str
    card_id: str
    attempt: int
    lease_token: str


@dataclass
class PlanningRun:
    root: Path
    run_id: str
    cards: list[StageCard]
    contract_sha256: str
    _writer_lock: _ExclusiveLock | None = field(default=None, repr=False, compare=False)
    _instance_id: str = field(default_factory=lambda: secrets.token_hex(24), repr=False, compare=False)
    _lease_capabilities: dict[str, _LeaseCapability] = field(
        default_factory=dict, repr=False, compare=False
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
            contract_sha256=self.contract_sha256,
            cards=self.cards,
        )
        payload["state_sha256"] = _sha(payload)
        return payload

    def _save(self, *, expected_state: str | None = None, lock: _ExclusiveLock | None = None) -> None:
        if lock is not None:
            lock.assert_owned()
        if expected_state is not None:
            current = PlanningKanban.load(self.root, self.run_id)
            if _state_fingerprint(current) != expected_state:
                raise PlanningKanbanError("kanban state changed during mutation")
        _validate_loaded_state(self.cards)
        _safe_state_path(self.root, self.run_id)
        _atomic_json(self.path, self._payload())
        if lock is not None:
            lock.assert_owned()

    def reconcile(self) -> "PlanningRun":
        """Reload and validate the persisted projection before dispatch/handoff."""
        loaded = PlanningKanban.load(self.root, self.run_id)
        if loaded.contract_sha256 != self.contract_sha256:
            raise PlanningKanbanError("kanban contract hash does not reconcile")
        return loaded

    def _adopt(self, loaded: "PlanningRun") -> None:
        self.cards = loaded.cards
        self.contract_sha256 = loaded.contract_sha256

    def _owns_lease(self, card_id: str, card: StageCard) -> bool:
        capability = self._lease_capabilities.get(card_id)
        if capability is None or capability.instance_id != self._instance_id:
            return False
        if (
            card.status != "running"
            or capability.card_id != card_id
            or capability.attempt != card.attempt
            or capability.lease_token != card.lease_token
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

    @contextmanager
    def _mutation(
        self,
        card_id: str,
        *,
        require_owner: bool = False,
        require_running_owner: bool = False,
    ) -> Iterator[tuple["PlanningRun", StageCard, str, _ExclusiveLock | None]]:
        local = self.card(card_id)
        probe = PlanningKanban.load(self.root, self.run_id)
        persisted = probe.card(card_id)
        writer_needed = persisted.workspace_mode == "dir" and persisted.stage in _WRITERS
        if (
            self._writer_lock is not None
            and self._writer_lock.card_id == card_id
            and not writer_needed
        ):
            raise WorkspacePolicyError("persisted workspace policy changed under a writer lease")
        if require_owner or (require_running_owner and persisted.status == "running"):
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
            if require_owner or (require_running_owner and current.status == "running"):
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
            self._parents_ready(loaded.cards, card)
            if card.status not in {"pending", "ready"}:
                raise StageBlocked(f"card {card_id} is {card.status}")
            card.attempt += 1
            card.status = "running"
            lease_token = writer_lock.token if writer_lock is not None else secrets.token_hex(24)
            card.lease_token = lease_token
            card.attempts.append(
                {"attempt": card.attempt, "worker": worker, "event": "claimed"}
            )
            capability = _LeaseCapability(
                instance_id=self._instance_id,
                worker=worker,
                card_id=card_id,
                attempt=card.attempt,
                lease_token=lease_token,
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
            card.attempts.append({"attempt": card.attempt, "event": "heartbeat"})
            loaded._save(expected_state=before, lock=writer_lock)
            self._adopt(loaded)
            return self.card(card_id)

    def complete(self, card_id: str, *, evidence: Mapping[str, Any]) -> StageCard:
        gate = _validated_completion_gate(evidence)
        with self._mutation(card_id, require_owner=True) as (loaded, card, before, writer_lock):
            if card.status != "running":
                raise StageBlocked("completion requires a claimed card")
            card.output = _json_copy(evidence, what="completion evidence")
            card.status = "complete"
            card.gate_passed = True
            card.gate_detail = json.dumps(gate, sort_keys=True, separators=(",", ":"))
            card.lease_token = None
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
        with self._mutation(card_id, require_owner=True) as (loaded, card, before, writer_lock):
            release_writer = False
            if passed:
                if card.status != "complete":
                    raise StageBlocked("a gate cannot pass an incomplete card")
                if not _same_json(card.output.get("gate"), dict(detail)):
                    raise StageBlocked("passing gate evidence does not match completion evidence")
                card.gate_passed = True
                card.gate_detail = json.dumps(dict(detail), sort_keys=True, separators=(",", ":"))
            else:
                release_writer = card.status == "running"
                card.gate_passed = False
                card.gate_detail = str(detail)
                if card.status in {"complete", "running"}:
                    card.status = "blocked"
                    card.blocking_reason = str(detail)
                    card.lease_token = None
                for child in loaded.cards:
                    if card.id in child.parents and child.status == "ready":
                        child.status = "blocked"
                        child.blocking_reason = f"parent {card.id} gate evidence is no longer valid"
            loaded._save(expected_state=before, lock=writer_lock)
            if not passed and release_writer and writer_lock is not None:
                writer_lock.release()
                if self._writer_lock is writer_lock:
                    self._writer_lock = None
            self._adopt(loaded)
            if not passed and release_writer:
                self._lease_capabilities.pop(card_id, None)
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
        with self._mutation(card_id, require_running_owner=True) as (loaded, card, before, writer_lock):
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
            loaded._save(expected_state=before, lock=writer_lock)
            if writer_lock is not None:
                writer_lock.release()
                if self._writer_lock is writer_lock:
                    self._writer_lock = None
            self._adopt(loaded)
            self._lease_capabilities.pop(card_id, None)
            return self.card(card_id)

    def resume(self, card_id: str, *, evidence: Mapping[str, Any] | None = None) -> StageCard:
        with self._mutation(card_id) as (loaded, card, before, writer_lock):
            if card.status != "needs_input":
                raise StageBlocked("only needs_input cards can be resumed")
            if evidence is None:
                raise StageBlocked("resume requires current human-decision and fresh-review evidence")
            validated = _validated_resume_evidence(evidence, card.required_context)
            card.status, card.blocking_reason = "ready", None
            card.required_context = {}
            card.output["resume"] = _json_copy(validated, what="resume evidence")
            card.attempts.append(
                {"attempt": card.attempt, "event": "resumed", "evidence": card.output["resume"]}
            )
            loaded._save(expected_state=before, lock=writer_lock)
            self._adopt(loaded)
            return self.card(card_id)

    def reclaim(self, card_id: str, *, reason: str) -> StageCard:
        if not isinstance(reason, str) or not reason.strip():
            raise PlanningKanbanError("reclaim reason must be non-empty")
        with self._mutation(card_id, require_owner=True) as (loaded, card, before, writer_lock):
            if card.status != "running":
                raise StageBlocked("only running cards can be reclaimed")
            card.status = "ready"
            card.attempts.append(
                {"attempt": card.attempt, "event": "reclaimed", "reason": reason}
            )
            card.lease_token = None
            loaded._save(expected_state=before, lock=writer_lock)
            if writer_lock is not None:
                writer_lock.release()
                if self._writer_lock is writer_lock:
                    self._writer_lock = None
            self._adopt(loaded)
            self._lease_capabilities.pop(card_id, None)
            return self.card(card_id)


class PlanningKanban:
    @staticmethod
    def materialize(
        root: Path,
        run_id: str,
        *,
        assignee: str = "planning-worker",
        workspace_mode: str = "dir",
    ) -> PlanningRun:
        if workspace_mode not in {"dir", "worktree"}:
            raise WorkspacePolicyError("workspace_mode must be dir or worktree")
        if not isinstance(assignee, str) or not assignee.strip():
            raise PlanningKanbanError("assignee must be a non-empty string")
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
                return PlanningKanban.load(root, run_id)
            if _safe_run(root, run_id) != run_path:
                raise PlanningKanbanError("planning run path changed during materialization")
            cards = _canonical_cards(root, run_id, assignee, workspace_mode)
            contract = _sha({"run_id": run_id, "cards": [_contract_card(card) for card in cards]})
            result = PlanningRun(root.resolve(), run_id, cards, contract)
            result._save(lock=state_lock)
            return result
        finally:
            state_lock.release()

    @staticmethod
    def load(root: Path, run_id: str) -> PlanningRun:
        path = _safe_state_path(root, run_id)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise PlanningKanbanError("kanban graph is unreadable") from exc
        if not isinstance(raw, Mapping):
            raise PlanningKanbanError("kanban graph is not an object")
        try:
            cards_raw = raw["cards"]
            contract = raw["contract_sha256"]
            cards = [StageCard.from_dict(item) for item in cards_raw]
        except (KeyError, TypeError) as exc:
            raise PlanningKanbanError("kanban graph is unreadable") from exc
        if raw.get("schema") != 1 or raw.get("run_id") != run_id:
            raise PlanningKanbanError("kanban graph header is invalid")
        state_hash = raw.get("state_sha256")
        if not isinstance(state_hash, str) or not _HEX_SHA256.fullmatch(state_hash):
            raise PlanningKanbanError("kanban state integrity hash is invalid")
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
        expected_state_hash = _sha(
            _state_payload(run_id=run_id, contract_sha256=contract, cards=cards)
        )
        if state_hash != expected_state_hash:
            raise PlanningKanbanError("kanban state integrity hash does not reconcile")
        _validate_loaded_state(cards)
        return PlanningRun(root.resolve(), run_id, cards, contract)

    @staticmethod
    def resume(root: Path, run_id: str) -> PlanningRun:
        return PlanningKanban.load(root, run_id)


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
    *, run_id: str, contract_sha256: str, cards: list[StageCard]
) -> dict[str, Any]:
    return {
        "schema": 1,
        "run_id": run_id,
        "contract_sha256": contract_sha256,
        "cards": [card.to_dict() for card in cards],
        "edges": [[card.parents[0], card.id] for card in cards if card.parents],
    }


def _state_fingerprint(run: PlanningRun) -> str:
    return _sha(
        _state_payload(
            run_id=run.run_id,
            contract_sha256=run.contract_sha256,
            cards=run.cards,
        )
    )


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


def _validate_loaded_state(cards: list[StageCard]) -> None:
    for card in cards:
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
