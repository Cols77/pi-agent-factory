from __future__ import annotations

import pytest

from coherence.planning.gates import _validate_feat17_bundle_members

pytestmark = pytest.mark.unit


_DOSSIER_MEMBERS = [
    "feat:FEAT-017",
    "spec:docs/superpowers/specs/2026-08-27-feat17-planning-bootstrap-design.md",
    "plan:docs/superpowers/plans/2026-08-27-feat17-planning-workflow-plan.md",
    "task:T-032-feat17-planning-workflow.md",
]


def test_feat17_bundle_allows_dossier_artifacts_and_owned_sr_members() -> None:
    members = [*_DOSSIER_MEMBERS, "sr:SR-043", "sr:SR-044", "sr:SR-051", "sr:SR-052", "sr:SR-053", "sr:SR-054", "sr:SR-055"]

    assert _validate_feat17_bundle_members(members)


def test_feat17_bundle_rejects_shared_sr050_and_foreign_sr_members() -> None:
    members = [*_DOSSIER_MEMBERS, "sr:SR-043", "sr:SR-044", "sr:SR-050", "sr:SR-051", "sr:SR-052", "sr:SR-053", "sr:SR-054", "sr:SR-055"]

    assert not _validate_feat17_bundle_members(members)

    foreign = [*_DOSSIER_MEMBERS, "sr:SR-043", "sr:SR-044", "sr:SR-051", "sr:SR-052", "sr:SR-053", "sr:SR-054", "sr:SR-055", "sr:SR-999"]
    assert not _validate_feat17_bundle_members(foreign)


def test_feat17_bundle_rejects_malformed_duplicate_members() -> None:
    members = [*_DOSSIER_MEMBERS, "sr:SR-043", "sr:SR-044", "sr:SR-051", "sr:SR-052", "sr:SR-053", "sr:SR-054", "sr:SR-055", "sr:SR-055"]

    assert not _validate_feat17_bundle_members(members)
    assert not _validate_feat17_bundle_members([*members[:-1], "../SR-054"])
