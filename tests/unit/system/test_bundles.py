"""Tests for factory.system.bundles: declared-bundle loading (§3.3).

A bundle is an index, not an assertion: it carries a label and exact member
refs, nothing else. An absent bundle directory is a legitimate state.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from factory.system.bundles import list_bundles, load_bundle
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


def test_empty_members_list_is_legal(tmp_path):
    bundles_dir = tmp_path / "bundles"
    _write_bundle(bundles_dir, "empty", {"id": "empty", "label": "Empty bundle", "members": []})

    bundle = load_bundle(bundles_dir, "empty")

    assert bundle.members == []
    assert bundle.unresolved == []
    assert bundle.degraded is False
