"""Contract-specific trace findings (optional-contract-artifacts task 5).

Covers the four contract gap kinds computed from the compiler closure:

* ``contract_missing_provenance`` -- a declaration with no authority, no
  ``validates_against`` and no consumers.
* ``contract_reference_broken`` -- a declaration carrying a
  ``CONTRACT_REFERENCE_BROKEN`` diagnostic from the compiler.
* ``contract_file_missing`` -- a declaration carrying a
  ``CONTRACT_DECLARED_FILE_MISSING`` diagnostic (file absent at the resolved
  location).
* ``contract_missing_consumer`` -- declared ``consumers:`` but every consumer
  file is absent, or zero consumers declared together with zero
  ``validates_against``/authority.

Detail strings name the declaration id and its exact repo-relative path. The
freshness-class findings (stale consumer, stale fixture, validation
unavailable) are task 7's scope and are intentionally NOT computed here.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from coherence.trace.graph import build_graph
from coherence.trace.gaps import Gap

pytestmark = pytest.mark.unit

CATALOG_SCHEMA = "coherence.contract-catalog.v1"


def _write(root: Path, rel: str, content: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _catalog(root: Path, document: dict) -> None:
    _write(root, ".factory/contracts.yaml", json.dumps(document))


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _declaration(
    identifier: str,
    path: str,
    *,
    kind: str = "fixture",
    status: str = "active",
    authority: str | None = None,
    validates_against: str | None = None,
    consumers: list[str] | None = None,
) -> dict:
    entry: dict = {
        "id": identifier,
        "path": path,
        "kind": kind,
        "status": status,
    }
    if authority is not None:
        entry["authority"] = authority
    if validates_against is not None:
        entry["validates_against"] = validates_against
    if consumers is not None:
        entry["consumers"] = consumers
    return entry


def _build(tmp_path: Path, contracts: list[dict], files: dict[str, str]) -> object:
    root = _project(tmp_path)
    _catalog(root, {"schema": CATALOG_SCHEMA, "contracts": contracts})
    for rel, content in files.items():
        _write(root, rel, content)
    return build_graph(root)


def _gaps_by_kind(graph: object) -> dict[str, list[Gap]]:
    by_kind: dict[str, list[Gap]] = {}
    for gap in graph.gaps:
        by_kind.setdefault(gap.kind, []).append(gap)
    return by_kind


def _contract_gap_kinds(graph: object) -> set[str]:
    return {
        gap.kind
        for gap in graph.gaps
        if gap.kind.startswith("contract_")
    }


def test_missing_provenance_reported_for_orphaned_declaration(tmp_path: Path) -> None:
    graph = _build(
        tmp_path,
        [_declaration("ORPHAN", "orphans/orphan.json")],
        {"orphans/orphan.json": '{"a": 1}'},
    )
    gaps = _gaps_by_kind(graph)
    (gap,) = gaps["contract_missing_provenance"]
    assert gap.node_id == "contract:ORPHAN"
    assert "ORPHAN" in gap.detail
    assert "orphans/orphan.json" in gap.detail
    assert gap.disposition == "pending"


def test_broken_reference_reported_from_compiler_diagnostic(tmp_path: Path) -> None:
    graph = _build(
        tmp_path,
        [_declaration("WIRE", "docs/wire.schema.json", kind="json_schema")],
        {"docs/wire.schema.json": '{"$ref": "does-not-exist.json"}'},
    )
    gaps = _gaps_by_kind(graph)
    (gap,) = gaps["contract_reference_broken"]
    assert gap.node_id == "contract:WIRE"
    assert "WIRE" in gap.detail
    assert "docs/wire.schema.json" in gap.detail


def test_missing_declared_file_reported(tmp_path: Path) -> None:
    graph = _build(
        tmp_path,
        [_declaration("GHOST", "ghosts/ghost.json")],
        {},
    )
    gaps = _gaps_by_kind(graph)
    (gap,) = gaps["contract_file_missing"]
    assert gap.node_id == "contract:GHOST"
    assert "GHOST" in gap.detail
    assert "ghosts/ghost.json" in gap.detail
    # No node is emitted for a declaration whose file is absent -- the gap
    # reports the miss without pretending the artifact exists.
    assert not any(n.id == "contract:GHOST" for n in graph.nodes)


def test_missing_consumer_when_every_consumer_file_is_absent(tmp_path: Path) -> None:
    graph = _build(
        tmp_path,
        [
            _declaration(
                "WIRE",
                "docs/wire.schema.json",
                kind="json_schema",
                authority="spec:SPEC-1",
                consumers=["code:backend/app.py", "test:tests/seed.py"],
            )
        ],
        {"docs/wire.schema.json": '{"type": "object"}'},
    )
    gaps = _gaps_by_kind(graph)
    (gap,) = gaps["contract_missing_consumer"]
    assert gap.node_id == "contract:WIRE"
    assert "WIRE" in gap.detail
    # The missing consumer paths are named exactly.
    assert "backend/app.py" in gap.detail
    assert "tests/seed.py" in gap.detail


def test_missing_consumer_when_zero_relations_declared(tmp_path: Path) -> None:
    graph = _build(
        tmp_path,
        [_declaration("SOLO", "solo/solo.json")],
        {"solo/solo.json": '{"a": 1}'},
    )
    gaps = _gaps_by_kind(graph)
    assert "contract_missing_consumer" in gaps
    assert "contract_missing_provenance" in gaps
    (gap,) = gaps["contract_missing_consumer"]
    assert "SOLO" in gap.detail
    assert "solo/solo.json" in gap.detail


def test_fully_supplied_declaration_reports_no_contract_gaps(tmp_path: Path) -> None:
    graph = _build(
        tmp_path,
        [
            _declaration(
                "WIRE",
                "docs/wire.schema.json",
                kind="json_schema",
                authority="spec:SPEC-1",
                consumers=["code:backend/app.py"],
            ),
            _declaration(
                "FIX",
                "fixtures/seed.json",
                validates_against="contract:WIRE",
                consumers=["code:backend/app.py"],
            ),
        ],
        {
            "docs/wire.schema.json": '{"type": "object"}',
            "fixtures/seed.json": '{"a": 1}',
            "backend/app.py": "x = 1",
        },
    )
    assert _contract_gap_kinds(graph) == set()
    assert not any(gap.kind.startswith("contract_") for gap in graph.gaps)


def test_consumer_file_present_is_not_missing(tmp_path: Path) -> None:
    graph = _build(
        tmp_path,
        [
            _declaration(
                "WIRE",
                "docs/wire.schema.json",
                kind="json_schema",
                authority="spec:SPEC-1",
                consumers=["code:backend/app.py"],
            )
        ],
        {
            "docs/wire.schema.json": '{"type": "object"}',
            "backend/app.py": "x = 1",
        },
    )
    assert "contract_missing_consumer" not in _gaps_by_kind(graph)


def test_no_catalog_reports_no_contract_gaps(tmp_path: Path) -> None:
    root = _project(tmp_path)
    graph = build_graph(root)
    assert _contract_gap_kinds(graph) == set()
    assert graph.gaps == []