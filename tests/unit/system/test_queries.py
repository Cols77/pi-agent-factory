"""Tests for factory.system.queries: brief, matrix, and scope listing.

These compose the loaders Task 1 built the model for: `factory.system.bundles`,
`factory.requirements.register`, `factory.orchestrator.ledger`, and
`factory.trace.validation_status`. Nothing here parses an artifact a loader
already owns -- existence and content come only from those loaders.
"""
from __future__ import annotations

import json

import pytest

from factory.system import queries
from factory.system.bundles import BundleIdMismatchError
from factory.system.models import ClaimClass, FreshnessState, MatrixStatus, SystemScopeRef
from factory.system.queries import (
    ScopeKindError,
    ScopeNotFoundError,
    list_bundle_errors,
    list_scopes,
    parse_scope_ref,
    query_brief,
    query_guide,
    query_matrix,
    query_timeline,
    query_traversal,
)
from factory.validation.schema_validator import SCHEMA_DIR, validate

from ._fixtures import (
    validation_entry,
    validation_requirement,
    write_bundle,
    write_bundle_raw,
    write_corrupt_validation_report,
    write_decision_artifact,
    write_non_dict_validation_report,
    write_plan,
    write_run_manifest,
    write_spec,
    write_sr,
    write_task,
    write_validation_report,
)
from ._fixtures import _write_bundle_fixture, _write_manifest_fixture, _write_task_fixture  # noqa: F401
from ._fixtures import _write_session_fixture  # noqa: F401

pytestmark = pytest.mark.unit

RESPONSE_SCHEMA = SCHEMA_DIR / "system_response.schema.json"
CLAIM_SCHEMA = SCHEMA_DIR / "system_claim.schema.json"
MATRIX_ROW_SCHEMA = SCHEMA_DIR / "system_matrix_row.schema.json"
TIMELINE_EVENT_SCHEMA = SCHEMA_DIR / "system_timeline_event.schema.json"


# ---------------------------------------------------------------------------
# Exact scope resolution -- bundle: and sr:, nothing fuzzy
# ---------------------------------------------------------------------------


def test_parse_scope_ref_accepts_bundle_and_sr():
    assert parse_scope_ref("bundle:evidence-lifecycle") == SystemScopeRef(
        kind="bundle", ref="bundle:evidence-lifecycle"
    )
    assert parse_scope_ref("sr:SR-001") == SystemScopeRef(kind="sr", ref="sr:SR-001")


@pytest.mark.parametrize("raw", ["spec:x.md", "nonsense", "bundle:", "sr:", ":x", ""])
def test_parse_scope_ref_rejects_anything_else(raw):
    with pytest.raises(ScopeKindError):
        parse_scope_ref(raw)


def test_task_and_file_are_now_openable_scopes():
    assert parse_scope_ref("task:T-059").kind == "task"
    assert parse_scope_ref("file:src/drone/planning/reactive.py").kind == "file"


def test_spec_and_plan_are_still_not_openable_scopes():
    with pytest.raises(ScopeKindError):
        parse_scope_ref("spec:docs/superpowers/specs/x.md")


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
# Member-of affordance: a sr: brief lists every bundle that contains it
# ---------------------------------------------------------------------------


def test_brief_includes_member_bundles_for_sr_scope(tmp_path):
    write_sr(tmp_path / "requirements", "SR-001")
    write_bundle(tmp_path / "bundles", "b1", "B1", ["sr:SR-001"])
    brief = query_brief(tmp_path, SystemScopeRef(kind="sr", ref="sr:SR-001"))
    assert brief["member_of"] == ["b1"]


def test_brief_member_of_lists_all_containing_bundles_multimembership(tmp_path):
    write_sr(tmp_path / "requirements", "SR-001")
    write_bundle(tmp_path / "bundles", "alpha", "A", ["sr:SR-001"])
    write_bundle(tmp_path / "bundles", "gamma", "G", ["sr:SR-001", "sr:SR-002"])
    brief = query_brief(tmp_path, SystemScopeRef(kind="sr", ref="sr:SR-001"))
    # Deterministic load order: alpha is written first.
    assert brief["member_of"] == ["alpha", "gamma"]


def test_brief_member_of_is_empty_when_sr_in_no_bundle(tmp_path):
    write_sr(tmp_path / "requirements", "SR-001")
    write_bundle(tmp_path / "bundles", "b1", "B1", ["sr:SR-998"])
    write_bundle(tmp_path / "bundles", "b2", "B2", ["sr:SR-999"])
    brief = query_brief(tmp_path, SystemScopeRef(kind="sr", ref="sr:SR-001"))
    # Present but empty: this sr is not a member of any bundle.
    assert brief["member_of"] == []


