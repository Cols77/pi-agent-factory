"""Contract coverage in feature bundles (optional-contract-artifacts task 6).

A declared contract can be reported bundled (cataloged and in a bundle),
unbundled (cataloged but in no bundle), or missing (declared but not resolvable),
without changing the semantics of the existing scope refs (`sr`/`task`/`spec`/
`plan`/`adr`).

No-catalog invariance: with no ``.factory/contracts.yaml`` the coverage output is
byte-identical to the pre-change output -- the contract kind contributes ZERO
rows/artifacts and no new finding (no 0/0 row).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


pytestmark = pytest.mark.unit

CATALOG_SCHEMA = "coherence.contract-catalog.v1"

NO_CATALOG_KINDS = ["sr", "task", "spec", "plan", "adr"]


def _write(root: Path, rel: str, content: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _catalog(root: Path, document: dict) -> None:
    _write(root, ".factory/contracts.yaml", json.dumps(document))


def _project_with_contracts(root: Path, *, bundled: list[str], declared: list[str]) -> None:
    """A catalog declaring the given contracts, each with a real artifact file."""
    contracts = [
        {
            "id": cid,
            "path": f"contracts/{cid.lower()}.schema.json",
            "kind": "json_schema",
            "status": "active",
        }
        for cid in declared
    ]
    _catalog(root, {"schema": CATALOG_SCHEMA, "contracts": contracts})
    for cid in declared:
        _write(root, f"contracts/{cid.lower()}.schema.json", '{"type": "object"}')
    members = [f"contract:{cid}" for cid in bundled]
    _write(
        root,
        "bundles/FEAT-001.json",
        json.dumps({"id": "FEAT-001", "label": "contract feature", "members": members}),
    )


def _coverage(root: Path) -> dict:
    from coherence.navigate.coverage import bundle_coverage

    from coherence.navigate.models import to_dict

    return to_dict(bundle_coverage(root))


def test_contract_bundled_when_cataloged_and_in_bundle(tmp_path: Path) -> None:
    from coherence.navigate.models import to_dict

    root = tmp_path / "project"
    _project_with_contracts(root, bundled=["WIRE"], declared=["WIRE"])

    from coherence.navigate.coverage import bundle_coverage

    cov = to_dict(bundle_coverage(root))
    contract = next(k for k in cov["kinds"] if k["kind"] == "contract")
    assert contract["total"] == 1
    assert contract["bundled"] == 1
    assert contract["unbundled"] == []


def test_cataloged_contract_not_in_bundle_is_unbundled(tmp_path: Path) -> None:
    root = tmp_path / "project"
    _project_with_contracts(root, bundled=[], declared=["WIRE", "FIX"])

    cov = _coverage(root)
    contract = next(k for k in cov["kinds"] if k["kind"] == "contract")
    assert contract["total"] == 2
    assert contract["bundled"] == 0
    assert contract["unbundled"] == ["contract:FIX", "contract:WIRE"]


def test_declared_but_unresolvable_contract_is_missing_not_a_row(tmp_path: Path) -> None:
    """Declared in a bundle but not cataloged -> nothing to count, reported missing
    by the caller's member resolution, and the coverage row is unaffected."""
    from coherence.navigate.coverage import member_target

    root = tmp_path / "project"
    _project_with_contracts(root, bundled=["NOPE"], declared=["WIRE"])

    # `contract:NOPE` is not a cataloged contract -> member target is None.
    assert member_target(root, "contract:NOPE") is None

    cov = _coverage(root)
    contract = next(k for k in cov["kinds"] if k["kind"] == "contract")
    # Only the genuinely cataloged WIRE is an artifact; NOPE is not fabricated.
    assert contract["total"] == 1
    assert contract["unbundled"] == ["contract:WIRE"]


def test_no_catalog_coverage_is_byte_identical_pre_change(tmp_path: Path) -> None:
    """No catalog -> the exact pre-change kind set and zero contract rows."""
    root = tmp_path / "project"
    root.mkdir(parents=True, exist_ok=True)

    cov = _coverage(root)
    assert [k["kind"] for k in cov["kinds"]] == NO_CATALOG_KINDS
    assert all(k["kind"] != "contract" for k in cov["kinds"])
    # No contract artifacts exist -- totals only reflect the base kinds.
    assert cov["total"] == 0
