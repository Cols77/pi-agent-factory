"""Tests for factory.system.models: claim classes, freshness, and the

§3.2 coupling rule (kind == missing iff freshness.state == n/a), enforced
in both the dataclasses and the JSON schemas.
"""
from __future__ import annotations

import json

import pytest

from factory.system.models import (
    ClaimClass,
    DecisionTimelineEvent,
    Freshness,
    FreshnessDependency,
    FreshnessState,
    MatrixStatus,
    Span,
    SystemCitation,
    SystemClaim,
    SystemGuide,
    SystemScopeRef,
    TimelineAction,
    TimelineActor,
    ValidationMatrixRow,
    CitationKind,
    to_dict,
)
from factory.validation.schema_validator import SCHEMA_DIR, validate

pytestmark = pytest.mark.unit

CLAIM_SCHEMA = SCHEMA_DIR / "system_claim.schema.json"
MATRIX_ROW_SCHEMA = SCHEMA_DIR / "system_matrix_row.schema.json"
TIMELINE_EVENT_SCHEMA = SCHEMA_DIR / "system_timeline_event.schema.json"


def _fresh(state: FreshnessState = FreshnessState.FRESH) -> Freshness:
    return Freshness(state=state, reason=None, dependencies=[])


def _citation(**overrides) -> SystemCitation:
    defaults = dict(kind=CitationKind.MANIFEST, path="evidence/runs/r1.json", sha256=None, anchor=None)
    defaults.update(overrides)
    return SystemCitation(**defaults)


# ---------------------------------------------------------------------------
# Claim-class preservation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "freshness_state"),
    [
        (ClaimClass.RECORDED, FreshnessState.FRESH),
        (ClaimClass.DERIVED, FreshnessState.STALE),
        (ClaimClass.SYNTHESIZED, FreshnessState.DEGRADED),
        (ClaimClass.MISSING, FreshnessState.NA),
    ],
)
def test_claim_class_is_preserved(kind, freshness_state):
    claim = SystemClaim(kind=kind, text="x", freshness=_fresh(freshness_state))
    assert claim.kind is kind
    assert claim.freshness.state is freshness_state


def test_all_four_claim_classes_exist():
    assert {c.value for c in ClaimClass} == {"recorded", "derived", "synthesized", "missing"}


# ---------------------------------------------------------------------------
# Freshness states
# ---------------------------------------------------------------------------


def test_all_four_freshness_states_exist():
    assert {s.value for s in FreshnessState} == {"fresh", "stale", "degraded", "n/a"}


def test_freshness_holds_dependencies():
    dep = FreshnessDependency(name="x", expected="a", actual="b")
    fr = Freshness(state=FreshnessState.STALE, reason="input changed", dependencies=[dep])
    assert fr.dependencies == [dep]


# ---------------------------------------------------------------------------
# Coupling rule -- both directions, dataclass-enforced
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "freshness_state",
    [FreshnessState.FRESH, FreshnessState.STALE, FreshnessState.DEGRADED],
)
def test_missing_kind_requires_na_freshness(freshness_state):
    with pytest.raises(ValueError):
        SystemClaim(kind=ClaimClass.MISSING, text="x", freshness=_fresh(freshness_state))


@pytest.mark.parametrize(
    "kind",
    [ClaimClass.RECORDED, ClaimClass.DERIVED, ClaimClass.SYNTHESIZED],
)
def test_na_freshness_requires_missing_kind(kind):
    with pytest.raises(ValueError):
        SystemClaim(kind=kind, text="x", freshness=_fresh(FreshnessState.NA))


def test_missing_kind_with_na_freshness_is_legal():
    claim = SystemClaim(kind=ClaimClass.MISSING, text="x", freshness=_fresh(FreshnessState.NA))
    assert claim.kind is ClaimClass.MISSING
    assert claim.freshness.state is FreshnessState.NA


# ---------------------------------------------------------------------------
# Coupling rule -- both directions, schema-enforced
# ---------------------------------------------------------------------------


def _claim_dict(kind: str, freshness_state: str, **extra) -> dict:
    base = {
        "kind": kind,
        "text": "x",
        "citations": [],
        "spans": [],
        "freshness": {"state": freshness_state, "reason": None, "dependencies": []},
    }
    base.update(extra)
    return base


@pytest.mark.parametrize(
    "freshness_state", ["fresh", "stale", "degraded"],
)
def test_schema_rejects_missing_kind_without_na_freshness(freshness_state):
    errors = validate(_claim_dict("missing", freshness_state), CLAIM_SCHEMA)
    assert errors


@pytest.mark.parametrize("kind", ["recorded", "derived", "synthesized"])
def test_schema_rejects_na_freshness_without_missing_kind(kind):
    errors = validate(_claim_dict(kind, "n/a"), CLAIM_SCHEMA)
    assert errors


