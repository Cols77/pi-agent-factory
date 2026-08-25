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


# -- expired_baselines (Task 7 Step 3) --------------------------------------


def _valid_sr(root, sid: str, *, with_binding=True) -> None:
    """Write a requirement file. With binding it is non-proposed, so a missing
    satisfies link drives it `invalid`; without binding it is proposed and the
    edge reads waived (still non-valid)."""
    (root / "requirements").mkdir(parents=True, exist_ok=True)
    binding = ""
    if with_binding:
        binding = (
            "binding:\n  harness: sim-testbench\n  experiment: e\n"
            "  metric: m\n  trials: 20\n  assert: \">= 0.90\"\n"
        )
    (root / "requirements" / f"{sid}.md").write_text(
        f"---\nid: {sid}\ntitle: T\nstatement: s\ndomain: d\n{binding}---\nbody\n",
        encoding="utf-8",
    )


def _write_baseline(root, bid: str, scope: list[str]) -> None:
    (root / "docs" / "baselines").mkdir(parents=True, exist_ok=True)
    scope_yaml = "\n".join(f"- {s}" for s in scope)
    (root / "docs" / "baselines" / f"{bid}.md").write_text(
        f"---\nid: {bid}\ntitle: t\ngit_ref: abc1234\nscope:\n{scope_yaml}\n"
        "approved_by: jane\n---\nbody\n",
        encoding="utf-8",
    )


def test_expired_baselines_returns_baselines_scoping_a_suspect_or_invalid_sr(tmp_path):
    from coherence.trace.suspect import expired_baselines

    # A non-proposed SR with no satisfies link -> `invalid` edge. A baseline
    # whose scope includes it is expired; a baseline scoping a clean SR is not.
    _valid_sr(tmp_path, "SR-001", with_binding=True)  # -> invalid (no satisfies)
    _write_baseline(tmp_path, "BASELINE-0001", ["sr:SR-001"])
    _write_baseline(tmp_path, "BASELINE-0002", ["sr:OTHER-999"])

    assert expired_baselines(tmp_path) == ["BASELINE-0001"]


def test_expired_baselines_is_empty_when_scoped_srs_are_valid(tmp_path):
    from coherence.trace.suspect import expired_baselines

    # No baselines at all -> empty (baselines are optional).
    _valid_sr(tmp_path, "SR-001", with_binding=True)
    assert expired_baselines(tmp_path) == []


def test_expired_baselines_is_a_query_not_an_auto_transition(tmp_path):
    # Closing an expired baseline is a human gate-protocol decision, never
    # automatic: this function only reports which baselines are stale; it does
    # not modify them.
    from coherence.trace.suspect import expired_baselines

    _valid_sr(tmp_path, "SR-001", with_binding=True)
    _write_baseline(tmp_path, "BASELINE-0001", ["sr:SR-001"])

    before = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*") if p.is_file())
    assert expired_baselines(tmp_path) == ["BASELINE-0001"]
    after = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*") if p.is_file())
    assert before == after