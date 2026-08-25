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