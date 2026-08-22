"""Goal lifecycle state machine (spec §13).

A goal moves through a fixed set of states via a deterministic transition
table. Transitions are the only way a goal state changes: recording a lifecycle
step goes through `transition`, never by direct assignment. The editor has no
LLM in the loop here — marking a goal REACHED is a deterministic edge result,
not a judgement call (spec §14).
"""
from __future__ import annotations

from typing import Literal

GoalState = Literal[
    "DECLARED",
    "ACTIVE",
    "EVALUATING",
    "NOT_REACHED",
    "REACHED",
    "REGRESSED",
    "BLOCKED",
]


class TransitionError(ValueError):
    """A state transition the spec §13 table does not allow."""


TERMINAL_GOAL_STATES: frozenset[GoalState] = frozenset({"REACHED", "NOT_REACHED"})


_TRANSITIONS: dict[GoalState, set[GoalState]] = {
    "DECLARED": {"ACTIVE"},
    "ACTIVE": {"EVALUATING", "BLOCKED"},
    "EVALUATING": {"NOT_REACHED", "REACHED", "BLOCKED"},
    "NOT_REACHED": {"ACTIVE", "EVALUATING", "BLOCKED"},
    "REACHED": {"EVALUATING", "REGRESSED"},
    "REGRESSED": {"ACTIVE", "EVALUATING"},
    "BLOCKED": {"ACTIVE"},
}


def can_transition(from_: GoalState, to: GoalState) -> bool:
    """True iff the §13 table permits the `from_ -> to` edge."""
    return to in _TRANSITIONS.get(from_, frozenset())


def transition(from_: GoalState, to: GoalState) -> GoalState:
    """Return `to` when the edge is legal; raise `TransitionError` otherwise."""
    if not can_transition(from_, to):
        raise TransitionError(f"{from_} -> {to} not allowed")
    return to

