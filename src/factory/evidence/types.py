from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from factory.orchestrator.backends import GateRunner


@dataclass(frozen=True)
class CheckResult:
    passed: bool
    evidence: str


@dataclass
class EvidenceContext:
    """Bundle of evidence sources a connector may read. A connector touches only
    the sources it needs; new sources are added here without changing existing
    connectors."""
    repo_root: Path
    gates: GateRunner | None = None
    kb_dir: Path | None = None


@runtime_checkable
class Connector(Protocol):
    kind: str
    args_schema: dict
    side_effect_free: bool

    def evaluate(self, args: dict, ctx: EvidenceContext) -> CheckResult: ...
