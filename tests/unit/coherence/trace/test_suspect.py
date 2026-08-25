import pytest
from dataclasses import dataclass
from coherence.trace.suspect import edge_validity
pytestmark = pytest.mark.unit

@dataclass
class _FakeGap:
    kind: str
    disposition: str

def test_no_gaps_without_recorded_prior_state_is_valid():
    assert edge_validity([]) == "valid"
def test_empty_gaps_preserve_recorded_suspect_state():
    assert edge_validity([], prior_state="suspect") == "suspect"
def test_empty_gaps_preserve_recorded_waived_state():
    assert edge_validity([], prior_state="waived") == "waived"
def test_pending_sr_stale_is_suspect():
    assert edge_validity([_FakeGap("sr_stale", "pending")]) == "suspect"
def test_pending_sr_unsatisfied_is_invalid():
    assert edge_validity([_FakeGap("sr_unsatisfied", "pending")]) == "invalid"
def test_only_non_pending_gaps_is_waived():
    assert edge_validity([_FakeGap("sr_stale", "deferred")]) == "waived"
def test_only_exempt_gaps_is_waived():
    assert edge_validity([_FakeGap("sr_unsatisfied", "exempt")]) == "waived"


def test_invalid_kind_beats_suspect_kind_when_both_pending():
    # A fatal pending gap must win the precedence over a non-fatal one: the
    # edge's satisfaction claim is untrusted regardless of a coexisting
    # staleness signal.
    assert (
        edge_validity(
            [_FakeGap("sr_stale", "pending"), _FakeGap("sr_unsatisfied", "pending")]
        )
        == "invalid"
    )


def test_mixed_waiver_and_pending_gaps_is_proposed_not_waived():
    # `waived` requires EVERY gap to carry a waiver disposition. A deferred
    # gap alongside a pending gap of an unrecognised kind (neither fatal nor
    # suspect) is still unresolved -- `proposed`, never `waived`.
    assert (
        edge_validity(
            [_FakeGap("sr_unrecognised", "deferred"), _FakeGap("sr_unrecognised", "pending")]
        )
        == "proposed"
    )


def test_pending_nonfatal_unknown_kind_is_proposed():
    # A kind outside the recognized tuples, still pending, is not clearly
    # disqualifying, suspect, or waived -- so it stays `proposed`.
    assert edge_validity([_FakeGap("sr_unrecognised", "pending")]) == "proposed"