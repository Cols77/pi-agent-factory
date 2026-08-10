from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum


@dataclass(frozen=True)
class DependencyFingerprint:
    name: str
    kind: str
    digest: str
    source: str


class FreshnessSeverity(str, Enum):
    INTEGRITY = "integrity"
    BLOCKING = "blocking"
    WARNING = "warning"


# The tiers that fail a gate. Named once so every gate agrees on it -- a gate
# that filtered on BLOCKING alone would silently pass the *more* severe
# INTEGRITY tier.
GATE_FAILING_SEVERITIES = frozenset({FreshnessSeverity.INTEGRITY, FreshnessSeverity.BLOCKING})


@dataclass(frozen=True)
class FreshnessIssue:
    code: str
    severity: FreshnessSeverity
    subject: str
    dependency: str
    expected: str | None
    actual: str | None
    detail: str
    repair: str | None = None


@dataclass(frozen=True)
class FreshnessReport:
    issues: list[FreshnessIssue]

    @property
    def ok(self) -> bool:
        return not any(issue.severity in GATE_FAILING_SEVERITIES for issue in self.issues)

    def to_dict(self) -> dict:
        return {"ok": self.ok, "issues": [asdict(issue) for issue in self.issues]}
