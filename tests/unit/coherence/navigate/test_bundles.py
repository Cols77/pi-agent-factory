"""`contract:<id>` members in declared feature bundles (optional-contract-artifacts task 6).

The bundle parser accepts a `contract:` member kind; resolution to the
artifact's real file goes through the same *compiled* contract catalog that the
trace surface uses -- never by re-parsing the catalog YAML in bundle code. An id
that is not a cataloged contract is unresolved (reported `missing` by the
caller), so one bad member never drops the whole bundle.

No-catalog invariance is non-negotiable: a project with no ``.factory/contracts.yaml``
keeps every existing bundle member resolving exactly as before and gains no
contract-specific rows or findings.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


pytestmark = pytest.mark.unit

CATALOG_SCHEMA = "coherence.contract-catalog.v1"


def _write(root: Path, rel: str, content: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _catalog(root: Path, document: dict) -> None:
    _write(root, ".factory/contracts.yaml", json.dumps(document))


def _contract_project(root: Path) -> None:
    """A cataloged contract plus a bundle that declares it as a member."""
    _catalog(
        root,
        {
            "schema": CATALOG_SCHEMA,
            "contracts": [
                {
                    "id": "WIRE",
                    "path": "docs/wire.schema.json",
                    "kind": "json_schema",
                    "status": "active",
                }
            ],
        },
    )
    _write(root, "docs/wire.schema.json", '{"$ref": "#/definitions/X"}')
    _write(
        root,
        "bundles/FEAT-001.json",
        json.dumps(
            {
                "id": "FEAT-001",
                "label": "contract feature",
                "members": ["contract:WIRE", "spec:docs/wire.schema.json"],
            }
        ),
    )


def _empty_bundle(root: Path) -> None:
    """A bundle whose members reference nothing contract-related."""
    _write(
        root,
        "bundles/FEAT-002.json",
        json.dumps(
            {
                "id": "FEAT-002",
                "label": "no contract",
                "members": ["spec:docs/other.md"],
            }
        ),
    )
    _write(root, "docs/other.md", "# other")


def test_contract_member_ref_parses(tmp_path: Path) -> None:
    from coherence.navigate.bundles import _parse_member_ref

    parsed = _parse_member_ref("contract:WIRE")
    assert parsed is not None
    assert parsed.kind == "contract"
    assert parsed.ref == "contract:WIRE"


def test_unresolved_contract_id_is_reported_missing_not_raised(tmp_path: Path) -> None:
    """A `contract:<id>` for an id never cataloged resolves to nothing.

    One bad member must degrade the bundle (a `missing` claim in `unresolved`
    via the caller's member resolution), never raise and drop the whole bundle.
    """
    from coherence.navigate.bundles import _parse_member_ref

    _contract_project(tmp_path)
    parsed = _parse_member_ref("contract:NOPE")
    assert parsed is not None  # well-formed contract ref parses fine
    from coherence.navigate.coverage import member_target

    assert member_target(tmp_path, "contract:NOPE") is None


def test_cataloged_contract_resolves_through_compiled_catalog(tmp_path: Path) -> None:
    """A contract that IS cataloged resolves to its real repo-relative file."""
    from coherence.navigate.coverage import member_target

    _contract_project(tmp_path)
    target = member_target(tmp_path, "contract:WIRE")
    assert target is not None
    assert target == (tmp_path / "docs" / "wire.schema.json").resolve()
    assert target.is_file()


def test_no_catalog_preserves_existing_bundle_members(tmp_path: Path) -> None:
    """Without a catalog, existing non-contract members still resolve and the
    bundle still loads -- no contract artifacts, no contract rows."""
    from coherence.navigate.bundles import list_bundles
    from coherence.navigate.coverage import member_target

    _empty_bundle(tmp_path)
    bundles = list_bundles(tmp_path / "bundles")
    assert [b.id for b in bundles] == ["FEAT-002"]
    assert member_target(tmp_path, "spec:docs/other.md") == (
        tmp_path / "docs" / "other.md"
    ).resolve()
