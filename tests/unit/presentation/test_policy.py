"""Task 1 — presentation levels + noise policy (spec §23-§24).

``decide`` is a pure function; these tests encode the spec's level policy:
default INSPECT for a bare lookup, PRESENT on an explicit "show me"/"where is",
PRESENT on an important simulation failure or newly reached goal, REVIEW only
on an explicit review checkpoint, and never a UI-open on a routine test pass.
"""
from __future__ import annotations

import pytest

from factory.presentation.level import Facts, Level, decide, parse_level

pytestmark = pytest.mark.unit


def test_default_bare_lookup_is_inspect():
    assert decide(Facts()) is Level.INSPECT


def test_show_me_is_present():
    assert decide(Facts(show_requested=True)) is Level.PRESENT


def test_important_simulation_failure_is_present():
    assert decide(Facts(important_failure=True)) is Level.PRESENT


def test_newly_reached_goal_is_present():
    assert decide(Facts(goal_reached=True)) is Level.PRESENT


def test_unit_test_pass_stays_inspect():
    # A routine passing run carries no promotion flag -> INSPECT (no UI).
    assert decide(Facts(goal_reached=False, important_failure=False)) is Level.INSPECT


def test_explicit_review_checkpoint_is_review():
    assert decide(Facts(review_checkpoint=True)) is Level.REVIEW


def test_review_checkpoint_beats_show_request():
    # An explicit multi-artifact review context outranks a single "show me".
    assert decide(Facts(show_requested=True, review_checkpoint=True)) is Level.REVIEW


def test_parse_level_accepts_all_three():
    assert parse_level("INSPECT") is Level.INSPECT
    assert parse_level("PRESENT") is Level.PRESENT
    assert parse_level("REVIEW") is Level.REVIEW


def test_parse_level_is_strict():
    with pytest.raises(ValueError):
        parse_level("inspect")
    with pytest.raises(ValueError):
        parse_level("NOPE")
