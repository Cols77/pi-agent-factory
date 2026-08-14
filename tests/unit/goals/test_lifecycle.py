"""Goal lifecycle state machine tests (spec §13 table)."""

import pytest

from factory.goals.lifecycle import GoalState, TransitionError, can_transition, transition

pytestmark = pytest.mark.unit

# The spec §13 adjacency table, mirrored so a missing/extra edge fails loudly.
_LEGAL: dict[GoalState, set[GoalState]] = {
    "DECLARED": {"ACTIVE"},
    "ACTIVE": {"EVALUATING", "BLOCKED"},
    "EVALUATING": {"NOT_REACHED", "REACHED", "BLOCKED"},
    "NOT_REACHED": {"ACTIVE", "EVALUATING", "BLOCKED"},
    "REACHED": {"EVALUATING", "REGRESSED"},
    "REGRESSED": {"ACTIVE", "EVALUATING"},
    "BLOCKED": {"ACTIVE"},
}

_ILLEGAL = [
    ("REACHED", "DECLARED"),
    ("DECLARED", "EVALUATING"),
    ("DECLARED", "REACHED"),
    ("ACTIVE", "DECLARED"),
    ("EVALUATING", "DECLARED"),
    ("REACHED", "ACTIVE"),
    ("REGRESSED", "REACHED"),
    ("BLOCKED", "EVALUATING"),
    ("BLOCKED", "REACHED"),
]


def test_every_legal_edge_is_allowed() -> None:
    for from_, targets in _LEGAL.items():
        for to in targets:
            assert can_transition(from_, to), f"{from_} -> {to} should be legal"


def test_transition_returns_target_for_legal_edge() -> None:
    assert transition("DECLARED", "ACTIVE") == "ACTIVE"
    assert transition("NOT_REACHED", "EVALUATING") == "EVALUATING"
    assert transition("REGRESSED", "EVALUATING") == "EVALUATING"


def test_no_legal_edge_is_missing() -> None:
    # The implementation table must not be a superset of the spec either:
    # every implementation edge must appear in the spec table.
    from factory.goals.lifecycle import _TRANSITIONS

    for from_, targets in _TRANSITIONS.items():
        for to in targets:
            assert to in _LEGAL.get(from_, set()), f"unexpected edge {from_} -> {to}"


def test_illegal_edges_are_rejected() -> None:
    for from_, to in _ILLEGAL:
        assert not can_transition(from_, to), f"{from_} -> {to} must be illegal"


def test_transition_raises_on_illegal_edge() -> None:
    for from_, to in _ILLEGAL:
        with pytest.raises(TransitionError):
            transition(from_, to)


def test_transition_error_is_a_value_error() -> None:
    with pytest.raises(ValueError):
        transition("REACHED", "DECLARED")


def test_not_reached_can_enter_blocked() -> None:
    # Blocked-by-external-dependency is legal from NOT_REACHED (spec §13).
    assert can_transition("NOT_REACHED", "BLOCKED")
    assert transition("NOT_REACHED", "BLOCKED") == "BLOCKED"


def test_regression_cycle_allowed() -> None:
    # REACHED -> REGRESSED -> EVALUATING -> REACHED is a valid §13 cycle.
    assert can_transition("REACHED", "REGRESSED")
    assert can_transition("REGRESSED", "EVALUATING")
    assert can_transition("EVALUATING", "REACHED")
    assert transition(transition(transition("REACHED", "REGRESSED"), "EVALUATING"), "REACHED") == "REACHED"
