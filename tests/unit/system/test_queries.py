"""Tests for factory.system.queries: brief, matrix, and scope listing.

These compose the loaders Task 1 built the model for: `factory.system.bundles`,
`factory.requirements.register`, `factory.orchestrator.ledger`, and
`factory.trace.validation_status`. Nothing here parses an artifact a loader
already owns -- existence and content come only from those loaders.
"""
from __future__ import annotations

import json

import pytest

from factory.system.models import ClaimClass, FreshnessState, MatrixStatus, SystemScopeRef
from factory.system.queries import (
    ScopeKindError,
    ScopeNotFoundError,
    list_scopes,
    parse_scope_ref,
    query_brief,
    query_matrix,
)
from factory.validation.schema_validator import SCHEMA_DIR, validate

from ._fixtures import (
    write_bundle,
    write_decision_artifact,
    write_plan,
    write_spec,
    write_sr,
    write_task,
    write_validation_report,
)

pytestmark = pytest.mark.unit

RESPONSE_SCHEMA = SCHEMA_DIR / "system_response.schema.json"
CLAIM_SCHEMA = SCHEMA_DIR / "system_claim.schema.json"
MATRIX_ROW_SCHEMA = SCHEMA_DIR / "system_matrix_row.schema.json"


# ---------------------------------------------------------------------------
# Exact scope resolution -- bundle: and sr:, nothing fuzzy
# ---------------------------------------------------------------------------


def test_parse_scope_ref_accepts_bundle_and_sr():
    assert parse_scope_ref("bundle:evidence-lifecycle") == SystemScopeRef(
        kind="bundle", ref="bundle:evidence-lifecycle"
    )
    assert parse_scope_ref("sr:SR-001") == SystemScopeRef(kind="sr", ref="sr:SR-001")


@pytest.mark.parametrize("raw", ["task:T-001", "spec:x.md", "nonsense", "bundle:", "sr:", ":x", ""])
def test_parse_scope_ref_rejects_anything_else(raw):
    with pytest.raises(ScopeKindError):
        parse_scope_ref(raw)


def test_query_brief_rejects_non_bundle_non_sr_scope_kind(tmp_path):
    with pytest.raises(ScopeKindError):
        query_brief(tmp_path, SystemScopeRef(kind="task", ref="task:T-001"))


