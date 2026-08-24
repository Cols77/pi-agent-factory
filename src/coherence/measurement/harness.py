from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from coherence.register.register import Binding

__all__ = ["Harness", "HarnessResult", "TrialResult"]


@dataclass(frozen=True)
class TrialResult:
    seed: int
    passed: bool
    detail: str = ""


@dataclass(frozen=True)
class HarnessResult:
    metric_value: float
    passed: bool
    trials: list[TrialResult]
    artifacts: list[Path]
    raw: dict


class Harness(Protocol):
    def run(self, binding: Binding, workdir: Path) -> HarnessResult: ...
