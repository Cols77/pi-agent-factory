from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from coherence.planning.semantic import SemanticReviewPacket, SemanticReviewReport

PlanningSeverity = Literal["error", "warning"]


@dataclass(frozen=True)
class PlanningInput:
    """The source files and project root inspected by a planning check."""

    intent_path: Path
    spec_path: Path
    plan_path: Path
    project_root: Path
    run_id: str


@dataclass(frozen=True)
class PlanningFinding:
    """One deterministic diagnostic emitted by the planning checker."""

    code: str
    severity: PlanningSeverity
    subject: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "severity": self.severity,
            "subject": self.subject,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class PlanningReport:
    """Stable, side-effect-free result of checking planning source artifacts."""

    schema: int
    run_id: str
    ok: bool
    artifacts: tuple[dict[str, object], ...]
    findings: tuple[PlanningFinding, ...]
    next_actions: tuple[dict[str, object], ...]
    review_required: bool
    suggestion: dict[str, object] | None

    def to_dict(self) -> dict[str, object]:
        """Return the contract's fixed JSON field order."""
        return {
            "schema": self.schema,
            "run_id": self.run_id,
            "ok": self.ok,
            "artifacts": list(self.artifacts),
            "findings": [finding.to_dict() for finding in self.findings],
            "next_actions": list(self.next_actions),
            "review_required": self.review_required,
            "suggestion": self.suggestion,
        }


@dataclass(frozen=True)
class IntentAnswer:
    """One verbatim answer captured during planning."""

    id: str
    question: str
    text: str
    source: str
    sequence: int


@dataclass(frozen=True)
class IntentDocument:
    """Canonical in-memory representation of schema-one or schema-two intent."""

    schema: int
    run_id: str | None
    prompt: str
    answers: tuple[IntentAnswer, ...]
    brief: dict[str, list[str]]
    capture_status: str
    redactions: list[str]


@dataclass(frozen=True)
class CaptureEvent:
    """One append-only planning capture event."""

    run_id: str
    sequence: int
    kind: str
    payload: dict[str, object]


__all__ = [
    "CaptureEvent",
    "IntentAnswer",
    "IntentDocument",
    "PlanningFinding",
    "PlanningInput",
    "PlanningReport",
    "PlanningSeverity",
]

__all__ += ["SemanticReviewPacket", "SemanticReviewReport"]
