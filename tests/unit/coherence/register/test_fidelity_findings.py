from __future__ import annotations

import pytest

from coherence.register.fidelity_findings import (
    FidelityFinding,
    FidelityFindingError,
    FidelityReviewResult,
    RelationRef,
    build_finding,
)
from coherence.register.fidelity_packet import (
    FidelityPacket,
    IndexSignatureView,
    ResolvedProductionRef,
    ResolvedValidationRef,
)

pytestmark = pytest.mark.unit


def _packet(**overrides) -> FidelityPacket:
    base = dict(
        sr_id="SR-900",
        statement="s",
        acceptance=(),
        design_source=None,
        profile="prototype",
        implemented=(
            ResolvedProductionRef(
                path="src/a.py",
                symbol="a:f",
                signature=IndexSignatureView(kind="function", name="f", signature="def f()", summary=""),
                source_excerpt="def f(): return 1",
            ),
        ),
        verified=(
            ResolvedValidationRef(
                path="tests/test_a.py",
                test="tests/test_a.py::test_f",
                signature=IndexSignatureView(
                    kind="function", name="test_f", signature="def test_f()", summary=""
                ),
                source_excerpt="def test_f(): assert True",
                outcome=None,
            ),
        ),
        import_overlap=(),
        unresolved=(),
    )
    base.update(overrides)
    return FidelityPacket(**base)


def _kwargs(**overrides) -> dict:
    base = dict(
        sr_id="SR-900",
        kind="overstated_link",
        relation=RelationRef(field="implemented_by", path="src/a.py", identity="a:f"),
        confidence=0.8,
        citations=("src/a.py#a:f",),
        rationale="the linked symbol only covers a subset of the claim",
        acceptance_ref=None,
        status="open",
        produced_at="2026-09-03T00:00:00Z",
        produced_by_run="run-1",
    )
    base.update(overrides)
    return base


def test_a_finding_with_empty_citations_is_rejected_at_construction():
    with pytest.raises(FidelityFindingError):
        FidelityFinding(**_kwargs(citations=()))


def test_a_finding_whose_relation_does_not_match_the_packet_is_rejected():
    packet = _packet()
    bad_relation = RelationRef(field="implemented_by", path="src/does-not-exist.py", identity="x:y")
    with pytest.raises(FidelityFindingError):
        build_finding(packet, **_kwargs(relation=bad_relation))


def test_a_finding_whose_relation_matches_the_packet_is_accepted():
    packet = _packet()
    finding = build_finding(packet, **_kwargs())
    assert finding.relation.path == "src/a.py"


def test_missing_link_compound_is_rejected_for_a_packet_with_no_acceptance():
    """Open design question #5: `missing_link_compound` names a partial-
    coverage gap in a declared `acceptance:` list -- an SR with no
    `acceptance:` block at all (`packet.acceptance == ()`) has no compound
    claim to check, so `build_finding` must reject the kind at construction
    time rather than let it land as an ordinary finding."""
    packet = _packet(acceptance=())
    with pytest.raises(FidelityFindingError):
        build_finding(packet, **_kwargs(kind="missing_link_compound"))


def test_missing_link_compound_is_accepted_for_a_packet_with_acceptance():
    from coherence.register.fidelity_packet import AcceptanceCriterionRef

    packet = _packet(
        acceptance=(AcceptanceCriterionRef(id="AC-1", criterion="c", verification_kind="test"),)
    )
    finding = build_finding(packet, **_kwargs(kind="missing_link_compound", acceptance_ref="AC-1"))
    assert finding.kind == "missing_link_compound"


def test_confidence_outside_bounds_is_rejected():
    with pytest.raises(FidelityFindingError):
        FidelityFinding(**_kwargs(confidence=1.5))
    with pytest.raises(FidelityFindingError):
        FidelityFinding(**_kwargs(confidence=-0.1))


def test_blank_rationale_is_rejected():
    with pytest.raises(FidelityFindingError):
        FidelityFinding(**_kwargs(rationale="   "))


def test_unknown_kind_is_rejected():
    with pytest.raises(FidelityFindingError):
        FidelityFinding(**_kwargs(kind="not_a_real_kind"))


def test_finding_round_trips_through_json_shape_losslessly():
    finding = FidelityFinding(**_kwargs())
    restored = FidelityFinding.from_dict(finding.to_dict())
    assert restored == finding


def test_review_result_round_trips_through_json_shape_losslessly():
    from coherence.register.relations import ReferenceIssue

    finding = FidelityFinding(**_kwargs())
    result = FidelityReviewResult(
        sr_id="SR-900",
        profile="high_assurance",
        findings=(finding,),
        unresolved=(ReferenceIssue(field="verified_by", index=0, detail="dangling"),),
        run_id="run-1",
        produced_at="2026-09-03T00:00:00Z",
        status="ok",
        error=None,
    )
    restored = FidelityReviewResult.from_dict(result.to_dict())
    assert restored == result


def test_unavailable_result_carries_a_distinct_status_not_an_empty_findings_tuple():
    result = FidelityReviewResult(
        sr_id="SR-900",
        profile="prototype",
        findings=(),
        unresolved=(),
        run_id="run-1",
        produced_at="2026-09-03T00:00:00Z",
        status="unavailable",
        error="judge dispatch failed",
    )
    assert result.status == "unavailable"
    assert result.error == "judge dispatch failed"
