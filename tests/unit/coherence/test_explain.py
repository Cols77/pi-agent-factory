"""Tests for coherence.explain: vocabulary-only term lookup, delegating
entirely to `coherence.navigate.vocabulary.build_vocabulary` (Increment 5
Task 2) -- no separate artifact-id lookup path, no reimplementation of the
vocabulary data."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from coherence.explain import UnknownTermError, explain_term
from coherence.navigate.vocabulary import VOCABULARY, build_vocabulary

pytestmark = pytest.mark.unit

_PROJECT_ROOT = Path(__file__).parents[3]


def _run_coherence(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "coherence", *args],
        cwd=str(_PROJECT_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )


# --------------------------------------------------------------------------
# explain_term: pure delegation to the existing vocabulary data
# --------------------------------------------------------------------------


def test_explain_term_returns_the_exact_vocabulary_entry_for_a_known_term():
    entry = explain_term("recorded")

    assert entry == build_vocabulary()["terms"]["recorded"]
    assert entry["term"] == "recorded"
    assert entry["group"] == "claim-kind"


@pytest.mark.parametrize("term", sorted(VOCABULARY.keys()))
def test_explain_term_resolves_every_known_vocabulary_key(term):
    entry = explain_term(term)

    assert entry is VOCABULARY[term] or entry == VOCABULARY[term]
    assert entry["term"] == VOCABULARY[term]["term"]


def test_explain_term_rejects_an_unknown_term():
    with pytest.raises(UnknownTermError):
        explain_term("definitely-not-a-real-term")


def test_explain_term_is_case_sensitive_and_rejects_a_near_miss():
    # "recorded" is real; "Recorded" is not a distinct key in VOCABULARY.
    with pytest.raises(UnknownTermError):
        explain_term("Recorded")


# --------------------------------------------------------------------------
# CLI wiring: `coherence explain <term-or-id>`
# --------------------------------------------------------------------------


def test_cli_explain_known_term_prints_gloss_and_exits_zero():
    result = _run_coherence("explain", "derived")

    assert result.returncode == 0
    assert "derived" in result.stdout
    assert VOCABULARY["derived"]["gloss"] in result.stdout


def test_cli_explain_json_flag_prints_the_exact_vocabulary_entry():
    result = _run_coherence("explain", "--json", "fresh")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload == VOCABULARY["fresh"]


def test_cli_explain_unknown_term_exits_nonzero_and_names_the_term():
    result = _run_coherence("explain", "not-a-real-term-xyz")

    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "not-a-real-term-xyz" in output


def test_explain_is_a_top_level_cli_group():
    from coherence import cli

    assert "explain" in cli.GROUPS
