from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Finding:
    usecase: str
    description: str
    snapshot: dict = field(default_factory=dict)
    sr: str | None = None
    artifacts: list[str] = field(default_factory=list)
