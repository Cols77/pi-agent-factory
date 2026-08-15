"""Presentation levels and the decision policy (spec §23-§24).

Three levels exist (INSPECT / PRESENT / REVIEW). ``decide`` is a pure function
from presentation facts to a level — it never touches the filesystem or opens
anything. The router and the CLI call it; callers that know more (e.g. the pi
extension after a simulation run) can pass facts.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Level(str, Enum):
    """Presentation level (spec §23)."""

    INSPECT = "INSPECT"
    PRESENT = "PRESENT"
    REVIEW = "REVIEW"


@dataclass(frozen=True)
class Facts:
    """Decision inputs for ``decide`` (all default off -> INSPECT)."""

    # "show me X" / "where is X" (spec §23 PRESENT).
    show_requested: bool = False
    # An important validation failure: a goal/simulation not reached (§24).
    important_failure: bool = False
    # A goal newly reached / a passing significant result (§24).
    goal_reached: bool = False
    # An explicit feature/task review checkpoint (spec §23 REVIEW).
    review_checkpoint: bool = False


def decide(facts: Facts) -> Level:
    """Map presentation facts to a level (spec §23-§24).

    Priority: an explicit review checkpoint wins (REVIEW); any single-purpose
    "show me" request, important validation failure, or newly reached goal
    promotes to PRESENT (open one relevant interface); otherwise INSPECT (no
    application focus change). A routine test pass never opens UI.
    """
    if facts.review_checkpoint:
        return Level.REVIEW
    if facts.show_requested or facts.important_failure or facts.goal_reached:
        return Level.PRESENT
    return Level.INSPECT


def parse_level(raw: str) -> Level:
    """Parse a CLI ``--level`` value, strict (no fuzzy fallback)."""
    for level in Level:
        if level.value == raw:
            return level
    raise ValueError(
        f"invalid --level: {raw!r} (expected INSPECT, PRESENT or REVIEW)"
    )
