from __future__ import annotations

import pytest

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


def test_feat17_bundle_allows_dossier_artifacts_and_owned_sr_members() -> None:
    members = [*_DOSSIER_MEMBERS, *(f"sr:{req_id}" for req_id in _OWNED_IDS)]

    assert _validate_feat17_bundle_members(members, _OWNED_IDS) == (True, "")


def test_feat17_bundle_rejects_shared_sr050_and_foreign_sr_members() -> None:
    members = [*_DOSSIER_MEMBERS, *(f"sr:{req_id}" for req_id in [*_OWNED_IDS[:2], "SR-050", *_OWNED_IDS[2:]])]

    assert _validate_feat17_bundle_members(members, _OWNED_IDS) == (
        False,
        "unexpected SR members: SR-050",
    )


def test_feat17_bundle_rejects_malformed_duplicate_members() -> None:
    members = [*_DOSSIER_MEMBERS, *(f"sr:{req_id}" for req_id in _OWNED_IDS), "sr:SR-055"]

    assert _validate_feat17_bundle_members(members, _OWNED_IDS) == (
        False,
        "bundle members contain duplicates",
    )
    assert _validate_feat17_bundle_members([*members[:-1], "../SR-054"], _OWNED_IDS)[0] is False
