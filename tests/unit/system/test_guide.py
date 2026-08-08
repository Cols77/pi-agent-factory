"""Tests for factory.system.guide: grounded prose synthesis (design SS4.4).

Every claim this module asserts traces back to one of:
- verbatim containment (a synthesized span must be found, character for
  character, inside the file its citation points at);
- the binary collapse predicate (all supporting dependencies fresh -> prose,
  anything else -> recorded bullets, never a hedged middle state);
- determinism (same repo content in, byte-identical dict out);
- no model invocation (this module never imports an LLM SDK or makes a
  network call).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from factory.system import guide as guide_module
from factory.system.guide import query_guide
from factory.system.models import SystemScopeRef
from factory.validation.schema_validator import SCHEMA_DIR, validate

from ._fixtures import (
    write_bundle,
    write_decision_artifact,
    write_sr,
    write_task,
    write_validation_report,
)

pytestmark = pytest.mark.unit

CLAIM_SCHEMA = SCHEMA_DIR / "system_claim.schema.json"


def _section(result: dict, index: int) -> dict:
    return result["sections"][index]


def _citation_for_span(section: dict, span: dict) -> dict:
    return section["citations"][span["citation_index"]]


# ---------------------------------------------------------------------------
# The `_verbatim_span` primitive: the one place a `Span` can be created.
# ---------------------------------------------------------------------------


def test_verbatim_span_accepts_text_actually_present_in_the_cited_file(tmp_path):
    source = tmp_path / "source.md"
    source.write_text("Some recorded text lives here.", encoding="utf-8")

    span = guide_module._verbatim_span("recorded text", str(source), citation_index=0)

    assert span is not None
    assert span.text == "recorded text"
    assert span.citation_index == 0
    # The independent verbatim check this test is pinning down.
    assert span.text in source.read_text(encoding="utf-8")


def test_verbatim_span_rejects_text_not_present_in_the_cited_file(tmp_path):
    # This is the "no paraphrase path exists" guarantee at its source: a
    # candidate that is not a literal substring of the cited file can never
    # become a `Span`, no matter how close it reads.
    source = tmp_path / "source.md"
    source.write_text("Some recorded text lives here.", encoding="utf-8")

    span = guide_module._verbatim_span("some reworded phrasing", str(source), citation_index=0)

    assert span is None


def test_verbatim_span_rejects_empty_candidate(tmp_path):
    source = tmp_path / "source.md"
    source.write_text("anything", encoding="utf-8")
    assert guide_module._verbatim_span("", str(source), citation_index=0) is None


def test_verbatim_span_rejects_unreadable_source_path():
    assert guide_module._verbatim_span("text", "/nonexistent/path/for/this/test.md", citation_index=0) is None


# ---------------------------------------------------------------------------
# Identity section: synthesized prose when fresh, span verified against the
# scope's own declaration file.
# ---------------------------------------------------------------------------


def test_bundle_identity_section_is_synthesized_with_span_verified_against_bundle_file(tmp_path):
    write_bundle(tmp_path / "bundles", "b1", "Evidence Lifecycle Bundle", [])

    result = query_guide(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:b1"))
    identity = _section(result, 0)

    assert validate(identity, CLAIM_SCHEMA) == []
    assert identity["kind"] == "synthesized"
    assert identity["freshness"]["state"] == "fresh"
    assert len(identity["spans"]) == 1
    span = identity["spans"][0]
    assert span["text"] == "Evidence Lifecycle Bundle"
    citation = _citation_for_span(identity, span)
    source_text = Path(citation["path"]).read_text(encoding="utf-8")
    assert span["text"] in source_text  # verbatim containment, asserted directly


def test_sr_identity_section_is_synthesized_with_span_verified_against_requirement_file(tmp_path):
    write_sr(tmp_path / "requirements", "SR-001", statement="When X happens, the system shall Y.")

    result = query_guide(tmp_path, SystemScopeRef(kind="sr", ref="sr:SR-001"))
    identity = _section(result, 0)

    assert validate(identity, CLAIM_SCHEMA) == []
    assert identity["kind"] == "synthesized"
    assert identity["freshness"]["state"] == "fresh"
    span = identity["spans"][0]
    assert span["text"] == "When X happens, the system shall Y."
    citation = _citation_for_span(identity, span)
    source_text = Path(citation["path"]).read_text(encoding="utf-8")
    assert span["text"] in source_text


# ---------------------------------------------------------------------------
# Coverage section: prose when every task member resolves; bullets the
# moment one does not (missing support degrades, never fabricates).
# ---------------------------------------------------------------------------


def test_bundle_coverage_section_is_synthesized_when_all_task_members_resolve(tmp_path):
    write_bundle(tmp_path / "bundles", "b1", "Bundle", ["task:T-001"])
    write_task(tmp_path / "tasks", "T-001", title="Implement the thing", status="done")

    result = query_guide(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:b1"))
    coverage = _section(result, 1)

    assert validate(coverage, CLAIM_SCHEMA) == []
    assert coverage["kind"] == "synthesized"
    assert coverage["freshness"]["state"] == "fresh"
    assert len(coverage["spans"]) == 1
    span = coverage["spans"][0]
    assert span["text"] == "Implement the thing"
    citation = _citation_for_span(coverage, span)
    assert span["text"] in Path(citation["path"]).read_text(encoding="utf-8")


def test_bundle_coverage_section_collapses_to_bullets_when_a_task_member_is_missing(tmp_path):
    # design SS4.4/brief: "missing support degrades to bullets rather than
    # fabricating confidence".
    write_bundle(tmp_path / "bundles", "b1", "Bundle", ["task:T-001", "task:T-999"])
    write_task(tmp_path / "tasks", "T-001", title="Implement the thing", status="done")
    # T-999 is never written -- an unresolved member.

    result = query_guide(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:b1"))
    coverage = _section(result, 1)

    assert validate(coverage, CLAIM_SCHEMA) == []
    assert coverage["kind"] == "recorded"
    assert coverage["spans"] == []
    assert coverage["freshness"]["state"] == "degraded"
    assert "task:T-999" in coverage["text"]


# ---------------------------------------------------------------------------
# Validation section: the collapse predicate is binary, driven by real
# staleness -- not a graduated/hedged state.
# ---------------------------------------------------------------------------


def test_validation_section_is_synthesized_when_validation_is_fresh(tmp_path):
    write_sr(tmp_path / "requirements", "SR-001", statement="When X happens, the system shall Y.")
    write_validation_report(tmp_path, [{"id": "SR-001", "passed": True, "stale": False, "artifacts": []}])

    result = query_guide(tmp_path, SystemScopeRef(kind="sr", ref="sr:SR-001"))
    validation = _section(result, 2)

    assert validate(validation, CLAIM_SCHEMA) == []
    assert validation["kind"] == "synthesized"
    assert validation["freshness"]["state"] == "fresh"
    span = validation["spans"][0]
    assert span["text"] == "When X happens, the system shall Y."
    citation = _citation_for_span(validation, span)
    assert span["text"] in Path(citation["path"]).read_text(encoding="utf-8")


def test_validation_section_collapses_to_bullets_when_validation_is_stale(tmp_path):
    write_sr(tmp_path / "requirements", "SR-001", statement="When X happens, the system shall Y.")
    write_validation_report(tmp_path, [{"id": "SR-001", "passed": True, "stale": True, "artifacts": []}])

    result = query_guide(tmp_path, SystemScopeRef(kind="sr", ref="sr:SR-001"))
    validation = _section(result, 2)

    assert validate(validation, CLAIM_SCHEMA) == []
    assert validation["kind"] == "recorded"
    assert validation["spans"] == []
    assert validation["freshness"]["state"] == "stale"
    # There is no partially-hedged prose: a stale dependency never leaves a
    # synthesized paragraph on screen.
    assert "synthesized" != validation["kind"]


def test_validation_section_collapses_to_bullets_when_never_validated(tmp_path):
    write_sr(tmp_path / "requirements", "SR-001")
    # No validation report at all -- the matrix still yields one real
    # "never-run" row (design SS8), so this is bullets, not `missing`
    # (`_validation_section`'s `missing` branch only fires on zero rows).
    result = query_guide(tmp_path, SystemScopeRef(kind="sr", ref="sr:SR-001"))
    validation = _section(result, 2)

    assert validate(validation, CLAIM_SCHEMA) == []
    assert validation["kind"] == "recorded"
    assert validation["spans"] == []
    # A `recorded` claim may never carry `n/a` (SS3.2 coupling rule): a
    # missing/n/a matrix row rolls up to `degraded` for the aggregate, not
    # `n/a` -- `_aggregate_freshness` enforces this explicitly.
    assert validation["freshness"]["state"] == "degraded"


def test_validation_section_is_genuinely_missing_when_bundle_has_no_sr_members(tmp_path):
    write_bundle(tmp_path / "bundles", "b1", "Bundle", ["task:T-001"])
    write_task(tmp_path / "tasks", "T-001", status="done")

    result = query_guide(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:b1"))
    validation = _section(result, 2)

    assert validate(validation, CLAIM_SCHEMA) == []
    assert validation["kind"] == "missing"
    assert validation["freshness"]["state"] == "n/a"


# ---------------------------------------------------------------------------
# Decisions section: real review records never name an actor, so a non-empty
# timeline always collapses to bullets -- an honest consequence of the real
# artifact shape, not a contrived fixture. An empty timeline is missing, not
# bullets (design SS3.2: "if nothing recorded supports the statement, it is
# missing, not synthesized").
# ---------------------------------------------------------------------------


def test_decisions_section_is_missing_when_there_are_no_recorded_decisions(tmp_path):
    write_sr(tmp_path / "requirements", "SR-001")

    result = query_guide(tmp_path, SystemScopeRef(kind="sr", ref="sr:SR-001"))
    decisions = _section(result, 3)

    assert validate(decisions, CLAIM_SCHEMA) == []
    assert decisions["kind"] == "missing"
    assert decisions["freshness"]["state"] == "n/a"


def test_decisions_section_collapses_to_bullets_when_actor_is_not_recorded(tmp_path):
    write_task(tmp_path / "tasks", "T-001", status="done", satisfies=["SR-001"])
    write_sr(tmp_path / "requirements", "SR-001")
    write_decision_artifact(tmp_path, task_id="T-001")

    result = query_guide(tmp_path, SystemScopeRef(kind="sr", ref="sr:SR-001"))
    decisions = _section(result, 3)

    assert validate(decisions, CLAIM_SCHEMA) == []
    assert decisions["kind"] == "recorded"
    assert decisions["spans"] == []
    assert decisions["freshness"]["state"] == "degraded"
    assert "task:T-001" in decisions["text"]


def test_decision_section_renders_prose_when_every_event_is_fresh():
    # Review round 1, finding 2: `actor`/`action` are controlled vocabulary
    # (`TimelineActor`/`TimelineAction`), never free-text prose copied from a
    # source document, so the decision section embeds them directly and
    # never routes them through `_verbatim_span` -- unlike an earlier
    # version, which checked `action` (but not `actor`) against
    # `_verbatim_span`, and since no real review record's mapped action
    # string ("approve" -> "approved") is ever literally present in its own
    # citation file, that inconsistency silently defeated the fresh->prose
    # path for this section on every real timeline.
    #
    # A real recorded review never actually produces a `fresh` event today
    # (queries.py's `_decision_event_from_record` always marks the actor
    # not-recorded, hence `degraded` -- see queries.py's module comment), so
    # this constructs the timeline dict directly (matching design SS7.4's
    # timelineEvent shape) rather than through `query_timeline`, to prove
    # the section *builder* itself takes the prose path once its input says
    # fresh. This is exactly the assertion that would have caught finding 2.
    timeline = {
        "scope": {"kind": "sr", "ref": "sr:SR-001"},
        "events": [
            {
                "at": "2026-08-08T12:00:00Z",
                "sequence": None,
                "actor": "human",
                "action": "approved",
                "subject": {"kind": "task", "ref": "task:T-001"},
                "citation": {
                    "kind": "decision",
                    "path": "evidence/runs/run-001.json",
                    "sha256": "a" * 64,
                    "anchor": "reviews[0]",
                },
                "freshness": {"state": "fresh", "reason": None, "dependencies": []},
            }
        ],
        "degraded": False,
        "degraded_reasons": [],
    }

    section = guide_module._decision_section(timeline)

    assert section.kind.value == "synthesized"
    assert section.spans == []  # nothing quotable here -- no span needed
    assert section.freshness.state.value == "fresh"
    assert "task:T-001" in section.text
    assert "approved" in section.text
    assert "human" in section.text
    assert len(section.citations) == 1
    assert section.citations[0].path == "evidence/runs/run-001.json"


# ---------------------------------------------------------------------------
# The verbatim-span verification safety net: a *fresh* section whose
# candidate text nonetheless fails independent verification must still
# degrade to bullets, never raise, never emit an unverified span. Previously
# this branch (`if span is None: ok = False; break`) was only exercised via
# a different trigger (task/requirement not found); this forces the actual
# verification-failure path directly.
# ---------------------------------------------------------------------------


def test_verbatim_span_failure_degrades_bundle_scope_sections_to_bullets_never_raises(tmp_path, monkeypatch):
    write_bundle(tmp_path / "bundles", "b1", "Bundle", ["task:T-001", "sr:SR-001"])
    write_task(tmp_path / "tasks", "T-001", title="Implement the thing", status="done", satisfies=["SR-001"])
    write_sr(tmp_path / "requirements", "SR-001", statement="When X happens, the system shall Y.")
    write_validation_report(tmp_path, [{"id": "SR-001", "passed": True, "stale": False, "artifacts": []}])

    monkeypatch.setattr(guide_module, "_verbatim_span", lambda *args, **kwargs: None)

    result = query_guide(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:b1"))

    # Identity (0), coverage (1), and validation (2) would all otherwise be
    # `fresh` and synthesized here -- with span verification forced to fail,
    # every one of them must degrade cleanly to bullets instead.
    for index in (0, 1, 2):
        section = result["sections"][index]
        assert validate(section, CLAIM_SCHEMA) == []
        assert section["kind"] == "recorded"
        assert section["spans"] == []
        assert section["text"]


def test_verbatim_span_failure_degrades_sr_scope_sections_to_bullets_never_raises(tmp_path, monkeypatch):
    write_sr(tmp_path / "requirements", "SR-001", statement="When X happens, the system shall Y.")
    write_validation_report(tmp_path, [{"id": "SR-001", "passed": True, "stale": False, "artifacts": []}])

    monkeypatch.setattr(guide_module, "_verbatim_span", lambda *args, **kwargs: None)

    result = query_guide(tmp_path, SystemScopeRef(kind="sr", ref="sr:SR-001"))

    # Identity (0), detail (1), and validation (2) would all otherwise be
    # `fresh` and synthesized here.
    for index in (0, 1, 2):
        section = result["sections"][index]
        assert validate(section, CLAIM_SCHEMA) == []
        assert section["kind"] == "recorded"
        assert section["spans"] == []
        assert section["text"]


# ---------------------------------------------------------------------------
# The collapse predicate is one binary axis, not graduated conservatism.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("stale", "expected_kind", "expected_state"),
    [
        (False, "synthesized", "fresh"),
        (True, "recorded", "stale"),
    ],
)
def test_collapse_predicate_is_binary_on_freshness_alone(tmp_path, stale, expected_kind, expected_state):
    write_sr(tmp_path / "requirements", "SR-001", statement="When X happens, the system shall Y.")
    write_validation_report(tmp_path, [{"id": "SR-001", "passed": True, "stale": stale, "artifacts": []}])

    result = query_guide(tmp_path, SystemScopeRef(kind="sr", ref="sr:SR-001"))
    validation = _section(result, 2)

    assert validation["kind"] == expected_kind
    assert validation["freshness"]["state"] == expected_state
    # There is no third rendering: prose is spans-non-empty XOR bullets is
    # spans-empty, always.
    assert bool(validation["spans"]) == (expected_kind == "synthesized")


def test_no_section_is_ever_synthesized_while_not_fresh(tmp_path):
    # A blanket sweep, not just the validation section above: across every
    # section this module can produce, "synthesized" and "not fresh" never
    # co-occur -- there is no stale-but-visible paragraph anywhere.
    write_bundle(tmp_path / "bundles", "b1", "Bundle", ["task:T-001", "task:T-999", "sr:SR-001"])
    write_task(tmp_path / "tasks", "T-001", title="Implement the thing", status="done", satisfies=["SR-001"])
    write_sr(tmp_path / "requirements", "SR-001", statement="When X happens, the system shall Y.")
    write_validation_report(tmp_path, [{"id": "SR-001", "passed": True, "stale": True, "artifacts": []}])
    write_decision_artifact(tmp_path, task_id="T-001")

    result = query_guide(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:b1"))

    for section in result["sections"]:
        if section["freshness"]["state"] != "fresh":
            assert section["kind"] != "synthesized"
            assert section["spans"] == []


# ---------------------------------------------------------------------------
# Determinism: no model call, no wall-clock, no unordered iteration.
# ---------------------------------------------------------------------------


def test_guide_assembly_is_deterministic(tmp_path):
    write_bundle(tmp_path / "bundles", "b1", "Evidence Lifecycle Bundle", ["task:T-001", "sr:SR-001"])
    write_task(tmp_path / "tasks", "T-001", title="Implement the thing", status="done", satisfies=["SR-001"])
    write_sr(tmp_path / "requirements", "SR-001", statement="When X happens, the system shall Y.")
    write_validation_report(tmp_path, [{"id": "SR-001", "passed": True, "stale": False, "artifacts": []}])

    scope = SystemScopeRef(kind="bundle", ref="bundle:b1")
    first = query_guide(tmp_path, scope)
    second = query_guide(tmp_path, scope)

    assert first == second
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_guide_full_shape_validates_against_claim_schema_for_every_section(tmp_path):
    write_bundle(tmp_path / "bundles", "b1", "Evidence Lifecycle Bundle", ["task:T-001", "sr:SR-001"])
    write_task(tmp_path / "tasks", "T-001", title="Implement the thing", status="done", satisfies=["SR-001"])
    write_sr(tmp_path / "requirements", "SR-001", statement="When X happens, the system shall Y.")
    write_validation_report(tmp_path, [{"id": "SR-001", "passed": True, "stale": False, "artifacts": []}])

    result = query_guide(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:b1"))

    assert result["scope"] == {"kind": "bundle", "ref": "bundle:b1"}
    assert len(result["sections"]) == 4
    for section in result["sections"]:
        assert validate(section, CLAIM_SCHEMA) == []


# ---------------------------------------------------------------------------
# No model call, ever. Parsed with `ast`, not a substring grep, so a forbidden
# name in a comment or docstring cannot produce a false failure and a real
# `import`/`from ... import ...` cannot hide behind formatting.
# ---------------------------------------------------------------------------

_FORBIDDEN_MODULE_PREFIXES = (
    "anthropic",
    "openai",
    "google.generativeai",
    "google.genai",
    "requests",
    "urllib.request",
    "http.client",
    "socket",
    "subprocess",
)


def _imported_module_names(source: str) -> set[str]:
    import ast

    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.add(node.module)
    return names


def test_guide_module_imports_no_llm_sdk_or_network_client():
    source = Path(guide_module.__file__).read_text(encoding="utf-8")
    imported = _imported_module_names(source)
    for forbidden in _FORBIDDEN_MODULE_PREFIXES:
        assert not any(name == forbidden or name.startswith(forbidden + ".") for name in imported), (
            f"guide.py must never import {forbidden!r} -- synthesis is deterministic template "
            "assembly only, never a model or network call"
        )