def test_schema_accepts_missing_kind_with_na_freshness():
    assert validate(_claim_dict("missing", "n/a"), CLAIM_SCHEMA) == []


def test_schema_accepts_every_legal_cell():
    for kind in ("recorded", "derived", "synthesized"):
        for state in ("fresh", "stale", "degraded"):
            assert validate(_claim_dict(kind, state), CLAIM_SCHEMA) == []


# ---------------------------------------------------------------------------
# Top-level schema rejection of unknown fields
# ---------------------------------------------------------------------------


def test_claim_schema_rejects_unknown_top_level_field():
    instance = _claim_dict("recorded", "fresh", extra_field="not allowed")
    assert validate(instance, CLAIM_SCHEMA)


def test_matrix_row_schema_rejects_unknown_top_level_field():
    instance = _matrix_row_dict(status="passed")
    instance["rationale"] = "not allowed"
    assert validate(instance, MATRIX_ROW_SCHEMA)


def test_timeline_event_schema_rejects_unknown_top_level_field():
    instance = _timeline_event_dict()
    instance["notes"] = "not allowed"
    assert validate(instance, TIMELINE_EVENT_SCHEMA)


# ---------------------------------------------------------------------------
# Citation retention and anchor round-tripping
# ---------------------------------------------------------------------------


def test_citation_round_trips_through_json():
    citation = SystemCitation(kind=CitationKind.VALIDATION, path="reports/v1.json", sha256="a" * 64, anchor="L10-L20")
    payload = json.loads(json.dumps(to_dict(citation)))
    rebuilt = SystemCitation(
        kind=CitationKind(payload["kind"]),
        path=payload["path"],
        sha256=payload["sha256"],
        anchor=payload["anchor"],
    )
    assert rebuilt == citation
    assert rebuilt.anchor == "L10-L20"


def test_claim_retains_all_citations_in_order():
    citations = [_citation(path="a"), _citation(path="b"), _citation(path="c")]
    claim = SystemClaim(kind=ClaimClass.RECORDED, text="x", freshness=_fresh(), citations=citations)
    assert [c.path for c in claim.citations] == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# spans allowed only on synthesized records
# ---------------------------------------------------------------------------


def test_spans_allowed_on_synthesized():
    claim = SystemClaim(
        kind=ClaimClass.SYNTHESIZED,
        text="x",
        freshness=_fresh(),
        citations=[_citation()],
        spans=[Span(text="verbatim", citation_index=0)],
    )
    assert claim.spans[0].text == "verbatim"


@pytest.mark.parametrize("kind", [ClaimClass.RECORDED, ClaimClass.DERIVED])
def test_spans_rejected_on_non_synthesized(kind):
    with pytest.raises(ValueError):
        SystemClaim(
            kind=kind,
            text="x",
            freshness=_fresh(),
            citations=[_citation()],
            spans=[Span(text="verbatim", citation_index=0)],
        )


def test_span_citation_index_out_of_range_rejected():
    with pytest.raises(ValueError):
        SystemClaim(
            kind=ClaimClass.SYNTHESIZED,
            text="x",
            freshness=_fresh(),
            citations=[_citation()],
            spans=[Span(text="verbatim", citation_index=5)],
        )


def test_schema_rejects_spans_on_non_synthesized_kind():
    instance = _claim_dict("recorded", "fresh", spans=[{"text": "x", "citation_index": 0}])
    assert validate(instance, CLAIM_SCHEMA)


def test_schema_accepts_empty_spans_on_recorded():
    assert validate(_claim_dict("recorded", "fresh", spans=[]), CLAIM_SCHEMA) == []


def test_schema_accepts_spans_on_synthesized():
    instance = _claim_dict(
        "synthesized",
        "fresh",
        citations=[{"kind": "manifest", "path": "a", "sha256": None, "anchor": None}],
        spans=[{"text": "x", "citation_index": 0}],
    )
    assert validate(instance, CLAIM_SCHEMA) == []


# ---------------------------------------------------------------------------
# Matrix row status enum -- no "stale"/"missing" in status
# ---------------------------------------------------------------------------


def _matrix_row_dict(status: str) -> dict:
    return {
        "subject": {"kind": "sr", "ref": "sr:SR-001"},
        "status": status,
        "evidence": [],
        "freshness": {"state": "fresh", "reason": None, "dependencies": []},
        "summary": "",
    }


@pytest.mark.parametrize("status", ["passed", "failed", "error", "blocked", "never-run"])
def test_matrix_row_accepts_legal_status(status):
    assert validate(_matrix_row_dict(status), MATRIX_ROW_SCHEMA) == []


