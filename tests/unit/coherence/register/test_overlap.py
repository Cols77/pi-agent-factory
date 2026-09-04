from __future__ import annotations

from pathlib import Path

import frontmatter as fm
import pytest

from coherence.gate.model import Decision, DecisionFile
from coherence.gate.service import resolve_gate
from coherence.gate.store import decision_path, write_decision
from coherence.register.overlap import (
    DEFAULT_K,
    OverlapCandidate,
    generate_candidates,
    has_declared_relation,
    run_overlap_check,
    verify_candidates,
)
from coherence.register.register import AcceptanceCriterion, Requirement, VerificationBinding

pytestmark = pytest.mark.unit

# SR-058/AC-1 + AC-2: cross-FEAT/SR semantic overlap detection at scale.
# See requirements/SR-058.md and coherence/register/overlap.py's own module
# docstring for the design this binds.


def _ac(ac_id: str, criterion: str) -> AcceptanceCriterion:
    return AcceptanceCriterion(
        id=ac_id,
        criterion=criterion,
        verification=VerificationBinding(kind="manual", reason="test fixture"),
    )


def _req(
    sr_id: str,
    statement: str,
    *,
    upstream: list[str] | None = None,
    relates_to: list[str] | None = None,
    acceptance: tuple = (),
) -> Requirement:
    return Requirement(
        id=sr_id,
        title=sr_id,
        statement=statement,
        domain="behavioral",
        upstream=upstream or [],
        binding=None,
        body="",
        path=Path(f"requirements/{sr_id}.md"),
        acceptance=acceptance,
        relates_to=relates_to or [],
    )


def _write_sr(
    root: Path,
    sr_id: str,
    statement: str,
    *,
    upstream: list[str] | None = None,
    relates_to: list[str] | None = None,
) -> None:
    path = root / "requirements" / f"{sr_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        "id": sr_id,
        "title": sr_id,
        "statement": statement,
        "domain": "behavioral",
    }
    if upstream:
        meta["upstream"] = upstream
    if relates_to:
        meta["relates_to"] = relates_to
    path.write_text(fm.dumps(fm.Post("", **meta)), encoding="utf-8")


_STATEMENT_A = (
    "When a requirement is registered, the system shall validate every "
    "acceptance criterion carries a non-blank verification kind before "
    "accepting the requirement into the register."
)
_STATEMENT_A_NEAR_DUP = (
    "When a requirement is registered, the system shall check every "
    "acceptance criterion carries a non-blank verification kind before "
    "accepting the requirement into the register."
)
_STATEMENT_UNRELATED = (
    "When a scheduled cron job misses its window, the operator dashboard "
    "shall render a red banner naming the missed job."
)


# ---------------------------------------------------------------------------
# AC-1: narrowing without O(N^2) candidate growth
# ---------------------------------------------------------------------------


@pytest.mark.sr("SR-058")
def test_narrowing_stays_bounded_not_quadratic():
    """A corpus sized well past what naive O(N^2) pairwise comparison would
    be proportionate for, with every pair maximally similar and undeclared
    (the worst case for candidate growth): candidate count must stay
    O(N*k), never approach the full O(N^2) pairwise set."""
    n = 60
    k = 3
    reqs = [_req(f"SR-{i:03d}", _STATEMENT_A) for i in range(n)]

    candidates, vectors = generate_candidates(reqs, k=k)

    assert len(vectors) == n
    quadratic = n * (n - 1) // 2
    bounded = n * k
    assert len(candidates) <= bounded
    # Sanity: this fixture is deliberately the worst case (every pair
    # maximally similar) -- if the narrowing step were silently falling back
    # to full pairwise output, this assertion is what would catch it.
    assert len(candidates) < quadratic


@pytest.mark.sr("SR-058")
def test_near_duplicate_pair_with_no_declared_relation_is_surfaced():
    reqs = [
        _req("SR-001", _STATEMENT_A),
        _req("SR-002", _STATEMENT_A_NEAR_DUP),
        _req("SR-003", _STATEMENT_UNRELATED),
    ]

    candidates, _ = generate_candidates(reqs, k=DEFAULT_K)

    pairs = {(c.sr_a, c.sr_b) for c in candidates}
    assert ("SR-001", "SR-002") in pairs


