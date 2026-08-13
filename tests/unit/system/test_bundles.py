"""Tests for factory.system.bundles: declared-bundle loading (§3.3).

A bundle is an index, not an assertion: it carries a label and exact member
refs, nothing else. An absent bundle directory is a legitimate state.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from factory.system.bundles import BundleIdMismatchError, list_bundle_errors, list_bundles, load_bundle
from factory.system.models import ClaimClass, CitationKind, FreshnessState

pytestmark = pytest.mark.unit


def _write_bundle(bundles_dir: Path, bundle_id: str, payload: dict) -> Path:
    bundles_dir.mkdir(parents=True, exist_ok=True)
    path = bundles_dir / f"{bundle_id}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# A bundle parses to a label plus a list of exact member refs
# ---------------------------------------------------------------------------


def test_bundle_parses_label_and_members(tmp_path):
    bundles_dir = tmp_path / "bundles"
    _write_bundle(
        bundles_dir,
        "evidence-lifecycle",
        {
            "id": "evidence-lifecycle",
            "label": "Evidence Lifecycle & Recovery",
            "members": [
                "spec:docs/superpowers/specs/2026-08-07-evidence.md",
                "plan:docs/superpowers/plans/2026-08-07-evidence.md",
                "task:T-045",
                "sr:SR-012",
            ],
        },
    )

    bundle = load_bundle(bundles_dir, "evidence-lifecycle")

    assert bundle.label == "Evidence Lifecycle & Recovery"
    assert [m.ref for m in bundle.members] == [
        "spec:docs/superpowers/specs/2026-08-07-evidence.md",
        "plan:docs/superpowers/plans/2026-08-07-evidence.md",
        "task:T-045",
        "sr:SR-012",
    ]
    assert [m.kind for m in bundle.members] == ["spec", "plan", "task", "sr"]
    assert bundle.unresolved == []
    assert bundle.degraded is False


# ---------------------------------------------------------------------------
# The schema rejects any status, claim, rationale, or free-prose field
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "extra_field",
    ["status", "claim", "rationale", "notes", "summary"],
)
def test_bundle_schema_rejects_narrative_fields(tmp_path, extra_field):
    bundles_dir = tmp_path / "bundles"
    _write_bundle(
        bundles_dir,
        "narrated",
        {
            "id": "narrated",
            "label": "Narrated bundle",
            "members": ["task:T-001"],
            extra_field: "this should never be allowed",
        },
    )

    with pytest.raises(ValueError):
        load_bundle(bundles_dir, "narrated")


# ---------------------------------------------------------------------------
# An unresolvable member is reported missing and degrades the bundle
# without dropping it
# ---------------------------------------------------------------------------


def test_unresolvable_member_is_reported_missing_and_degrades_bundle(tmp_path):
    bundles_dir = tmp_path / "bundles"
    _write_bundle(
        bundles_dir,
        "partial",
        {
            "id": "partial",
            "label": "Partially broken bundle",
            "members": [
                "task:T-001",
                "not-a-real-kind:whatever",
                "sr:",  # empty identifier
            ],
        },
    )

    bundle = load_bundle(bundles_dir, "partial")

    # the bundle still loads and keeps the good member
    assert [m.ref for m in bundle.members] == ["task:T-001"]

    # the bad members are reported missing, not silently dropped
    assert len(bundle.unresolved) == 2
    for claim in bundle.unresolved:
        assert claim.kind is ClaimClass.MISSING
        assert claim.freshness.state is FreshnessState.NA

    # the bundle degrades but is not dropped
    assert bundle.degraded is True
    assert bundle.label == "Partially broken bundle"


def test_unresolvable_member_claim_cites_the_bundle_file_that_declared_it(tmp_path):
    # An unresolved-member claim previously carried no citation at all --
    # a reader had no way to check which bundle file declared the bad ref.
    bundles_dir = tmp_path / "bundles"
    path = _write_bundle(
        bundles_dir,
        "partial",
        {"id": "partial", "label": "Partially broken bundle", "members": ["not-a-real-kind:whatever"]},
    )

    bundle = load_bundle(bundles_dir, "partial")

    assert len(bundle.unresolved) == 1
    claim = bundle.unresolved[0]
    assert len(claim.citations) == 1
    citation = claim.citations[0]
    assert citation.kind is CitationKind.BUNDLE
    assert citation.path == str(path)
    assert citation.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Duplicate members are rejected
# ---------------------------------------------------------------------------


def test_duplicate_members_are_rejected(tmp_path):
    bundles_dir = tmp_path / "bundles"
    _write_bundle(
        bundles_dir,
        "dupes",
        {
            "id": "dupes",
            "label": "Duplicate members",
            "members": ["task:T-001", "task:T-001"],
        },
    )

    with pytest.raises(ValueError):
        load_bundle(bundles_dir, "dupes")


# ---------------------------------------------------------------------------
# An absent bundle directory returns no bundles and raises nothing
# ---------------------------------------------------------------------------


def test_absent_bundle_directory_returns_empty_list(tmp_path):
    bundles_dir = tmp_path / "does-not-exist"
    assert bundles_dir.exists() is False

    result = list_bundles(bundles_dir)

    assert result == []
    # the directory must not be created as a side effect of reading
    assert bundles_dir.exists() is False


def test_list_bundles_reports_no_bundle_scopes_when_dir_absent(tmp_path):
    # `scope` (a later task) enumerates bundle scopes from list_bundles(); an
    # empty list here is exactly what makes it report no bundle scopes.
    bundles_dir = tmp_path / "does-not-exist"
    assert list_bundles(bundles_dir) == []


def test_list_bundles_finds_all_declared_bundles(tmp_path):
    bundles_dir = tmp_path / "bundles"
    _write_bundle(bundles_dir, "alpha", {"id": "alpha", "label": "Alpha", "members": []})
    _write_bundle(bundles_dir, "beta", {"id": "beta", "label": "Beta", "members": ["task:T-001"]})

    bundles = list_bundles(bundles_dir)

    assert sorted(b.id for b in bundles) == ["alpha", "beta"]


# ---------------------------------------------------------------------------
# The bundle itself is emitted as a citation for the membership list
# ---------------------------------------------------------------------------


def test_bundle_is_its_own_citation(tmp_path):
    bundles_dir = tmp_path / "bundles"
    payload = {"id": "cited", "label": "Cited bundle", "members": ["task:T-001"]}
    path = _write_bundle(bundles_dir, "cited", payload)

    bundle = load_bundle(bundles_dir, "cited")

    assert bundle.citation.kind is CitationKind.BUNDLE
    assert Path(bundle.citation.path) == path
    assert bundle.citation.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# One malformed bundle file does not abort the whole listing (design SS8:
# failures degrade only the affected scope)
# ---------------------------------------------------------------------------


def test_list_bundles_skips_one_malformed_file_without_aborting(tmp_path):
    bundles_dir = tmp_path / "bundles"
    _write_bundle(bundles_dir, "alpha", {"id": "alpha", "label": "Alpha", "members": []})
    _write_bundle(bundles_dir, "beta", {"id": "beta", "label": "Beta", "members": ["task:T-001"]})
    (bundles_dir / "broken.json").write_text("{not json", encoding="utf-8")

    bundles = list_bundles(bundles_dir)

    assert sorted(b.id for b in bundles) == ["alpha", "beta"]


def test_list_bundles_skips_a_file_that_fails_schema_validation(tmp_path):
    bundles_dir = tmp_path / "bundles"
    _write_bundle(bundles_dir, "alpha", {"id": "alpha", "label": "Alpha", "members": []})
    _write_bundle(
        bundles_dir,
        "narrated",
        {"id": "narrated", "label": "Narrated", "members": [], "status": "not allowed"},
    )

    bundles = list_bundles(bundles_dir)

    assert [b.id for b in bundles] == ["alpha"]


def test_empty_members_list_is_legal(tmp_path):
    bundles_dir = tmp_path / "bundles"
    _write_bundle(bundles_dir, "empty", {"id": "empty", "label": "Empty bundle", "members": []})

    bundle = load_bundle(bundles_dir, "empty")

    assert bundle.members == []
    assert bundle.unresolved == []
    assert bundle.degraded is False


# ---------------------------------------------------------------------------
# A bundle file's declared `id` must exactly equal its filename stem
# (findings 4/5) -- a distinct, visible failure, not "not found"
# ---------------------------------------------------------------------------


def test_load_bundle_raises_id_mismatch_when_id_does_not_match_filename(tmp_path):
    bundles_dir = tmp_path / "bundles"
    # File is "foo.json" but the payload declares id "bar" -- schema-legal
    # on its own, but not reachable as either "foo" or "bar".
    _write_bundle(bundles_dir, "foo", {"id": "bar", "label": "X", "members": []})

    with pytest.raises(BundleIdMismatchError):
        load_bundle(bundles_dir, "foo")


def test_bundle_id_mismatch_error_is_a_value_error(tmp_path):
    # Deliberately a ValueError subclass -- NOT a FileNotFoundError -- so it
    # is never mistaken for "the file does not exist" and is still caught by
    # list_bundles' generic (OSError, ValueError) handling.
    bundles_dir = tmp_path / "bundles"
    _write_bundle(bundles_dir, "foo", {"id": "bar", "label": "X", "members": []})

    with pytest.raises(ValueError):
        load_bundle(bundles_dir, "foo")


def test_list_bundles_still_skips_an_id_mismatched_file(tmp_path):
    bundles_dir = tmp_path / "bundles"
    _write_bundle(bundles_dir, "foo", {"id": "bar", "label": "X", "members": []})
    _write_bundle(bundles_dir, "good", {"id": "good", "label": "Good", "members": []})

    bundles = list_bundles(bundles_dir)

    assert [b.id for b in bundles] == ["good"]


def test_list_bundle_errors_reports_id_mismatch(tmp_path):
    bundles_dir = tmp_path / "bundles"
    _write_bundle(bundles_dir, "foo", {"id": "bar", "label": "X", "members": []})

    errors = list_bundle_errors(bundles_dir)

    assert len(errors) == 1
    assert errors[0].bundle_id == "foo"
    assert "bar" in errors[0].error


def test_list_bundle_errors_reports_malformed_json(tmp_path):
    bundles_dir = tmp_path / "bundles"
    (bundles_dir).mkdir(parents=True, exist_ok=True)
    (bundles_dir / "broken.json").write_text("{not json", encoding="utf-8")

    errors = list_bundle_errors(bundles_dir)

    assert len(errors) == 1
    assert errors[0].bundle_id == "broken"


def test_list_bundle_errors_reports_schema_violation(tmp_path):
    bundles_dir = tmp_path / "bundles"
    _write_bundle(
        bundles_dir,
        "narrated",
        {"id": "narrated", "label": "Narrated", "members": [], "status": "not allowed"},
    )

    errors = list_bundle_errors(bundles_dir)

    assert len(errors) == 1
    assert errors[0].bundle_id == "narrated"


def test_list_bundle_errors_empty_when_all_bundles_load_cleanly(tmp_path):
    bundles_dir = tmp_path / "bundles"
    _write_bundle(bundles_dir, "good", {"id": "good", "label": "Good", "members": []})

    assert list_bundle_errors(bundles_dir) == []


def test_list_bundle_errors_on_absent_dir_is_empty(tmp_path):
    bundles_dir = tmp_path / "does-not-exist"
    assert list_bundle_errors(bundles_dir) == []


# ---------------------------------------------------------------------------
# `adr:` is an id-based member kind (SP-A Task 2)
# ---------------------------------------------------------------------------


def test_adr_member_ref_resolves_by_id(tmp_path):
    bundles_dir = tmp_path / "bundles"
    _write_bundle(
        bundles_dir,
        "shark-detection",
        {
            "id": "shark-detection",
            "label": "Shark detection",
            "members": ["adr:ADR-0001", "sr:SR-007"],
        },
    )

    bundle = load_bundle(bundles_dir, "shark-detection")

    assert [m.kind for m in bundle.members] == ["adr", "sr"]
    assert [m.ref for m in bundle.members] == ["adr:ADR-0001", "sr:SR-007"]
    assert bundle.unresolved == []


def test_feature_metric_and_goal_member_refs_resolve_by_id(tmp_path):
    bundles_dir = tmp_path / "bundles"
    _write_bundle(
        bundles_dir,
        "navigator",
        {
            "id": "navigator",
            "label": "Navigator",
            "members": ["feat:FEAT-NAV-017", "metric:MET-NAV-004", "goal:GOAL-NAV-003"],
        },
    )

    bundle = load_bundle(bundles_dir, "navigator")

    assert [member.kind for member in bundle.members] == ["feat", "metric", "goal"]
    assert [member.ref for member in bundle.members] == [
        "feat:FEAT-NAV-017",
        "metric:MET-NAV-004",
        "goal:GOAL-NAV-003",
    ]
    assert bundle.unresolved == []


def test_adr_member_with_an_empty_identifier_does_not_resolve(tmp_path):
    bundles_dir = tmp_path / "bundles"
    _write_bundle(
        bundles_dir,
        "broken",
        {"id": "broken", "label": "Broken", "members": ["adr:"]},
    )

    bundle = load_bundle(bundles_dir, "broken")

    assert bundle.members == []
    assert [c.text for c in bundle.unresolved] == ["adr:"]
    assert bundle.unresolved[0].kind is ClaimClass.MISSING
    assert bundle.unresolved[0].freshness.state is FreshnessState.NA