@pytest.mark.parametrize("status", ["stale", "missing"])
def test_matrix_row_schema_rejects_stale_and_missing_status(status):
    assert validate(_matrix_row_dict(status), MATRIX_ROW_SCHEMA)


def test_matrix_status_enum_has_no_stale_or_missing():
    values = {s.value for s in MatrixStatus}
    assert "stale" not in values
    assert "missing" not in values
    assert values == {"passed", "failed", "error", "blocked", "never-run"}


def test_validation_matrix_row_round_trips():
    row = ValidationMatrixRow(
        subject=SystemScopeRef(kind="sr", ref="sr:SR-001"),
        status=MatrixStatus.PASSED,
        evidence=["reports/v1.json"],
        freshness=_fresh(),
        summary="all green",
    )
    payload = to_dict(row)
    assert validate(payload, MATRIX_ROW_SCHEMA) == []


# ---------------------------------------------------------------------------
# Timeline event ordering fields
# ---------------------------------------------------------------------------


def _timeline_event_dict(at="2026-08-08T12:00:00Z", sequence=None) -> dict:
    return {
        "at": at,
        "sequence": sequence,
        "actor": "human",
        "action": "approved",
        "subject": {"kind": "task", "ref": "task:T-001"},
        "citation": {"kind": "decision", "path": "decisions/d1.json", "sha256": None, "anchor": None},
        "freshness": {"state": "fresh", "reason": None, "dependencies": []},
    }


def test_timeline_event_orders_by_at():
    event = DecisionTimelineEvent(
        actor=TimelineActor.HUMAN,
        action=TimelineAction.APPROVED,
        subject=SystemScopeRef(kind="task", ref="task:T-001"),
        citation=_citation(kind=CitationKind.DECISION, path="decisions/d1.json"),
        freshness=_fresh(),
        at="2026-08-08T12:00:00Z",
    )
    assert event.at == "2026-08-08T12:00:00Z"
    assert event.sequence is None


def test_timeline_event_falls_back_to_sequence():
    event = DecisionTimelineEvent(
        actor=TimelineActor.UNKNOWN,
        action=TimelineAction.NOT_RECORDED,
        subject=SystemScopeRef(kind="task", ref="task:T-001"),
        citation=_citation(kind=CitationKind.DECISION, path="decisions/d1.json"),
        freshness=Freshness(state=FreshnessState.DEGRADED, reason="no timestamp recorded", dependencies=[]),
        sequence=3,
    )
    assert event.sequence == 3
    assert event.at is None


def test_timeline_event_requires_at_or_sequence():
    with pytest.raises(ValueError):
        DecisionTimelineEvent(
            actor=TimelineActor.UNKNOWN,
            action=TimelineAction.NOT_RECORDED,
            subject=SystemScopeRef(kind="task", ref="task:T-001"),
            citation=_citation(kind=CitationKind.DECISION, path="decisions/d1.json"),
            freshness=_fresh(FreshnessState.DEGRADED),
        )


def test_timeline_schema_accepts_at_only():
    assert validate(_timeline_event_dict(at="2026-08-08T12:00:00Z", sequence=None), TIMELINE_EVENT_SCHEMA) == []


def test_timeline_schema_accepts_sequence_only():
    assert validate(_timeline_event_dict(at=None, sequence=3), TIMELINE_EVENT_SCHEMA) == []


def test_timeline_schema_rejects_neither_at_nor_sequence():
    assert validate(_timeline_event_dict(at=None, sequence=None), TIMELINE_EVENT_SCHEMA)


def test_timeline_schema_rejects_bad_datetime_format():
    assert validate(_timeline_event_dict(at="not-a-date", sequence=None), TIMELINE_EVENT_SCHEMA)


# ---------------------------------------------------------------------------
# SystemGuide -- narrow shape check (no guide logic in this task)
# ---------------------------------------------------------------------------


def test_system_guide_holds_scope_and_claim_sections():
    guide = SystemGuide(
        scope=SystemScopeRef(kind="bundle", ref="bundle:example"),
        sections=[SystemClaim(kind=ClaimClass.RECORDED, text="x", freshness=_fresh())],
    )
    assert guide.scope.ref == "bundle:example"
    assert len(guide.sections) == 1


# ---------------------------------------------------------------------------
# Plan checkboxes are never classified `recorded` -- no such helper exists
# to misuse; guard the model surface stays narrow.
# ---------------------------------------------------------------------------


def test_no_fuzzy_or_extra_claim_classes_leak_in():
    # ClaimClass must stay exactly the four defined classes -- nothing like a
    # "checked"/"unchecked" plan-box state can be smuggled in as a claim kind.
    assert len(ClaimClass) == 4
