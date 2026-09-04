from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # Static-analysis-only: gives pyright the real substrate types for
    # annotations like `AgentResult | None` elsewhere in the codebase (e.g.
    # factory.orchestrator.nodes/backends), without adding a runtime import --
    # actual runtime access still goes through __getattr__ below, which is
    # what emits the deprecation warning.
    from substrate.agents.model import AgentResult as AgentResult
    from substrate.agents.model import InterruptionReason as InterruptionReason


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
    # Read-only per-SR semantic-fidelity judge (SR-050/AC-4,
    # coherence.register.fidelity's default judge). Scope: read-only, no
    # bash; receives an injected FidelityPacket and emits a JSON findings
    # verdict -- never authoritative on its own, see fidelity.py's docstring.
    FIDELITY_REVIEW = "fidelity-review"
    # Read-only cross-SR overlap judge (SR-058/AC-2,
    # coherence.register.overlap's default judge). Scope: read-only, no
    # bash; receives an injected OverlapCandidate and emits a JSON verdict
    # (confirmed/dismissed) -- never auto-declares a relation or auto-merges
    # requirements, see coherence/register/overlap.py's docstring.
    OVERLAP_REVIEW = "overlap-review"


class NodeOutcome(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    REJECT = "reject"
    CHANGES = "changes-requested"
    ESCALATE = "escalate"
    ALREADY_DONE = "already-done"


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


# AgentResult and InterruptionReason moved to substrate.agents.model (they are
# neutral agent-subprocess primitives, unlike the four types above which are
# domain/pipeline concepts and stay here untouched). Exposed below as a lazy,
# per-attribute warn-and-reexport shim (PEP 562 module __getattr__) rather
# than a whole-module warnings.warn(), so that importing AgentRole/NodeOutcome
# /NodeEvent/TaskResult -- this module's permanent, non-deprecated surface,
# used on every normal run -- never spuriously warns.
_REEXPORT_TARGETS = {
    "AgentResult": "substrate.agents.model",
    "InterruptionReason": "substrate.agents.model",
}


def __getattr__(name: str) -> Any:
    target_module = _REEXPORT_TARGETS.get(name)
    if target_module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    warnings.warn(
        f"factory.orchestrator.types.{name} is deprecated; import {target_module}.{name}",
        DeprecationWarning,
        stacklevel=2,
    )
    module = __import__(target_module, fromlist=[name])
    return getattr(module, name)