def test_query_brief_raises_for_nonexistent_bundle(tmp_path):
    with pytest.raises(ScopeNotFoundError):
        query_brief(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:does-not-exist"))


def test_query_brief_raises_for_nonexistent_sr(tmp_path):
    with pytest.raises(ScopeNotFoundError):
        query_brief(tmp_path, SystemScopeRef(kind="sr", ref="sr:SR-999"))


def test_query_brief_does_not_fuzzy_match_sr_id(tmp_path):
    # "SR-1" must not resolve to "SR-001" -- exact refs only.
    write_sr(tmp_path / "requirements", "SR-001")
    with pytest.raises(ScopeNotFoundError):
        query_brief(tmp_path, SystemScopeRef(kind="sr", ref="sr:SR-1"))


def test_query_brief_does_not_fuzzy_match_bundle_id_case(tmp_path):
    write_bundle(tmp_path / "bundles", "evidence-lifecycle", "Label", [])
    with pytest.raises(ScopeNotFoundError):
        query_brief(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:Evidence-Lifecycle"))


# ---------------------------------------------------------------------------
# SR refs resolve through factory.requirements.register, not a hardcoded path
# ---------------------------------------------------------------------------


def test_sr_scope_resolves_through_requirements_register_default_dir(tmp_path):
    write_sr(tmp_path / "requirements", "SR-001", title="Nav preempts patrol")
    result = query_brief(tmp_path, SystemScopeRef(kind="sr", ref="sr:SR-001"))
    assert result["scope"]["ref"] == "sr:SR-001"
    texts = " ".join(c["text"] for c in result["claims"])
    assert "SR-001" in texts


def test_sr_scope_absent_requirements_dir_is_not_found_not_error(tmp_path):
    # No requirements/ dir at all -- register.load_register returns [] rather
    # than raising, so this must surface as "not found", not a crash.
    with pytest.raises(ScopeNotFoundError):
        query_brief(tmp_path, SystemScopeRef(kind="sr", ref="sr:SR-001"))


# ---------------------------------------------------------------------------
# Stale evidence downgrades a row but does not crash the query
# ---------------------------------------------------------------------------


def test_stale_validation_downgrades_matrix_row_freshness_without_crashing(tmp_path):
    write_sr(tmp_path / "requirements", "SR-001")
    write_validation_report(
        tmp_path,
        [
            {
                "id": "SR-001",
                "metric": "demo_rate",
                "value": 0.9,
                "assert": ">= 0.5",
                "passed": True,
                "trials": 1,
                "declared_trials": 1,
                "stale": True,
                "artifacts": ["traces/demo.json"],
            }
        ],
    )

    result = query_matrix(tmp_path, SystemScopeRef(kind="sr", ref="sr:SR-001"))

    row = result["rows"][0]
    assert row["status"] == "passed"  # recorded outcome untouched by staleness
    assert row["freshness"]["state"] == "stale"


def test_stale_validation_downgrades_brief_claim_freshness(tmp_path):
    write_sr(tmp_path / "requirements", "SR-001")
    write_validation_report(
        tmp_path,
        [{"id": "SR-001", "passed": False, "stale": True, "artifacts": []}],
    )

    result = query_brief(tmp_path, SystemScopeRef(kind="sr", ref="sr:SR-001"))

    validation_claims = [c for c in result["claims"] if "SR-001" in c["text"] and c["kind"] == "recorded"]
    assert any(c["freshness"]["state"] == "stale" for c in validation_claims)


# ---------------------------------------------------------------------------
# Missing evidence becomes missing, not guessed
# ---------------------------------------------------------------------------


def test_sr_with_no_validation_report_is_missing_in_brief(tmp_path):
    write_sr(tmp_path / "requirements", "SR-001")
    # no validation/ dir at all

    result = query_brief(tmp_path, SystemScopeRef(kind="sr", ref="sr:SR-001"))

    validation_claims = [c for c in result["claims"] if c["text"].endswith("never validated")]
    assert len(validation_claims) == 1
    assert validation_claims[0]["kind"] == "missing"
    assert validation_claims[0]["freshness"]["state"] == "n/a"


def test_sr_with_no_validation_report_is_never_run_in_matrix(tmp_path):
    write_sr(tmp_path / "requirements", "SR-001")

    result = query_matrix(tmp_path, SystemScopeRef(kind="sr", ref="sr:SR-001"))

    row = result["rows"][0]
    assert row["status"] == "never-run"
    assert row["freshness"]["state"] == "n/a"


def test_proposed_sr_has_no_binding_is_blocked_in_matrix(tmp_path):
    write_sr(tmp_path / "requirements", "SR-009", proposed=True)

    result = query_matrix(tmp_path, SystemScopeRef(kind="sr", ref="sr:SR-009"))

    row = result["rows"][0]
    assert row["status"] == "blocked"


def test_proposed_sr_binding_claim_is_missing_in_brief(tmp_path):
    write_sr(tmp_path / "requirements", "SR-009", proposed=True)

    result = query_brief(tmp_path, SystemScopeRef(kind="sr", ref="sr:SR-009"))

    missing = [c for c in result["claims"] if c["kind"] == "missing"]
    assert missing  # at least the "no binding" claim
    for claim in missing:
        assert claim["freshness"]["state"] == "n/a"


# ---------------------------------------------------------------------------
# Matrix `status` carries the recorded outcome only -- never "stale"/"missing"
# ---------------------------------------------------------------------------


def test_matrix_status_never_contains_stale_or_missing(tmp_path):
    write_sr(tmp_path / "requirements", "SR-001")
    write_sr(tmp_path / "requirements", "SR-002")
    write_validation_report(
        tmp_path,
        [{"id": "SR-001", "passed": True, "stale": True, "artifacts": []}],
    )
    bundle_dir = tmp_path / "bundles"
    write_bundle(bundle_dir, "b1", "Bundle One", ["sr:SR-001", "sr:SR-002"])

    result = query_matrix(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:b1"))

    statuses = {row["status"] for row in result["rows"]}
    assert "stale" not in statuses
    assert "missing" not in statuses


# ---------------------------------------------------------------------------
# Carry-forward: real bundle-member existence resolution (not just syntax)
# ---------------------------------------------------------------------------


def test_bundle_member_that_does_not_exist_is_reported_missing_and_kept(tmp_path):
    write_task(tmp_path / "tasks", "T-001", status="done")
    write_bundle(
        tmp_path / "bundles",
        "partial",
        "Partial bundle",
        ["task:T-001", "task:T-999", "sr:SR-404", "spec:docs/superpowers/specs/absent.md"],
    )

    result = query_brief(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:partial"))

    missing_texts = {c["text"] for c in result["claims"] if c["kind"] == "missing"}
    # every unresolvable member is still present in the output, not dropped
    assert "task:T-999" in missing_texts
    assert "sr:SR-404" in missing_texts
    assert "spec:docs/superpowers/specs/absent.md" in missing_texts
    for text in missing_texts:
        matching = [c for c in result["claims"] if c["text"] == text]
        assert all(c["freshness"]["state"] == "n/a" for c in matching)
    assert result["degraded"] is True


def test_bundle_with_all_members_resolving_is_not_degraded(tmp_path):
    write_task(tmp_path / "tasks", "T-001", status="done")
    write_bundle(tmp_path / "bundles", "clean", "Clean bundle", ["task:T-001"])

    result = query_brief(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:clean"))

    assert result["degraded"] is False


def test_bundle_member_spec_and_plan_existence_resolves_via_real_files(tmp_path):
    write_spec(tmp_path, "2026-08-08-x.md")
    write_plan(tmp_path, "2026-08-08-x.md")
    write_bundle(
        tmp_path / "bundles",
        "docs",
        "Docs bundle",
        [
            "spec:docs/superpowers/specs/2026-08-08-x.md",
            "plan:docs/superpowers/plans/2026-08-08-x.md",
        ],
    )

    result = query_brief(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:docs"))

    assert result["degraded"] is False
    kinds = {c["text"]: c["kind"] for c in result["claims"]}
    assert kinds["spec:docs/superpowers/specs/2026-08-08-x.md"] == "recorded"
    assert kinds["plan:docs/superpowers/plans/2026-08-08-x.md"] == "recorded"


# ---------------------------------------------------------------------------
# Plan checkbox state is never emitted as `recorded`
# ---------------------------------------------------------------------------


def test_plan_checkbox_state_never_classified_recorded(tmp_path):
    write_plan(tmp_path, "2026-08-07-pif-browser-evidence-integration.md")
    write_task(tmp_path / "tasks", "T-045", status="done")
    write_bundle(
        tmp_path / "bundles",
        "evidence-lifecycle",
        "Evidence Lifecycle",
        [
            "plan:docs/superpowers/plans/2026-08-07-pif-browser-evidence-integration.md",
            "task:T-045",
        ],
    )

    result = query_brief(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:evidence-lifecycle"))

    # No claim text ever carries a checkbox marker -- the plan body is never
    # read for anything beyond existence.
    for claim in result["claims"]:
        assert "- [ ]" not in claim["text"]
        assert "- [x]" not in claim["text"]

    # Implementation status for T-045 comes from the task ledger (done), not
    # from the plan's unchecked boxes.
    impl_claims = [c for c in result["claims"] if "T-045" in c["text"] and "status" in c["text"]]
    assert impl_claims, "expected a task-ledger-sourced implementation claim"
    assert impl_claims[0]["kind"] == "recorded"
    assert "done" in impl_claims[0]["text"]


# ---------------------------------------------------------------------------
# Carry-forward: list_bundles/list_scopes must not abort on one bad file
# ---------------------------------------------------------------------------


def test_list_scopes_skips_one_malformed_bundle_without_aborting(tmp_path):
    bundles_dir = tmp_path / "bundles"
    write_bundle(bundles_dir, "alpha", "Alpha", [])
    write_bundle(bundles_dir, "beta", "Beta", [])
    (bundles_dir / "broken.json").write_text("{not json", encoding="utf-8")

    scopes = list_scopes(tmp_path)

    bundle_refs = {s.ref for s in scopes if s.kind == "bundle"}
    assert bundle_refs == {"bundle:alpha", "bundle:beta"}


def test_list_scopes_includes_srs(tmp_path):
    write_sr(tmp_path / "requirements", "SR-001")
    write_sr(tmp_path / "requirements", "SR-002")
    write_bundle(tmp_path / "bundles", "b1", "Bundle", [])

    scopes = list_scopes(tmp_path)

    assert SystemScopeRef(kind="sr", ref="sr:SR-001") in scopes
    assert SystemScopeRef(kind="sr", ref="sr:SR-002") in scopes
    assert SystemScopeRef(kind="bundle", ref="bundle:b1") in scopes


def test_list_scopes_on_empty_repo_is_empty(tmp_path):
    assert list_scopes(tmp_path) == []


# ---------------------------------------------------------------------------
# A decision artifact in the repo does not confuse brief/matrix (Task 3's
# job, not this one) -- present as realistic scaffolding only.
# ---------------------------------------------------------------------------


def test_decision_artifact_present_does_not_break_brief_or_matrix(tmp_path):
    write_sr(tmp_path / "requirements", "SR-001")
    write_task(tmp_path / "tasks", "T-001", status="done")
    write_decision_artifact(tmp_path, task_id="T-001")
    write_bundle(tmp_path / "bundles", "b1", "Bundle", ["sr:SR-001", "task:T-001"])

    brief = query_brief(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:b1"))
    matrix = query_matrix(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:b1"))

    assert brief["degraded"] is False
    assert len(matrix["rows"]) == 1


# ---------------------------------------------------------------------------
# Shape validation against the record-level and envelope schemas
# ---------------------------------------------------------------------------


def test_brief_claims_validate_against_claim_schema(tmp_path):
    write_sr(tmp_path / "requirements", "SR-001")
    write_validation_report(tmp_path, [{"id": "SR-001", "passed": True, "stale": False, "artifacts": []}])

    result = query_brief(tmp_path, SystemScopeRef(kind="sr", ref="sr:SR-001"))

    for claim in result["claims"]:
        assert validate(claim, CLAIM_SCHEMA) == []


def test_matrix_rows_validate_against_matrix_row_schema(tmp_path):
    write_sr(tmp_path / "requirements", "SR-001")
    write_validation_report(tmp_path, [{"id": "SR-001", "passed": True, "stale": False, "artifacts": []}])

    result = query_matrix(tmp_path, SystemScopeRef(kind="sr", ref="sr:SR-001"))

    for row in result["rows"]:
        assert validate(row, MATRIX_ROW_SCHEMA) == []


def test_full_envelope_validates_against_response_schema(tmp_path):
    write_sr(tmp_path / "requirements", "SR-001")
    write_validation_report(tmp_path, [{"id": "SR-001", "passed": True, "stale": False, "artifacts": []}])
    scope = SystemScopeRef(kind="sr", ref="sr:SR-001")

    envelope = {
        "scope": {"kind": scope.kind, "ref": scope.ref},
        "brief": query_brief(tmp_path, scope),
        "matrix": query_matrix(tmp_path, scope),
        "freshness": {"state": "fresh", "details": []},
    }

    assert validate(envelope, RESPONSE_SCHEMA) == []
    # round-trips through JSON cleanly (no dataclasses/enums leaking through)
    json.dumps(envelope)


# ---------------------------------------------------------------------------
# No fuzzy matching, no inferred provenance
# ---------------------------------------------------------------------------


def test_missing_claims_never_carry_fabricated_citations(tmp_path):
    write_bundle(tmp_path / "bundles", "partial", "Partial", ["task:T-999"])

    result = query_brief(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:partial"))

    missing = [c for c in result["claims"] if c["kind"] == "missing"]
    assert missing
    for claim in missing:
        assert claim["citations"] == []


def test_matrix_kind_only_ever_produces_declared_claim_classes(tmp_path):
    write_sr(tmp_path / "requirements", "SR-001")
    result = query_brief(tmp_path, SystemScopeRef(kind="sr", ref="sr:SR-001"))
    for claim in result["claims"]:
        assert ClaimClass(claim["kind"]) in ClaimClass
        assert FreshnessState(claim["freshness"]["state"]) in FreshnessState


def test_all_matrix_statuses_are_legal_enum_members(tmp_path):
    write_sr(tmp_path / "requirements", "SR-001", proposed=True)
    result = query_matrix(tmp_path, SystemScopeRef(kind="sr", ref="sr:SR-001"))
    for row in result["rows"]:
        assert MatrixStatus(row["status"]) in MatrixStatus
