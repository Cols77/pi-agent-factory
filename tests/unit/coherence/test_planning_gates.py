from __future__ import annotations

import pytest

from coherence.planning import gates
from coherence.planning.gates import _validate_feat17_bundle_members

pytestmark = pytest.mark.unit


_DOSSIER_MEMBERS = [
    "feat:FEAT-017",
    "spec:docs/superpowers/specs/2026-08-27-feat17-planning-bootstrap-design.md",
    "plan:docs/superpowers/plans/2026-08-27-feat17-planning-workflow-plan.md",
    "task:T-032",
    "task:T-045",
]
_OWNED_IDS = ["SR-043", "SR-044", "SR-051", "SR-052", "SR-053", "SR-054", "SR-055"]


def test_feat17_bundle_accepts_owned_requirements_and_extra_dossier_refs() -> None:
    members = [*_DOSSIER_MEMBERS, *(f"sr:{req_id}" for req_id in _OWNED_IDS)]

    assert _validate_feat17_bundle_members(members, _OWNED_IDS) == (
        True,
        "FEAT-017 bundle ownership is current",
    )


def test_feat17_bundle_rejects_non_owned_requirements() -> None:
    members = [*_DOSSIER_MEMBERS, *(f"sr:{req_id}" for req_id in [*_OWNED_IDS, "SR-050"])]

    assert _validate_feat17_bundle_members(members, _OWNED_IDS) == (
        False,
        "FEAT-017 bundle contains non-owned requirement(s): SR-050",
    )


def test_feat17_bundle_rejects_duplicate_members() -> None:
    members = [*_DOSSIER_MEMBERS, *(f"sr:{req_id}" for req_id in _OWNED_IDS), "sr:SR-055"]

    assert _validate_feat17_bundle_members(members, _OWNED_IDS) == (
        False,
        "FEAT-017 bundle has duplicate members",
    )


def test_feat17_bundle_rejects_non_list_members() -> None:
    assert _validate_feat17_bundle_members("feat:FEAT-017", _OWNED_IDS) == (
        False,
        "FEAT-017 bundle has invalid members",
    )


def test_feat17_bundle_reports_missing_requirements_before_other_membership_errors() -> None:
    assert _validate_feat17_bundle_members(["feat:not-FEAT-017"], _OWNED_IDS) == (
        False,
        "FEAT-017 bundle is missing required member(s): "
        "SR-043, SR-044, SR-051, SR-052, SR-053, SR-054, SR-055",
    )


def test_feat17_bundle_rejects_invalid_feature_membership_after_requirements() -> None:
    members = [*(f"sr:{req_id}" for req_id in _OWNED_IDS), "feat:not-FEAT-017"]

    assert _validate_feat17_bundle_members(members, _OWNED_IDS) == (
        False,
        "FEAT-017 bundle contains an invalid feature membership",
    )


def test_requirement_consent_returns_bundle_detail_without_wrapper(tmp_path, monkeypatch) -> None:
    feature_path = tmp_path / "docs" / "features" / "FEAT-017.md"
    bundle_path = tmp_path / "bundles" / "FEAT-017.json"
    feature_path.parent.mkdir(parents=True)
    bundle_path.parent.mkdir()
    feature_path.write_text("placeholder", encoding="utf-8")
    bundle_path.write_text(
        '{"id": "FEAT-017", "members": ["feat:FEAT-017"]}', encoding="utf-8"
    )
    monkeypatch.setattr(
        gates,
        "_read_metadata",
        lambda path: {"id": "FEAT-017", "requirements": _OWNED_IDS},
    )

    assert gates.validate_requirement_consent(tmp_path, "run-1", tmp_path / "spec.md") == (
        False,
        "FEAT-017 bundle is missing required member(s): "
        "SR-043, SR-044, SR-051, SR-052, SR-053, SR-054, SR-055",
    )