@pytest.mark.sr("SR-058")
def test_similar_but_declared_pair_is_excluded():
    reqs = [
        _req("SR-001", _STATEMENT_A, relates_to=["SR-002"]),
        _req("SR-002", _STATEMENT_A_NEAR_DUP),
        _req("SR-003", _STATEMENT_UNRELATED),
    ]

    candidates, _ = generate_candidates(reqs, k=DEFAULT_K)

    pairs = {(c.sr_a, c.sr_b) for c in candidates}
    assert ("SR-001", "SR-002") not in pairs


@pytest.mark.sr("SR-058")
def test_declared_relation_checked_from_either_side():
    """upstream/relates_to declared from EITHER SR excludes the pair --
    relations are not necessarily declared from both sides."""
    a = _req("SR-001", _STATEMENT_A)
    b = _req("SR-002", _STATEMENT_A_NEAR_DUP, upstream=["SR-001"])
    assert has_declared_relation(a, b)
    assert has_declared_relation(b, a)


@pytest.mark.sr("SR-058")
def test_dissimilar_and_undeclared_pair_never_becomes_candidate():
    reqs = [
        _req("SR-001", _STATEMENT_A),
        _req("SR-002", _STATEMENT_UNRELATED),
    ]

    candidates, _ = generate_candidates(reqs, k=DEFAULT_K)

    assert candidates == []


@pytest.mark.sr("SR-058")
def test_vector_cache_reuses_unchanged_fingerprint_and_recomputes_changed():
    reqs = [_req("SR-001", _STATEMENT_A), _req("SR-002", _STATEMENT_UNRELATED)]
    _, vectors = generate_candidates(reqs, k=DEFAULT_K)

    # Re-run with the prior vectors as cache and one SR's text changed: the
    # unchanged SR's cached SrVector object is reused verbatim (identity
    # check), the changed one gets a fresh vector with a different fingerprint.
    changed = [_req("SR-001", _STATEMENT_A), _req("SR-002", "a totally different claim entirely")]
    _, new_vectors = generate_candidates(changed, k=DEFAULT_K, cache=vectors)

    assert new_vectors["SR-001"] is vectors["SR-001"]
    assert new_vectors["SR-002"].fingerprint != vectors["SR-002"].fingerprint


# ---------------------------------------------------------------------------
# AC-2: model verification never lets a dismissed candidate reach a human;
# judge failure degrades explicitly, never silently "no overlap"
# ---------------------------------------------------------------------------


def _candidate(pair_id: str = "SR-001__SR-002") -> OverlapCandidate:
    return OverlapCandidate(
        pair_id=pair_id,
        sr_a="SR-001",
        sr_b="SR-002",
        score=0.9,
        sr_a_statement=_STATEMENT_A,
        sr_b_statement=_STATEMENT_A_NEAR_DUP,
    )


@pytest.mark.sr("SR-058")
def test_verify_candidates_confirmed_and_dismissed_are_distinguished():
    candidates = [_candidate("SR-001__SR-002"), _candidate("SR-003__SR-004")]

    def judge(candidate: OverlapCandidate) -> dict:
        confirmed = candidate.pair_id == "SR-001__SR-002"
        return {"confirmed": confirmed, "rationale": "because", "suggested_relation": None}

    results = verify_candidates(candidates, judge)
    by_pair = {r.candidate.pair_id: r for r in results}
    assert by_pair["SR-001__SR-002"].status == "confirmed"
    assert by_pair["SR-003__SR-004"].status == "dismissed"


@pytest.mark.sr("SR-058")
def test_judge_unavailable_is_never_silently_no_overlap():
    def failing_judge(candidate: OverlapCandidate) -> dict:
        raise RuntimeError("subagent dispatch failed")

    results = verify_candidates([_candidate()], failing_judge)
    assert len(results) == 1
    assert results[0].status == "unavailable"
    assert results[0].status != "dismissed"
    assert results[0].error is not None


@pytest.mark.sr("SR-058")
def test_judge_malformed_output_is_unavailable_not_dismissed():
    results = verify_candidates([_candidate()], lambda c: {"not_confirmed": True})
    assert results[0].status == "unavailable"


# ---------------------------------------------------------------------------
# Full pipeline: dismissed candidates never reach the gate; a confirmed
# candidate's human decision round-trips through the real DecisionFile
# mechanism.
# ---------------------------------------------------------------------------


