from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class InterruptionReason(str, Enum):
    CONTEXT_LIMIT = "context_limit"
    IDLE_TIMEOUT = "idle_timeout"
    TOTAL_TIMEOUT = "total_timeout"
    PROCESS_EXIT = "process_exit"


@dataclass
class AgentResult:
    ok: bool
    output: dict
    raw: str = ""
    session_id: str | None = None
    interruption: InterruptionReason | None = None


class ScopeLike(Protocol):
    """Structural stand-in for `factory.orchestrator.roles.Scope`.

    substrate must never import that class (it is a factory-catalogue type
    built from AgentRole-keyed data), so `PiAgentBackend` only ever reads
    `.allow` / `.bash` off whatever `scope_for(role)` returns -- the real
    `Scope` dataclass satisfies this Protocol structurally, with no change to
    `Scope` itself. Declared as read-only properties (not plain attributes):
    `Scope` is a FROZEN dataclass, so pyright models it as offering no
    writable `__setattr__` -- a plain (read-write) Protocol attribute would
    reject it as "not writable"; a read-only one only ever needs `.allow` /
    `.bash` to be *readable*, which any of frozen Scope, a mutable stand-in,
    or a namedtuple all satisfy.
    """

    @property
    def allow(self) -> list[str]: ...

    @property
    def bash(self) -> str: ...
