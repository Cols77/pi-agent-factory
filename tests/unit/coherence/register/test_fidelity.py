from __future__ import annotations

import pytest

from coherence.register.fidelity import FidelityJudgeUnavailable, review_fidelity
from coherence.register.fidelity_packet import (
    AcceptanceCriterionRef,
    FidelityPacket,
    IndexSignatureView,
    ResolvedProductionRef,
    ResolvedValidationRef,
)

pytestmark = pytest.mark.unit

# SR-050/AC-4 (T5.3): one fixture per the plan's own test list -- each a
# hand-built FidelityPacket + a stub judge returning a fixed verdict, so
# these tests never depend on a real model call.

_IMPL = ResolvedProductionRef(
    path="src/widgets/feature.py",
    symbol="widgets.feature:feature_context",
    signature=IndexSignatureView(kind="function", name="feature_context", signature="def feature_context()", summary=""),
    source_excerpt="def feature_context(): return 1",
)
_VER = ResolvedValidationRef(
    path="tests/unit/test_feature.py",
    test="tests/unit/test_feature.py::test_feature_context",
    signature=IndexSignatureView(kind="function", name="test_feature_context", signature="def test_feature_context()", summary=""),
    source_excerpt="def test_feature_context(): assert True",
    outcome=None,
)


def _packet(*, profile: str = "prototype", acceptance: tuple = (), implemented=(_IMPL,), verified=(_VER,)) -> FidelityPacket:
    return FidelityPacket(
        sr_id="SR-900",
        statement="the system shall provide feature context",
        acceptance=acceptance,
        design_source=None,
        profile=profile,
        implemented=implemented,
        verified=verified,
        import_overlap=(),
        unresolved=(),
    )


def _relation(field: str = "implemented_by") -> dict:
    if field == "implemented_by":
        return {"field": "implemented_by", "path": _IMPL.path, "identity": _IMPL.symbol}
    return {"field": "verified_by", "path": _VER.path, "identity": _VER.test}


@pytest.mark.sr("SR-050")
def test_supported_link_produces_no_finding():
    packet = _packet()
    result = review_fidelity(packet, judge=lambda p: [])
    assert result.status == "ok"
    assert result.findings == ()


@pytest.mark.sr("SR-050")
def test_overstated_link_round_trips_and_lands_open_under_high_assurance():
    packet = _packet(profile="high_assurance")
    candidate = {
        "kind": "overstated_link",
        "relation": _relation(),
        "confidence": 0.7,
        "citations": [f"{_IMPL.path}#{_IMPL.symbol}"],
        "rationale": "the linked symbol only covers part of the claimed behavior",
        "acceptance_ref": None,
    }
    result = review_fidelity(packet, judge=lambda p: [candidate])
    assert result.status == "ok"
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.kind == "overstated_link"
    assert finding.status == "open"


@pytest.mark.sr("SR-050")
def test_weaker_subset_test_citation_includes_the_specific_test_node():
    ac = AcceptanceCriterionRef(id="AC-1", criterion="handles both the happy path and the error path", verification_kind="test_marker")
    packet = _packet(acceptance=(ac,))
    candidate = {
        "kind": "weaker_subset_test",
        "relation": _relation("verified_by"),
        "confidence": 0.6,
        "citations": [f"{_VER.path}::{_VER.test.rsplit('::', 1)[-1]}"],
        "rationale": "the test only exercises the happy path, not the error path AC-1 also names",
        "acceptance_ref": "AC-1",
    }
    result = review_fidelity(packet, judge=lambda p: [candidate])
    assert result.status == "ok"
    finding = result.findings[0]
    assert finding.kind == "weaker_subset_test"
    assert any(_VER.test.rsplit("::", 1)[-1] in c for c in finding.citations)


@pytest.mark.sr("SR-050")
def test_incidental_helper_link():
    candidate = {
        "kind": "incidental_helper",
        "relation": _relation(),
        "confidence": 0.65,
        "citations": [f"{_IMPL.path}#{_IMPL.symbol}"],
        "rationale": "feature_context is a genuinely-called utility, not the behavior owner",
        "acceptance_ref": None,
    }
    result = review_fidelity(_packet(), judge=lambda p: [candidate])
    assert result.findings[0].kind == "incidental_helper"


@pytest.mark.sr("SR-050")
def test_high_assurance_vs_normal_disposition():
    candidate = {
        "kind": "overstated_link",
        "relation": _relation(),
        "confidence": 0.5,
        "citations": [f"{_IMPL.path}#{_IMPL.symbol}"],
        "rationale": "r",
        "acceptance_ref": None,
    }
    ha_result = review_fidelity(_packet(profile="high_assurance"), judge=lambda p: [dict(candidate)])
    normal_result = review_fidelity(_packet(profile="prototype"), judge=lambda p: [dict(candidate)])
    assert ha_result.findings[0].status == "open"
    assert normal_result.findings[0].status == "escalated"


@pytest.mark.sr("SR-050")
def test_missing_link_compound_fixture():
    ac = AcceptanceCriterionRef(id="AC-2", criterion="also handles the timeout case", verification_kind="test_marker")
    packet = _packet(acceptance=(ac,))
    candidate = {
        "kind": "missing_link_compound",
        "relation": _relation(),
        "confidence": 0.8,
        "citations": [f"{_IMPL.path}#{_IMPL.symbol}"],
        "rationale": "no declared relation covers AC-2's timeout clause",
        "acceptance_ref": "AC-2",
    }
    result = review_fidelity(packet, judge=lambda p: [candidate])
    assert result.status == "ok"
    finding = result.findings[0]
    assert finding.kind == "missing_link_compound"
    assert finding.acceptance_ref == "AC-2"


@pytest.mark.sr("SR-050")
def test_different_behavior_fixture():
    candidate = {
        "kind": "different_behavior",
        "relation": _relation("verified_by"),
        "confidence": 0.9,
        "citations": [f"{_VER.path}::test_feature_context"],
        "rationale": "the test exercises an unrelated code path entirely",
        "acceptance_ref": None,
    }
    result = review_fidelity(_packet(), judge=lambda p: [candidate])
    assert result.findings[0].kind == "different_behavior"


@pytest.mark.sr("SR-050")
def test_judge_raising_yields_unavailable_status_not_empty_findings():
    def _judge(p):
        raise FidelityJudgeUnavailable("subagent dispatch failed")

    result = review_fidelity(_packet(), judge=_judge)
    assert result.status == "unavailable"
    assert result.error is not None
    assert result.findings == ()


@pytest.mark.sr("SR-050")
def test_judge_returning_malformed_output_yields_unavailable_status():
    result = review_fidelity(_packet(), judge=lambda p: "not a list")
    assert result.status == "unavailable"
    assert result.findings == ()


@pytest.mark.sr("SR-050")
def test_judge_returning_a_hallucinated_relation_yields_unavailable_status():
    candidate = {
        "kind": "overstated_link",
        "relation": {"field": "implemented_by", "path": "src/does-not-exist.py", "identity": "x:y"},
        "confidence": 0.5,
        "citations": ["src/does-not-exist.py#x:y"],
        "rationale": "r",
        "acceptance_ref": None,
    }
    result = review_fidelity(_packet(), judge=lambda p: [candidate])
    assert result.status == "unavailable"
    assert result.findings == ()

# default_judge (the real PiAgentBackend-dispatch implementation, open
# design question #4) lives in coherence.audit.fidelity_dispatch, not this
# module -- see coherence/register/fidelity.py's own "Layering" docstring
# section for why. Its tests live at
# tests/unit/coherence/test_fidelity_dispatch.py, matching that home.