@pytest.mark.sr("SR-058")
def test_dismissed_candidate_never_produces_a_gate_item(tmp_path: Path):
    _write_sr(tmp_path, "SR-001", _STATEMENT_A)
    _write_sr(tmp_path, "SR-002", _STATEMENT_A_NEAR_DUP)

    run_dir = tmp_path / "overlap-reviews" / "run-1"
    result = run_overlap_check(
        tmp_path,
        run_dir,
        run_id="run-1",
        judge=lambda c: {"confirmed": False, "rationale": "coincidental vocabulary overlap"},
    )

    assert result["candidates"]
    assert all(c["status"] == "dismissed" for c in result["candidates"])
    assert result["gate"] is None
    assert not decision_path(run_dir, "overlap:run-1").exists()


@pytest.mark.sr("SR-058")
def test_confirmed_candidate_blocks_until_a_decision_is_authored(tmp_path: Path):
    _write_sr(tmp_path, "SR-001", _STATEMENT_A)
    _write_sr(tmp_path, "SR-002", _STATEMENT_A_NEAR_DUP)

    run_dir = tmp_path / "overlap-reviews" / "run-1"
    result = run_overlap_check(
        tmp_path,
        run_dir,
        run_id="run-1",
        judge=lambda c: {"confirmed": True, "rationale": "same behavioral claim"},
    )

    assert result["gate"]["status"] == "blocked"
    item_ids = result["gate"]["items"]
    assert item_ids == ["overlap:run-1:candidate:SR-001__SR-002"]

    # Unattended, still no decision: hard-blocked, never auto-finalised.
    unattended = run_overlap_check(
        tmp_path,
        run_dir,
        run_id="run-1",
        judge=lambda c: {"confirmed": True, "rationale": "same behavioral claim"},
        unattended=True,
    )
    assert unattended["gate"]["status"] == "blocked_unattended"


@pytest.mark.sr("SR-058")
def test_human_accept_decision_round_trips_through_decision_file(tmp_path: Path):
    _write_sr(tmp_path, "SR-001", _STATEMENT_A)
    _write_sr(tmp_path, "SR-002", _STATEMENT_A_NEAR_DUP)

    run_dir = tmp_path / "overlap-reviews" / "run-1"
    judge = lambda c: {  # noqa: E731
        "confirmed": True,
        "rationale": "same behavioral claim",
        "suggested_relation": "SR-002 should declare relates_to SR-001",
    }
    first = run_overlap_check(tmp_path, run_dir, run_id="run-1", judge=judge)
    item_id = first["gate"]["items"][0]
    assert item_id == "overlap:run-1:candidate:SR-001__SR-002"

    # A human resolves the candidate through the EXISTING DecisionFile
    # mechanism -- accepting the overlap and recording, in `reason`, the
    # relation they judge it needs (captured as information, never
    # auto-written into either SR's frontmatter).
    write_decision(
        run_dir,
        DecisionFile(
            gate_id="overlap:run-1",
            artifact_ref="overlap:run-1",
            decisions=(
                Decision(
                    item_id=item_id,
                    action="accept",
                    reason="Confirmed overlap; SR-002 should declare relates_to SR-001",
                    decided_by="human-reviewer",
                ),
            ),
            decided_at="2026-09-04T00:00:00Z",
            decided_by="human-reviewer",
        ),
    )

    second = run_overlap_check(tmp_path, run_dir, run_id="run-1", judge=judge)
    assert second["gate"]["status"] == "accept"
    decided = second["gate"]["decisions"]["decisions"][0]
    assert decided["item_id"] == item_id
    assert decided["action"] == "accept"
    assert "relates_to SR-001" in decided["reason"]

    # The same item id resolves through coherence.gate.service directly too
    # -- this is the real, unmodified gate mechanism, not a parallel one.
    assert resolve_gate(run_dir, "overlap:run-1", unattended=False) == "accept"


@pytest.mark.sr("SR-058")
def test_human_reject_decision_requires_reason_per_existing_gate_rules(tmp_path: Path):
    """AC-2's decision capture reuses the EXISTING DecisionFile validation
    rules unmodified: reject/defer still require a non-blank reason."""
    from coherence.gate.model import Decision, DecisionValidationError

    with pytest.raises(DecisionValidationError):
        DecisionFile(
            gate_id="overlap:run-1",
            decisions=(Decision(item_id="overlap:run-1:candidate:SR-001__SR-002", action="reject"),),
            decided_at="2026-09-04T00:00:00Z",
            decided_by="human-reviewer",
        )
