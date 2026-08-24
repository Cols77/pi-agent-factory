"""Tests for coherence.router: the deterministic phrase-to-intent router
(Increment 5 Task 4, spec plan
docs/superpowers/plans/2026-08-20-coherence-increment-5-status-focus-dispatcher.md,
"Approved deterministic-router amendment"). No model call anywhere in this
module or its CLI wiring -- `route_text` is pure string matching against a
versioned phrase table."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from coherence.router import Intent, RouteMatch, main, route_text

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------
# One test per intent -- a phrase that should route to it, alone, with no
# other intent's phrases present.
# --------------------------------------------------------------------------


def test_route_text_routes_understand():
    match = route_text("What is the current status?")
    assert match == RouteMatch(intent=Intent.UNDERSTAND, scope_ref=None, score=3)


def test_route_text_routes_verify_claim():
    match = route_text("Please verify this")
    assert match == RouteMatch(intent=Intent.VERIFY_CLAIM, scope_ref=None, score=3)


def test_route_text_routes_close_gaps():
    match = route_text("Let's close gaps in coverage")
    assert match is not None
    assert match.intent is Intent.CLOSE_GAPS
    assert match.score >= 3


def test_route_text_routes_author_requirements():
    match = route_text("Please write requirement for the new feature")
    assert match is not None
    assert match.intent is Intent.AUTHOR_REQUIREMENTS
    assert match.score >= 3


def test_route_text_routes_build():
    match = route_text("Let's build the feature now")
    assert match == RouteMatch(intent=Intent.BUILD, scope_ref=None, score=3)


def test_route_text_routes_recover():
    match = route_text("We need to recover from this")
    assert match == RouteMatch(intent=Intent.RECOVER, scope_ref=None, score=3)


def test_route_text_routes_triage():
    match = route_text("Time to triage this issue")
    assert match is not None
    assert match.intent is Intent.TRIAGE
    assert match.score >= 3


def test_route_text_routes_teach():
    match = route_text("Can you teach me this?")
    assert match is not None
    assert match.intent is Intent.TEACH
    assert match.score >= 3


# --------------------------------------------------------------------------
# Scope-ref extraction (reuses coherence.navigate.queries.parse_scope_ref;
# never a second `<kind>:<id>` parser).
# --------------------------------------------------------------------------


def test_route_text_extracts_scope_ref_from_free_text():
    match = route_text("verify sr:SR-001 please")
    assert match is not None
    assert match.intent is Intent.VERIFY_CLAIM
    assert match.scope_ref == "sr:SR-001"


def test_route_text_extracts_scope_ref_and_strips_trailing_punctuation():
    match = route_text("please recover task:T-001, thanks")
    assert match is not None
    assert match.intent is Intent.RECOVER
    assert match.scope_ref == "task:T-001"


def test_route_text_scope_ref_is_none_when_absent():
    match = route_text("Please verify this")
    assert match is not None
    assert match.scope_ref is None


def test_route_text_ignores_a_scope_ref_with_an_unrecognized_kind():
    # "xyz" is not in _SCOPE_KINDS, so this never even looks like a scope ref
    # to the extractor -- it is plain text, not a malformed ref to reject.
    match = route_text("please verify xyz:not-a-real-scope")
    assert match is not None
    assert match.intent is Intent.VERIFY_CLAIM
    assert match.scope_ref is None


# --------------------------------------------------------------------------
# Normalization: case and whitespace never change the route.
# --------------------------------------------------------------------------


def test_route_text_normalizes_case_and_whitespace():
    match = route_text("   VERIFY   this   CLAIM   ")
    assert match == RouteMatch(intent=Intent.VERIFY_CLAIM, scope_ref=None, score=3)


# --------------------------------------------------------------------------
# None cases: tie, no match, below threshold.
# --------------------------------------------------------------------------


def test_route_text_returns_none_on_a_tie():
    # "verify" (VERIFY_CLAIM, 3) and "build" (BUILD, 3) score equally --
    # no unique maximum, so the router refuses to guess.
    assert route_text("verify and build this") is None


def test_route_text_returns_none_when_no_phrase_matches():
    assert route_text("The weather is nice today") is None


def test_route_text_returns_none_when_score_is_below_threshold():
    # "gap" alone is CLOSE_GAPS' lowest-weighted phrase (1) -- some match,
    # but the max score never reaches the threshold (3).
    assert route_text("there is a small gap here") is None


def test_route_text_returns_none_for_empty_text():
    assert route_text("") is None


# --------------------------------------------------------------------------
# CLI wiring
# --------------------------------------------------------------------------


def test_main_json_flag_prints_a_route_when_matched(capsys):
    code = main(["Please verify this", "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"route": {"intent": "VERIFY_CLAIM", "scope_ref": None, "score": 3}}


def test_main_json_flag_prints_null_route_when_no_match(capsys):
    code = main(["The weather is nice today", "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"route": None}


def test_main_json_flag_includes_scope_ref_when_present(capsys):
    code = main(["verify sr:SR-001 please", "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"route": {"intent": "VERIFY_CLAIM", "scope_ref": "sr:SR-001", "score": 3}}


def test_coherence_route_is_registered_in_the_group_dispatcher():
    from coherence import cli

    assert "route" in cli.GROUPS


def test_coherence_route_dispatches_through_top_level_module():
    import subprocess
    import sys as _sys

    project_root = Path(__file__).parents[3]
    result = subprocess.run(
        [_sys.executable, "-m", "coherence", "route", "Please verify this", "--json"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["route"]["intent"] == "VERIFY_CLAIM"
