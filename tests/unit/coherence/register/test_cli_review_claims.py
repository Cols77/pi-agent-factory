from __future__ import annotations

import pytest

from coherence.register.cli import cmd_review

pytestmark = pytest.mark.unit

# SR-049: produced-code traceability. `coherence register review
# --check-claims` reconciles the claim denominator (T3's `claimed_paths`)
# against declared relations and blocks on any `changed_but_undeclared`
# finding. `--no-ingest` keeps the gate read-only, for CI checkouts that must
# not persist an evidence manifest.


@pytest.mark.sr("SR-049")
def test_check_claims_exits_non_zero_on_a_claimed_but_undeclared_path(claims_repo):
    assert cmd_review(claims_repo, None, check_claims=True, no_ingest=True) == 1


@pytest.mark.sr("SR-049")
def test_check_claims_exits_zero_when_every_claimed_path_is_declared(declared_repo):
    assert cmd_review(declared_repo, None, check_claims=True, no_ingest=True) == 0


@pytest.mark.sr("SR-049")
def test_check_claims_blocks_under_the_prototype_profile_too(claims_repo):
    """Unlike the fidelity check, claim reconciliation has no judge in the
    loop, so it blocks under every compiled profile."""
    (claims_repo / ".factory" / "factory.yaml").write_text(
        "profile: prototype\ngates:\n  full: []\n", encoding="utf-8"
    )
    assert cmd_review(claims_repo, None, check_claims=True, no_ingest=True) == 1


@pytest.mark.sr("SR-049")
def test_no_ingest_leaves_the_evidence_store_untouched(claims_repo):
    before = sorted(p.name for p in (claims_repo / "evidence" / "runs").glob("*.json"))
    assert before, "fixture must have ingested a manifest for this to mean anything"
    cmd_review(claims_repo, None, check_claims=True, no_ingest=True)
    after = sorted(p.name for p in (claims_repo / "evidence" / "runs").glob("*.json"))
    assert before == after
