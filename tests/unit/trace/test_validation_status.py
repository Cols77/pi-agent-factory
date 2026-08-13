"""Goal-aware requirement status tests (Task 7, additive)."""

import pytest
from pathlib import Path

from factory.goals.schema import Goal
from factory.trace.validation_status import requirement_validation

pytestmark = pytest.mark.unit


def _goal(state: str) -> Goal:
    return Goal(
        id="GOAL-NAV-003",
        title="t",
        path=Path("goals/GOAL-NAV-003.md"),
        state=state,  # type: ignore[arg-type]
    )


def test_no_goals_is_none():
    assert requirement_validation([]) is None


def test_all_reached_is_validated():
    assert requirement_validation([_goal("REACHED"), _goal("REACHED")]) == "VALIDATED"


def test_any_regressed_is_regressed():
    assert requirement_validation([_goal("REACHED"), _goal("REGRESSED")]) == "REGRESSED"


def test_goals_but_none_reached_is_verification_pending():
    assert requirement_validation([_goal("NOT_REACHED"), _goal("DECLARED")]) == "VERIFICATION_PENDING"


def test_mixed_reached_and_pending_is_verification_pending():
    assert requirement_validation([_goal("REACHED"), _goal("NOT_REACHED")]) == "VERIFICATION_PENDING"


def test_blocked_counts_as_pending_not_reached():
    assert requirement_validation([_goal("BLOCKED")]) == "VERIFICATION_PENDING"