"""System navigator data model (design §3.1, §3.2, §7.2-§7.4).

Every rendered fact carries a claim class saying where it came from
(`ClaimClass`) and a freshness state saying whether it is still current
(`FreshnessState`). The two are orthogonal axes with exactly one coupling
rule: ``kind == missing`` if and only if ``freshness.state == n/a``. That
rule is enforced here in `SystemClaim.__post_init__` and, redundantly, in
the JSON schemas under `factory/schemas/system_*.schema.json` -- neither
layer can be bypassed on its own.

Nothing here performs a query. These are shapes: stable dataclasses that
later tasks populate from `factory.trace`, `factory.requirements.register`,
`factory.evidence`, and friends.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any


class ClaimClass(str, Enum):
    """Where a rendered fact came from (design §3.1)."""

    RECORDED = "recorded"
    DERIVED = "derived"
    SYNTHESIZED = "synthesized"
    MISSING = "missing"


class FreshnessState(str, Enum):
    """Whether a claim is still current (design §3.2)."""

    FRESH = "fresh"
    STALE = "stale"
    DEGRADED = "degraded"
    NA = "n/a"


class CitationKind(str, Enum):
    MANIFEST = "manifest"
    TASK = "task"
    REQUIREMENT = "requirement"
    VALIDATION = "validation"
    REVIEW = "review"
    DECISION = "decision"
    TRACE = "trace"
    BUNDLE = "bundle"
    SESSION = "session"


class MatrixStatus(str, Enum):
    """Recorded outcome only -- staleness/absence live on `freshness` (design §7.3)."""

    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    BLOCKED = "blocked"
    NEVER_RUN = "never-run"
    UNKNOWN = "unknown"


class TimelineActor(str, Enum):
    HUMAN = "human"
    DEV = "dev"
    REVIEW = "review"
    VALIDATION = "validation"
    ORCHESTRATOR = "orchestrator"
    UNKNOWN = "unknown"
    NOT_RECORDED = "not-recorded"


class TimelineAction(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    VALIDATED = "validated"
    REPAIRED = "repaired"
    PUBLISHED = "published"
    STOPPED = "stopped"
    NOT_RECORDED = "not-recorded"


@dataclass(frozen=True)
class SystemScopeRef:
    """A `{kind, ref}` pointer, reused for scopes and record subjects.

    Legal `kind` values are context-dependent (declared bundle members are
    restricted to spec/plan/task/sr; matrix/timeline subjects have their own
    legal sets) so this stays a plain string here -- each JSON schema
    constrains the legal set for its own context.
    """

    kind: str
    ref: str


@dataclass(frozen=True)
class SystemCitation:
    """A recorded source a claim can be traced back to (design §7.2)."""

    kind: CitationKind
    path: str
    sha256: str | None = None
    anchor: str | None = None


@dataclass(frozen=True)
class Span:
    """A verbatim quoted span, present only on synthesized claims (design §7.2)."""

    text: str
    citation_index: int


@dataclass(frozen=True)
class FreshnessDependency:
    name: str
    expected: str | None = None
    actual: str | None = None


@dataclass(frozen=True)
class Freshness:
    state: FreshnessState
    reason: str | None = None
    dependencies: list[FreshnessDependency] = field(default_factory=list)


@dataclass(frozen=True)
class SystemClaim:
    """The shared record shape (design §7.2).

    Enforces, in both directions, the §3.2 coupling rule (`kind == missing`
    iff `freshness.state == n/a`), and that `spans` is only ever present on
    `synthesized` claims (design §7.2, brief item 4).
    """

    kind: ClaimClass
    text: str
    freshness: Freshness
    citations: list[SystemCitation] = field(default_factory=list)
    spans: list[Span] = field(default_factory=list)

    def __post_init__(self) -> None:
        is_missing = self.kind is ClaimClass.MISSING
        is_na = self.freshness.state is FreshnessState.NA
        if is_missing != is_na:
            raise ValueError(
                "coupling rule violated: kind == missing iff freshness.state == n/a "
                f"(kind={self.kind.value!r}, freshness.state={self.freshness.state.value!r})"
            )
        if self.spans and self.kind is not ClaimClass.SYNTHESIZED:
            raise ValueError(
                f"spans are only allowed on synthesized claims (kind={self.kind.value!r})"
            )
        for span in self.spans:
            if not (0 <= span.citation_index < len(self.citations)):
                raise ValueError(
                    f"span citation_index {span.citation_index} is out of range for "
                    f"{len(self.citations)} citation(s)"
                )


@dataclass(frozen=True)
class ValidationMatrixRow:
    """One row of the implementation/validation/decision matrix (design §7.3)."""

    subject: SystemScopeRef
    status: MatrixStatus
    evidence: list[str]
    freshness: Freshness
    summary: str


@dataclass(frozen=True)
class DecisionTimelineEvent:
    """A chronological decision or state change (design §7.4, §4.3).

    Ordering comes only from recorded timestamps (`at`) or recorded sequence
    numbers (`sequence`) -- never inferred -- so at least one must be set.
    """

    actor: TimelineActor
    action: TimelineAction
    subject: SystemScopeRef
    citation: SystemCitation
    freshness: Freshness
    at: str | None = None
    sequence: int | None = None

    def __post_init__(self) -> None:
        if self.at is None and self.sequence is None:
            raise ValueError("timeline event requires 'at' or 'sequence' for ordering")


@dataclass(frozen=True)
class SystemGuide:
    """A grounded prose guide: a scope plus an ordered list of claim sections.

    Each section is a full `SystemClaim` -- either synthesized prose with
    spans (when every supporting dependency is fresh) or recorded bullets
    (when the collapse predicate fires). Section assembly is query logic and
    is out of scope for this task; only the shape is defined here.
    """

    scope: SystemScopeRef
    sections: list[SystemClaim]


@dataclass(frozen=True)
class BundleDeclaration:
    """A declared feature-scope bundle (design §3.3).

    Carries a label and exact member refs only -- no status, no claims, no
    rationale. A member ref that fails to parse is reported in `unresolved`
    as a `missing` claim rather than dropped, and degrades the bundle
    without removing it (`degraded`).
    """

    id: str
    label: str
    members: list[SystemScopeRef]
    unresolved: list[SystemClaim]
    citation: SystemCitation

    @property
    def degraded(self) -> bool:
        return bool(self.unresolved)


def to_dict(value: Any) -> Any:
    """Recursively convert dataclasses/enums into plain JSON-able values."""
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: to_dict(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, (list, tuple)):
        return [to_dict(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    return value