def test_brief_member_of_absent_for_bundle_scope(tmp_path):
    write_bundle(tmp_path / "bundles", "b1", "B1", ["sr:SR-001"])
    brief = query_brief(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:b1"))
    assert "member_of" not in brief


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
    # "Fresh" against zero evidence would be an unfounded assertion, and it
    # would contradict the brief's `missing`/`n/a` claim for the identical
    # condition (finding 2) -- there is no recorded basis to be current
    # about, so freshness is n/a, not fresh.
    assert row["freshness"]["state"] == "n/a"


def test_proposed_sr_binding_claim_is_missing_in_brief(tmp_path):
    write_sr(tmp_path / "requirements", "SR-009", proposed=True)

    result = query_brief(tmp_path, SystemScopeRef(kind="sr", ref="sr:SR-009"))

    missing = [c for c in result["claims"] if c["kind"] == "missing"]
    assert missing  # at least the "no binding" claim
    for claim in missing:
        assert claim["freshness"]["state"] == "n/a"


# ---------------------------------------------------------------------------
# A corrupt validation report is degraded, never asserted as the recorded
# fact "never validated" (finding 1) -- but a report that parses fine and
# simply has nothing (yet) to say is genuinely "never validated", not
# degraded (fix round 3). `_validation_report_is_corrupt` distinguishes them
# by attempting its own JSON parse rather than inferring corruption from
# `load_validation`'s collapsed `{}` return value.
# ---------------------------------------------------------------------------


def test_corrupt_validation_report_is_degraded_not_missing_in_brief(tmp_path):
    write_sr(tmp_path / "requirements", "SR-001")
    write_corrupt_validation_report(tmp_path)

    result = query_brief(tmp_path, SystemScopeRef(kind="sr", ref="sr:SR-001"))

    validation_claims = [c for c in result["claims"] if "SR-001" in c["text"] and "unreadable" in c["text"]]
    assert len(validation_claims) == 1
    claim = validation_claims[0]
    # Not `missing` -- that would assert "never validated", a guess this
    # code cannot make about a report it could not read.
    assert claim["kind"] != "missing"
    assert claim["freshness"]["state"] == "degraded"
    # None of the claims may claim the unfounded "never validated" text.
    assert not any(c["text"].endswith("never validated") for c in result["claims"])


def test_corrupt_validation_report_is_degraded_not_never_run_freshness_in_matrix(tmp_path):
    write_sr(tmp_path / "requirements", "SR-001")
    write_corrupt_validation_report(tmp_path)

    result = query_matrix(tmp_path, SystemScopeRef(kind="sr", ref="sr:SR-001"))

    row = result["rows"][0]
    # `status` must be "unknown", not "never-run" (user ruling, 2026-08-08):
    # "never-run" would assert a recorded fact the evidence does not
    # support, and it contradicted the brief's `derived`/`degraded` claim
    # about the same SR (IMPORTANT 4). Freshness says "degraded", not "n/a",
    # because a report genuinely exists and could not be read.
    assert row["status"] == "unknown"
    assert row["status"] != "never-run"
    assert row["freshness"]["state"] == "degraded"


def test_corrupt_validation_report_claim_still_validates_against_claim_schema(tmp_path):
    write_sr(tmp_path / "requirements", "SR-001")
    write_corrupt_validation_report(tmp_path)

    result = query_brief(tmp_path, SystemScopeRef(kind="sr", ref="sr:SR-001"))

    for claim in result["claims"]:
        assert validate(claim, CLAIM_SCHEMA) == []


def test_corrupt_validation_report_brief_and_matrix_agree_about_the_same_sr(tmp_path):
    # IMPORTANT 4: the brief and matrix previously contradicted each other
    # for an unreadable report -- brief said `derived`/`degraded`, matrix
    # asserted the recorded outcome `never-run`. Both surfaces must now
    # agree the outcome is undetermined.
    write_sr(tmp_path / "requirements", "SR-001")
    write_corrupt_validation_report(tmp_path)
    scope = SystemScopeRef(kind="sr", ref="sr:SR-001")

    brief = query_brief(tmp_path, scope)
    matrix = query_matrix(tmp_path, scope)

    validation_claim = next(c for c in brief["claims"] if "unreadable" in c["text"])
    row = matrix["rows"][0]

    assert validation_claim["kind"] == "derived"
    assert validation_claim["freshness"]["state"] == "degraded"
    assert row["status"] == "unknown"
    assert row["freshness"]["state"] == "degraded"
    # Neither surface asserts the recorded fact "never validated"/"never-run"
    # about a report that could not be read.
    assert "never validated" not in validation_claim["text"]
    assert row["status"] != "never-run"


# ---------------------------------------------------------------------------
# Non-object JSON in a validation report (e.g. a bare array) is also
# corrupt -- `_validation_report_is_corrupt` previously only checked whether
# the file parsed at all, so a file like `[1,2,3]` parsed fine and was
# reported "not corrupt", and `validation_status.load_validation`'s
# `raw.get("requirements", [])` then raised `AttributeError` on the list,
# crashing brief/matrix/guide for every scope (IMPORTANT 3).
# ---------------------------------------------------------------------------


def test_non_dict_validation_report_json_degrades_brief_instead_of_crashing(tmp_path):
    write_sr(tmp_path / "requirements", "SR-001")
    write_non_dict_validation_report(tmp_path)

    result = query_brief(tmp_path, SystemScopeRef(kind="sr", ref="sr:SR-001"))

    validation_claims = [c for c in result["claims"] if "SR-001" in c["text"] and "unreadable" in c["text"]]
    assert len(validation_claims) == 1
    assert validation_claims[0]["kind"] == "derived"
    assert validation_claims[0]["freshness"]["state"] == "degraded"


def test_non_dict_validation_report_json_degrades_matrix_instead_of_crashing(tmp_path):
    write_sr(tmp_path / "requirements", "SR-001")
    write_non_dict_validation_report(tmp_path)

    result = query_matrix(tmp_path, SystemScopeRef(kind="sr", ref="sr:SR-001"))

    row = result["rows"][0]
    assert row["status"] == "unknown"
    assert row["freshness"]["state"] == "degraded"


def test_non_dict_validation_report_json_degrades_guide_instead_of_crashing(tmp_path):
    write_sr(tmp_path / "requirements", "SR-001", statement="When X happens, the system shall Y.")
    write_non_dict_validation_report(tmp_path)

    result = query_guide(tmp_path, SystemScopeRef(kind="sr", ref="sr:SR-001"))

    validation_section = result["sections"][2]
    assert validate(validation_section, CLAIM_SCHEMA) == []
    assert validation_section["kind"] == "derived"
    assert validation_section["freshness"]["state"] == "degraded"


def test_non_dict_validation_report_json_is_reported_corrupt(tmp_path):
    from factory.system.queries import _validation_report_is_corrupt

    write_non_dict_validation_report(tmp_path)
    assert _validation_report_is_corrupt(tmp_path) is True


def test_missing_validation_report_file_is_still_na_not_degraded(tmp_path):
    # No file at all (as opposed to a corrupt one) is genuinely "never
    # validated" -- the degraded path must not fire just because the dict
    # came back empty.
    write_sr(tmp_path / "requirements", "SR-001")

    brief = query_brief(tmp_path, SystemScopeRef(kind="sr", ref="sr:SR-001"))
    matrix = query_matrix(tmp_path, SystemScopeRef(kind="sr", ref="sr:SR-001"))

    validation_claims = [c for c in brief["claims"] if c["text"].endswith("never validated")]
    assert validation_claims[0]["freshness"]["state"] == "n/a"
    assert matrix["rows"][0]["freshness"]["state"] == "n/a"


def test_valid_but_empty_validation_report_is_never_validated_not_degraded_in_brief(tmp_path):
    # A report that parses fine but has an empty `requirements` array is
    # exactly what factory.validation.pipeline.validate_task_requirements
    # writes before anything has run -- a legitimate state, not corruption
    # (fix round 3: _validation_report_is_corrupt previously false-positived
    # on this by inferring corruption from load_validation's collapsed `{}`
    # instead of attempting its own parse).
    write_sr(tmp_path / "requirements", "SR-001")
    write_validation_report(tmp_path, [])

    result = query_brief(tmp_path, SystemScopeRef(kind="sr", ref="sr:SR-001"))

    validation_claims = [c for c in result["claims"] if c["text"].endswith("never validated")]
    assert len(validation_claims) == 1
    assert validation_claims[0]["kind"] == "missing"
    assert validation_claims[0]["freshness"]["state"] == "n/a"
    assert not any("unreadable" in c["text"] for c in result["claims"])


def test_valid_but_empty_validation_report_is_never_run_not_degraded_in_matrix(tmp_path):
    write_sr(tmp_path / "requirements", "SR-001")
    write_validation_report(tmp_path, [])

    result = query_matrix(tmp_path, SystemScopeRef(kind="sr", ref="sr:SR-001"))

    row = result["rows"][0]
    assert row["status"] == "never-run"
    assert row["freshness"]["state"] == "n/a"
    assert row["summary"] == "never validated"


def test_valid_report_with_only_other_srs_is_never_validated_not_degraded(tmp_path):
    # A non-empty, well-formed report that simply never mentions this SR is
    # also not corruption -- distinct from the "zero entries at all" case,
    # covered separately so both shapes of "legitimately says nothing about
    # this SR" are pinned.
    write_sr(tmp_path / "requirements", "SR-001")
    write_sr(tmp_path / "requirements", "SR-002")
    write_validation_report(tmp_path, [{"id": "SR-002", "passed": True, "stale": False, "artifacts": []}])

    result = query_matrix(tmp_path, SystemScopeRef(kind="sr", ref="sr:SR-001"))

    row = result["rows"][0]
    assert row["status"] == "never-run"
    assert row["freshness"]["state"] == "n/a"


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


# ---------------------------------------------------------------------------
# Task 5: a bundle task: member claim carries an implementation summary
# ---------------------------------------------------------------------------


def test_bundle_task_members_carry_an_implementation_summary(tmp_path, write_task,
                                                              write_manifest, write_bundle):
    write_task(tmp_path, "T-059", status="done", satisfies=[])
    write_manifest(tmp_path, run_id="r1", task_id="T-059", outcome="completed",
                   changed_files=["src/a.py", "src/b.py"])
    write_bundle(tmp_path / "bundles", "feat", "Feature", ["task:T-059"])

    result = query_brief(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:feat"))

    member = next(c for c in result["claims"] if "T-059" in c["text"])
    summary = member["implementation_summary"]
    assert summary["runs"] == 1
    assert summary["latest_outcome"] == "completed"
    assert summary["changed_file_count"] == 2


def test_a_task_member_with_no_runs_summarises_as_none_not_zero(tmp_path, write_task,
                                                                write_bundle):
    write_task(tmp_path, "T-070", status="todo", satisfies=[])
    write_bundle(tmp_path / "bundles", "feat", "Feature", ["task:T-070"])

    result = query_brief(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:feat"))
    member = next(c for c in result["claims"] if "T-070" in c["text"])

    assert member["implementation_summary"]["runs"] == 0
    assert member["implementation_summary"]["latest_outcome"] is None
    assert member["implementation_summary"]["changed_file_count"] is None


# ---------------------------------------------------------------------------
# Task 5 review fix: `latest_validation`'s three verdict branches and three
# `None` conditions -- the controller-supplied rule (2026-08-09) had zero
# coverage. Each test here pins exactly one branch.
# ---------------------------------------------------------------------------


def test_latest_validation_is_failed_when_any_requirement_did_not_pass(
    tmp_path, write_task, write_manifest, write_bundle
):
    write_task(tmp_path, "T-081", status="done", satisfies=[])
    write_manifest(
        tmp_path,
        run_id="r1",
        task_id="T-081",
        outcome="completed",
        validation=[
            validation_entry(
                [
                    validation_requirement(req_id="SR-001", passed=True, stale=False),
                    validation_requirement(req_id="SR-002", passed=False, stale=False),
                ]
            )
        ],
    )
    write_bundle(tmp_path / "bundles", "feat", "Feature", ["task:T-081"])

    result = query_brief(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:feat"))
    member = next(c for c in result["claims"] if "T-081" in c["text"])

    assert member["implementation_summary"]["latest_validation"] == "failed"


def test_latest_validation_is_stale_when_all_passed_but_one_is_stale(
    tmp_path, write_task, write_manifest, write_bundle
):
    # The whole reason the third state exists: a stale pass must never be
    # reported as a plain pass (controller ruling, 2026-08-09) -- this is
    # the pin for that.
    write_task(tmp_path, "T-082", status="done", satisfies=[])
    write_manifest(
        tmp_path,
        run_id="r1",
        task_id="T-082",
        outcome="completed",
        validation=[
            validation_entry(
                [
                    validation_requirement(req_id="SR-001", passed=True, stale=False),
                    validation_requirement(req_id="SR-002", passed=True, stale=True),
                ]
            )
        ],
    )
    write_bundle(tmp_path / "bundles", "feat", "Feature", ["task:T-082"])

    result = query_brief(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:feat"))
    member = next(c for c in result["claims"] if "T-082" in c["text"])

    assert member["implementation_summary"]["latest_validation"] == "stale"


def test_latest_validation_is_passed_when_all_passed_and_none_stale(
    tmp_path, write_task, write_manifest, write_bundle
):
    write_task(tmp_path, "T-083", status="done", satisfies=[])
    write_manifest(
        tmp_path,
        run_id="r1",
        task_id="T-083",
        outcome="completed",
        validation=[validation_entry([validation_requirement(req_id="SR-001", passed=True, stale=False)])],
    )
    write_bundle(tmp_path / "bundles", "feat", "Feature", ["task:T-083"])

    result = query_brief(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:feat"))
    member = next(c for c in result["claims"] if "T-083" in c["text"])

    assert member["implementation_summary"]["latest_validation"] == "passed"


def test_latest_validation_is_none_for_a_session_sourced_latest_run(
    tmp_path, write_task, write_session, write_bundle
):
    write_task(tmp_path, "T-084", status="done", satisfies=[])
    write_session(tmp_path, "session-1", "T-084", "completed")
    write_bundle(tmp_path / "bundles", "feat", "Feature", ["task:T-084"])

    result = query_brief(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:feat"))
    member = next(c for c in result["claims"] if "T-084" in c["text"])

    # A session record never captures validation (design, same reasoning as
    # `changed_files`), so there is nothing to verdict -- never guessed.
    assert member["implementation_summary"]["latest_validation"] is None


def test_latest_validation_is_none_when_manifest_has_no_validation_entries(
    tmp_path, write_task, write_manifest, write_bundle
):
    write_task(tmp_path, "T-085", status="done", satisfies=[])
    write_manifest(tmp_path, run_id="r1", task_id="T-085", outcome="completed")  # validation defaults to []
    write_bundle(tmp_path / "bundles", "feat", "Feature", ["task:T-085"])

    result = query_brief(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:feat"))
    member = next(c for c in result["claims"] if "T-085" in c["text"])

    assert member["implementation_summary"]["latest_validation"] is None


def test_latest_validation_is_none_when_validation_entries_name_no_requirements(
    tmp_path, write_task, write_manifest, write_bundle
):
    write_task(tmp_path, "T-086", status="done", satisfies=[])
    write_manifest(
        tmp_path,
        run_id="r1",
        task_id="T-086",
        outcome="completed",
        validation=[validation_entry(requirements=[])],
    )
    write_bundle(tmp_path / "bundles", "feat", "Feature", ["task:T-086"])

    result = query_brief(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:feat"))
    member = next(c for c in result["claims"] if "T-086" in c["text"])

    assert member["implementation_summary"]["latest_validation"] is None


def test_bundle_task_member_gets_a_derived_implementation_summary_claim_with_citation(
    tmp_path, write_task, write_manifest, write_bundle
):
    write_task(tmp_path, "T-090", status="done", satisfies=[])
    write_manifest(tmp_path, run_id="r1", task_id="T-090", outcome="completed", changed_files=["src/a.py"])
    write_bundle(tmp_path / "bundles", "feat", "Feature", ["task:T-090"])

    result = query_brief(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:feat"))

    aggregate_claims = [c for c in result["claims"] if c["kind"] == "derived" and "T-090" in c["text"]]
    assert len(aggregate_claims) == 1
    claim = aggregate_claims[0]
    assert validate(claim, CLAIM_SCHEMA) == []
    assert claim["citations"]
    assert claim["citations"][0]["kind"] == "manifest"
    assert claim["freshness"]["state"] == "fresh"


def test_unreadable_run_citation_degrades_the_bundle_brief(
    tmp_path, write_task, write_manifest, write_bundle, monkeypatch
):
    write_task(tmp_path, "T-091", status="done", satisfies=[])
    write_manifest(tmp_path, run_id="r1", task_id="T-091", outcome="completed", changed_files=["src/a.py"])
    write_bundle(tmp_path / "bundles", "feat", "Feature", ["task:T-091"])

    # Simulate the cited manifest becoming unreadable at the exact point
    # `story.py` hashes it for the run's own citation -- the same OSError
    # path `factory.system._claims.sha256_file` already handles by
    # returning `None`. The manifest itself is real and schema-valid
    # (written above through the real writer); only the hashing outcome for
    # this one test is forced, so this exercises the defensive branch
    # without a flaky, OS-specific permission trick.
    monkeypatch.setattr("factory.system.story._sha256_file", lambda path: None)

    result = query_brief(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:feat"))

    assert result["degraded"] is True
    assert any(
        "implementation summary cites a manifest or session record that could not be read" in reason
        for reason in result["degraded_reasons"]
    )


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
    assert kinds["Spec title — spec:docs/superpowers/specs/2026-08-08-x.md"] == "recorded"
    assert kinds["Plan title — plan:docs/superpowers/plans/2026-08-08-x.md"] == "recorded"


def test_bundle_member_claims_carry_the_documents_recorded_title(tmp_path):
    # A brief whose claims are bare refs tells a reader nothing they could not
    # get from `ls`. The repo already parses a title out of every spec and plan
    # (factory.trace.model._file_node), so surfacing it is recorded evidence
    # from the cited document -- not a new inference.
    write_spec(tmp_path, "2026-08-08-evidence.md", title="Evidence lifecycle and recovery")
    write_bundle(
        tmp_path / "bundles",
        "ev",
        "Evidence bundle",
        ["spec:docs/superpowers/specs/2026-08-08-evidence.md"],
    )

    result = query_brief(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:ev"))

    member = next(c for c in result["claims"] if "2026-08-08-evidence.md" in c["text"])
    assert "Evidence lifecycle and recovery" in member["text"]
    # The ref stays: the title is for humans, the ref is what resolves.
    assert "spec:docs/superpowers/specs/2026-08-08-evidence.md" in member["text"]
    assert member["kind"] == "recorded"


def test_member_title_falls_back_to_the_ref_when_no_title_is_recorded(tmp_path):
    # No heading, no frontmatter title -> nothing recorded to show. The claim
    # must not invent one, and must not render an empty prefix.
    specs = tmp_path / "docs" / "superpowers" / "specs"
    specs.mkdir(parents=True, exist_ok=True)
    (specs / "2026-08-08-untitled.md").write_text("no heading here\n", encoding="utf-8")
    write_bundle(
        tmp_path / "bundles",
        "untitled",
        "Untitled bundle",
        ["spec:docs/superpowers/specs/2026-08-08-untitled.md"],
    )

    result = query_brief(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:untitled"))

    member = next(c for c in result["claims"] if "2026-08-08-untitled.md" in c["text"])
    assert not member["text"].startswith("—")
    assert member["text"] == "spec:docs/superpowers/specs/2026-08-08-untitled.md"


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


def test_list_scopes_omits_srs(tmp_path):
    write_sr(tmp_path / "requirements", "SR-001")
    write_sr(tmp_path / "requirements", "SR-002")
    write_bundle(tmp_path / "bundles", "b1", "Bundle", [])

    scopes = list_scopes(tmp_path)

    # sr: scopes leave the sidebar listing (SP-B Task 3) but bundle: remains.
    assert SystemScopeRef(kind="sr", ref="sr:SR-001") not in scopes
    assert SystemScopeRef(kind="sr", ref="sr:SR-002") not in scopes
    assert SystemScopeRef(kind="bundle", ref="bundle:b1") in scopes


def test_list_scopes_omits_sr_but_parse_resolves(tmp_path):
    write_sr(tmp_path / "requirements", "SR-007")

    scopes = list_scopes(tmp_path)
    kinds = {s.kind for s in scopes}
    assert "sr" not in kinds

    # sr: is still a legal, resolvable top-level scope -- just not listed.
    ref = parse_scope_ref("sr:SR-007")
    assert ref.kind == "sr"
    assert ref.ref == "sr:SR-007"


def test_list_scopes_on_empty_repo_is_empty(tmp_path):
    assert list_scopes(tmp_path) == []


# ---------------------------------------------------------------------------
# A bundle whose declared id does not match its filename is a distinct,
# visible failure -- not "not found" (which would erase it from
# list_bundles with no trace), and not silently swallowed (findings 4/5).
# ---------------------------------------------------------------------------


def test_bundle_id_filename_mismatch_is_reported_not_silently_dropped(tmp_path):
    bundles_dir = tmp_path / "bundles"
    # File is "foo.json" but declares id "bar" -- schema-legal, but
    # unreachable under either name without a diagnostic.
    write_bundle_raw(bundles_dir, "foo", {"id": "bar", "label": "Mismatched", "members": []})
    write_bundle(bundles_dir, "good", "Good bundle", [])

    scopes = list_scopes(tmp_path)
    errors = list_bundle_errors(tmp_path)

    # It never becomes a usable scope under either name.
    assert SystemScopeRef(kind="bundle", ref="bundle:foo") not in scopes
    assert SystemScopeRef(kind="bundle", ref="bundle:bar") not in scopes
    assert SystemScopeRef(kind="bundle", ref="bundle:good") in scopes

    # But it is reported, not erased.
    assert len(errors) == 1
    assert errors[0]["bundle_id"] == "foo"
    assert "bar" in errors[0]["error"]


def test_malformed_bundle_json_is_reported_via_list_bundle_errors(tmp_path):
    bundles_dir = tmp_path / "bundles"
    write_bundle(bundles_dir, "good", "Good bundle", [])
    write_bundle_raw(bundles_dir, "broken", "{not json at all")

    errors = list_bundle_errors(tmp_path)

    assert len(errors) == 1
    assert errors[0]["bundle_id"] == "broken"


def test_list_bundle_errors_empty_when_everything_loads(tmp_path):
    write_bundle(tmp_path / "bundles", "good", "Good bundle", [])
    assert list_bundle_errors(tmp_path) == []


def test_list_bundle_errors_on_absent_dir_is_empty(tmp_path):
    assert list_bundle_errors(tmp_path) == []


def test_bundle_load_raises_bundle_id_mismatch_error_directly(tmp_path):
    # Confirms the underlying exception type queries.py's
    # _load_bundle_or_raise depends on to convert this into
    # ScopeNotFoundError (test_query_brief_does_not_fuzzy_match_bundle_id_case
    # exercises that conversion end to end).
    from factory.system.bundles import load_bundle

    bundles_dir = tmp_path / "bundles"
    write_bundle_raw(bundles_dir, "foo", {"id": "bar", "label": "X", "members": []})

    with pytest.raises(BundleIdMismatchError):
        load_bundle(bundles_dir, "foo")


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
        "timeline": query_timeline(tmp_path, scope),
        "guide": query_guide(tmp_path, scope),
    }

    assert validate(envelope, RESPONSE_SCHEMA) == []
    # round-trips through JSON cleanly (no dataclasses/enums leaking through)
    json.dumps(envelope)


# ---------------------------------------------------------------------------
# The envelope schema's inlined matrixRow/scopeRef kind enums must not drift
# from the record-level schemas (finding 3). `schema_validator.py` has no
# cross-file $ref resolver, so the duplication itself is forced -- but a row
# the record-level schema rejects must be rejected by the envelope too.
# ---------------------------------------------------------------------------


def test_matrix_row_rejected_by_row_schema_is_also_rejected_by_envelope(tmp_path):
    # "task" is the new boundary (design amendment at commit 561c89a, fix
    # round 2): the matrix is a validation matrix, subject.kind is `sr`
    # only. "task" used to be a legal matrixRow.subject.kind under the old
    # four-kind enum, so this exercises the ruling, not just any illegal
    # string.
    write_sr(tmp_path / "requirements", "SR-001")
    write_validation_report(tmp_path, [{"id": "SR-001", "passed": True, "stale": False, "artifacts": []}])
    scope = SystemScopeRef(kind="sr", ref="sr:SR-001")

    matrix = query_matrix(tmp_path, scope)
    matrix["rows"][0]["subject"]["kind"] = "task"

    assert validate(matrix["rows"][0], MATRIX_ROW_SCHEMA) != []

    envelope = {
        "scope": {"kind": scope.kind, "ref": scope.ref},
        "brief": query_brief(tmp_path, scope),
        "matrix": matrix,
        "timeline": query_timeline(tmp_path, scope),
        "guide": query_guide(tmp_path, scope),
    }
    assert validate(envelope, RESPONSE_SCHEMA) != []


def test_matrix_row_subject_kind_enum_is_sr_only(tmp_path):
    # Locks in the design amendment directly: sr is legal, task/validation/
    # decision are not -- in both the record-level and envelope schemas.
    write_sr(tmp_path / "requirements", "SR-001")
    write_validation_report(tmp_path, [{"id": "SR-001", "passed": True, "stale": False, "artifacts": []}])
    result = query_matrix(tmp_path, SystemScopeRef(kind="sr", ref="sr:SR-001"))
    row = result["rows"][0]
    assert row["subject"]["kind"] == "sr"
    assert validate(row, MATRIX_ROW_SCHEMA) == []

    for illegal_kind in ("task", "validation", "decision"):
        mutated = dict(row, subject={**row["subject"], "kind": illegal_kind})
        assert validate(mutated, MATRIX_ROW_SCHEMA) != []


def test_envelope_top_level_scope_kind_enum_matches_bundle_and_sr_only(tmp_path):
    # The envelope's top-level `scope`/`brief.scope`/`matrix.scope` use a
    # narrower kind enum (bundle|sr) than matrixRow.subject (sr|task|
    # validation|decision) -- they must not share one loosely-typed def.
    write_sr(tmp_path / "requirements", "SR-001")
    envelope = {
        "scope": {"kind": "task", "ref": "task:T-001"},  # illegal top-level kind
        "brief": query_brief(tmp_path, SystemScopeRef(kind="sr", ref="sr:SR-001")),
        "matrix": query_matrix(tmp_path, SystemScopeRef(kind="sr", ref="sr:SR-001")),
        "timeline": query_timeline(tmp_path, SystemScopeRef(kind="sr", ref="sr:SR-001")),
        "guide": query_guide(tmp_path, SystemScopeRef(kind="sr", ref="sr:SR-001")),
    }
    assert validate(envelope, RESPONSE_SCHEMA) != []


def test_timeline_event_rejected_by_event_schema_is_also_rejected_by_envelope(tmp_path):
    # Same drift-guard shape as test_matrix_row_rejected_by_row_schema_is_
    # also_rejected_by_envelope above, for the timeline's own inlined defs
    # (system_response.schema.json's timelineEvent/timelineSubjectRef vs.
    # system_timeline_event.schema.json) -- Task 2's report flagged this
    # exact kind of drift as a review-round loss, so both directions get a
    # test rather than just eyeballing that the two files match.
    write_sr(tmp_path / "requirements", "SR-001")
    write_task(tmp_path / "tasks", "T-001", status="done", satisfies=["SR-001"])
    write_decision_artifact(tmp_path, task_id="T-001")
    scope = SystemScopeRef(kind="sr", ref="sr:SR-001")

    timeline = query_timeline(tmp_path, scope)
    assert timeline["events"], "fixture must actually produce an event to mutate"
    timeline["events"][0]["subject"]["kind"] = "validation"  # not in task|sr|run|manifest

    assert validate(timeline["events"][0], TIMELINE_EVENT_SCHEMA) != []

    envelope = {
        "scope": {"kind": scope.kind, "ref": scope.ref},
        "brief": query_brief(tmp_path, scope),
        "matrix": query_matrix(tmp_path, scope),
        "timeline": timeline,
        "guide": query_guide(tmp_path, scope),
    }
    assert validate(envelope, RESPONSE_SCHEMA) != []


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


def _write_adr_fixture(repo_root, filename, text):
    directory = repo_root / "docs" / "adr"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / filename).write_text(text, encoding="utf-8")


_ADR_TEXT = """---
id: ADR-0001
title: Typed Contract Spine
status: accepted
superseded_by: null
---

## Decision
Keep the existing packages.

## Consequences
No parallel tree exists.
"""


def test_adr_is_a_legal_scope_ref(tmp_path):
    scope = parse_scope_ref("adr:ADR-0001")
    assert scope.kind == "adr"
    assert scope.ref == "adr:ADR-0001"


def test_adr_brief_renders_title_status_and_each_section_as_recorded_claims(tmp_path):
    _write_adr_fixture(tmp_path, "0001-spine.md", _ADR_TEXT)

    result = query_brief(tmp_path, parse_scope_ref("adr:ADR-0001"))

    texts = [c["text"] for c in result["claims"]]
    assert texts == [
        "Typed Contract Spine",
        "status: accepted",
        "Decision: Keep the existing packages.",
        "Consequences: No parallel tree exists.",
    ]
    assert {c["kind"] for c in result["claims"]} == {"recorded"}
    assert {c["freshness"]["state"] for c in result["claims"]} == {"fresh"}


def test_adr_brief_cites_the_adr_file_with_a_content_hash(tmp_path):
    _write_adr_fixture(tmp_path, "0001-spine.md", _ADR_TEXT)

    result = query_brief(tmp_path, parse_scope_ref("adr:ADR-0001"))

    citation = result["claims"][0]["citations"][0]
    assert citation["kind"] == "decision"
    assert citation["path"].endswith("0001-spine.md")
    assert citation["sha256"] is not None


def test_adr_brief_for_an_unknown_id_raises_scope_not_found(tmp_path):
    _write_adr_fixture(tmp_path, "0001-spine.md", _ADR_TEXT)

    with pytest.raises(ScopeNotFoundError):
        query_brief(tmp_path, parse_scope_ref("adr:ADR-9999"))


def test_adr_brief_reports_schema_errors_as_a_missing_claim(tmp_path):
    _write_adr_fixture(
        tmp_path,
        "0002-bad.md",
        "---\nid: ADR-0002\ntitle: Bad\nstatus: rubbish\n---\n\n## Decision\nx.\n",
    )

    result = query_brief(tmp_path, parse_scope_ref("adr:ADR-0002"))

    missing = [c for c in result["claims"] if c["kind"] == "missing"]
    assert missing, "a schema violation must be visible, not silently tolerated"
    assert missing[0]["freshness"]["state"] == "n/a"


def test_list_scopes_includes_declared_adrs(tmp_path):
    _write_adr_fixture(tmp_path, "0001-spine.md", _ADR_TEXT)

    refs = [s.ref for s in list_scopes(tmp_path)]

    assert "adr:ADR-0001" in refs


# ---------------------------------------------------------------------------
# Working traversal: requirement -> satisfying tasks -> design -> files
# ---------------------------------------------------------------------------


def _write_task_traversal(root, task_id, sr_id, source_plan):
    """A task with a `satisfies` link and a `source_plan`, for the traversal."""
    tasks_dir = root / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    (tasks_dir / f"{task_id}-traversal.md").write_text(
        f"---\nid: {task_id}\ntitle: T\nstatus: done\ndod: []\n"
        f"satisfies:\n- {sr_id}\nsource_plan: docs/superpowers/plans/{source_plan}\n"
        f"---\nbody\n",
        encoding="utf-8",
    )
    return task_id


def _write_adr(root, filename, adr_id):
    adr_dir = root / "docs" / "adr"
    adr_dir.mkdir(parents=True, exist_ok=True)
    (adr_dir / filename).write_text(
        f"---\nid: {adr_id}\ntitle: T\nstatus: accepted\n---\nbody\n",
        encoding="utf-8",
    )
    return adr_id


def test_traversal_chain_requirement_and_tasks(tmp_path):
    """The sr: anchor yields its satisfying tasks; design/files are lists."""
    write_sr(tmp_path / "requirements", "SR-001")
    _write_task_traversal(tmp_path, "T-001", "SR-001", "2026-08-12-P.md")
    _write_task_traversal(tmp_path, "T-002", "SR-001", "2026-08-12-P.md")
    trav = query_traversal(tmp_path, parse_scope_ref("sr:SR-001"))
    assert trav["requirement"] == "SR-001"
    assert "T-001" in trav["tasks"]
    assert "T-002" in trav["tasks"]
    assert isinstance(trav["design"], list)
    assert isinstance(trav["files"], list)


def test_traversal_full_chain_plan_spec_design_files(tmp_path):
    """The full chain: task -> source_plan -> spec_ref -> bundle ADR + files."""
    write_sr(tmp_path / "requirements", "SR-001")
    _write_task_traversal(tmp_path, "T-001", "SR-001", "2026-08-12-P.md")
    # a plan whose body names its spec (trace spec_ref edge source)
    plans = tmp_path / "docs" / "superpowers" / "plans"
    plans.mkdir(parents=True, exist_ok=True)
    (plans / "2026-08-12-P.md").write_text(
        "# Plan P\n\nSpec: docs/superpowers/specs/2026-08-12-S.md\n",
        encoding="utf-8",
    )
    write_spec(tmp_path, "2026-08-12-S.md")
    # a bundle that declares the sr and the design ADR; the ADR loader reads
    # it from docs/adr (masked so list_scopes does not also list it).
    _write_adr(tmp_path, "0001-spine.md", "ADR-0001")
    write_bundle(tmp_path / "bundles", "b1", "B1", ["sr:SR-001", "adr:ADR-0001"])
    # a recorded evidence manifest naming the file T-001 changed
    write_run_manifest(tmp_path, run_id="run-001", task_id="T-001", changed_files=["src/a.py"])
    trav = query_traversal(tmp_path, parse_scope_ref("sr:SR-001"))
    assert "T-001" in trav["tasks"]
    assert "adr:ADR-0001" in trav["design"]
    assert "src/a.py" in trav["files"]


def test_traversal_bundle_scope_aggregates_sr_members(tmp_path):
    """A bundle: anchor unions the traversal over its sr members."""
    write_sr(tmp_path / "requirements", "SR-001")
    write_sr(tmp_path / "requirements", "SR-002")
    _write_task_traversal(tmp_path, "T-001", "SR-001", "2026-08-12-P.md")
    _write_task_traversal(tmp_path, "T-002", "SR-002", "2026-08-12-P.md")
    write_bundle(tmp_path / "bundles", "b1", "B1", ["sr:SR-001", "sr:SR-002"])
    trav = query_traversal(tmp_path, parse_scope_ref("bundle:b1"))
    assert "SR-001" in trav["requirement"]
    assert "SR-002" in trav["requirement"]
    assert "T-001" in trav["tasks"]
    assert "T-002" in trav["tasks"]


def test_traversal_bundle_scope_shares_one_lookup_across_sr_members(tmp_path, monkeypatch):
    write_sr(tmp_path / "requirements", "SR-001")
    write_sr(tmp_path / "requirements", "SR-002")
    write_bundle(tmp_path / "bundles", "b1", "B1", ["sr:SR-001", "sr:SR-002"])
    seen = []
    real_bundles_containing = queries.bundles.bundles_containing

    def capture_bundles_containing(repo_root, ref, *, lookup):
        seen.append(lookup)
        return real_bundles_containing(repo_root, ref, lookup=lookup)

    monkeypatch.setattr(queries.bundles, "bundles_containing", capture_bundles_containing)

    query_traversal(tmp_path, parse_scope_ref("bundle:b1"))

    assert len(seen) == 2
    assert seen[0] is seen[1]


def test_traversal_loads_trace_nodes_once_for_a_multi_sr_bundle(tmp_path, monkeypatch):
    write_sr(tmp_path / "requirements", "SR-001")
    write_sr(tmp_path / "requirements", "SR-002")
    write_bundle(tmp_path / "bundles", "b1", "B1", ["sr:SR-001", "sr:SR-002"])
    real_load_nodes = queries.trace_model.load_nodes
    calls = 0

    def counted_load_nodes(root):
        nonlocal calls
        calls += 1
        return real_load_nodes(root)

    monkeypatch.setattr(queries.trace_model, "load_nodes", counted_load_nodes)

    query_traversal(tmp_path, parse_scope_ref("bundle:b1"))

    assert calls == 1
