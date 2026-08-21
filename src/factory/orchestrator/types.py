from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class AgentRole(str, Enum):
    CONTEXT_GATHERER = "context-gatherer"
    DEV = "dev"
    VALIDATION = "validation"
    REVIEW = "review"
    SESSION_REVIEW = "session-review"
    SYNTHESIS = "synthesis"
    # Read-only per-SR semantic audit child for the coverage-review workflow
    # (factory.coverage.runner). Scope: read-only, no bash; emits a JSON verdict.
    COVERAGE_AUDIT = "coverage-audit"


class InterruptionReason(str, Enum):
    CONTEXT_LIMIT = "context_limit"
    IDLE_TIMEOUT = "idle_timeout"
    TOTAL_TIMEOUT = "total_timeout"
    PROCESS_EXIT = "process_exit"


class NodeOutcome(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    REJECT = "reject"
    CHANGES = "changes-requested"
    ESCALATE = "escalate"
    ALREADY_DONE = "already-done"


@dataclass
class AgentResult:
    ok: bool
    output: dict
    raw: str = ""
    session_id: str | None = None
    interruption: InterruptionReason | None = None


@dataclass
class NodeEvent:
    node: str
    result: str
    attempts: int = 1
    extra: dict = field(default_factory=dict)


@dataclass
class TaskResult:
    task_id: str
    title: str
    outcome: str  # completed | rejected | escalated
    iterations: int
    events: list[NodeEvent]
    dod_met: bool
    manifest: dict | None = None
    start_commit: str | None = None
    result_commit: str | None = None
