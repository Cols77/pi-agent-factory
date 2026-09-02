"""The compiled Obligation contract (spec §4). Health, navigator and gates
consume this shape (SR-009); none reinterpret the profile independently.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Requiredness = Literal["not_applicable", "advisory", "required", "blocking"]


@dataclass(frozen=True)
class Obligation:
    id: str
    scope_ref: str
    kind: str
    requiredness: Requiredness
    reason: str
    source_policy: str
    state: str
    resolve_cmd: tuple[str, ...] | None = None
