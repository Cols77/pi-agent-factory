"""Contract trace nodes and typed edges (optional-contract-artifacts task 5).

Evidence for SR-076 / AC-1:
  * ``contract:<id>`` nodes are absent when no contract catalog is declared;
  * they are present, with their typed ``defines``/``consumed_by``/
    ``validated_by``/``validates_against``/``references`` edges, when a valid
    catalog is declared; and
  * both the node set and the edge set are emitted in a deterministic order
    (declarations order for nodes, ``(src, dst, kind)`` for edges) rather than
    in filesystem discovery order -- asserted by building the graph twice and
    comparing, and by comparing against the sorted form directly.

The contract contributions come from the compiler closure via
``coherence.trace.contracts``, never from JSON globbing; the no-catalog path
must stay byte-identical to the pre-contract graph (zero contract nodes, zero
contract edges).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from coherence.trace.graph import build_graph

pytestmark = pytest.mark.unit

CATALOG_SCHEMA = "coherence.contract-catalog.v1"


def _write(root: Path, rel: str, content: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _catalog(root: Path, document: dict) -> None:
    _write(root, ".factory/contracts.yaml", json.dumps(document))


def _empty_project(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)


def _full_project(root: Path) -> None:
    """A catalog + real artifact files exercising all five contract edge kinds.

    FIX is a fixture validated against WIRE; WIRE is a json_schema with an
    authority (spec) and code/test consumers; WIRE's ``$ref`` points at an
    un-declared file, producing a ``references`` edge to a ``code:`` target.
    """
    document = {
        "schema": CATALOG_SCHEMA,
        "contracts": [
            {
                "id": "WIRE",
                "path": "docs/wire.schema.json",
                "kind": "json_schema",
                "status": "active",
                "authority": "spec:SPEC-1",
                "consumers": ["code:backend/app.py", "test:tests/seed.py"],
            },
            {
                "id": "FIX",
                "path": "fixtures/seed.json",
                "kind": "fixture",
                "status": "active",
                "validates_against": "contract:WIRE",
                "consumers": ["code:backend/app.py"],
            },
        ],
    }
    _catalog(root, document)
    _write(root, "docs/wire.schema.json", '{"$ref": "../docs/note.json"}')
    _write(root, "docs/note.json", '{"shared": true}')
    _write(root, "fixtures/seed.json", '{"a": 1}')
    _write(root, "backend/app.py", "x = 1")
    _write(root, "tests/seed.py", "def test_one(): pass")


def _contract_ids(graph: object) -> list[str]:
    return [n.id for n in graph.nodes if n.kind == "contract"]


def _edges(graph: object) -> list[tuple[str, str, str]]:
    return [(e.src, e.dst, e.kind) for e in graph.edges]


@pytest.mark.sr("SR-076")
def test_sr076_ac1_no_catalog_adds_no_contract_nodes_or_edges(tmp_path: Path) -> None:
    root = tmp_path / "project"
    _empty_project(root)
    graph = build_graph(root)
    assert _contract_ids(graph) == []
    assert _edges(graph) == []
    assert graph.gaps == []


@pytest.mark.sr("SR-076")
def test_sr076_ac1_contract_nodes_present_with_valid_catalog(tmp_path: Path) -> None:
    root = tmp_path / "project"
    _full_project(root)
    graph = build_graph(root)

    nodes = [n for n in graph.nodes if n.kind == "contract"]
    ids = [n.id for n in nodes]
    # Deterministic: the nodes follow the declared contracts in id order,
    # and each carries a repo-relative path under the project root.
    assert ids == ["contract:FIX", "contract:WIRE"]
    for node in nodes:
        assert str(node.path).startswith(str(root))
        assert node.path.exists()


@pytest.mark.sr("SR-076")
def test_sr076_ac1_contract_edges_present_and_typed(tmp_path: Path) -> None:
    root = tmp_path / "project"
    _full_project(root)
    graph = build_graph(root)

    edges = _edges(graph)
    # Every contract edge connects a contract:<id> endpoint (src or dst).
    assert all(
        e[0].startswith("contract:") or e[1].startswith("contract:") for e in edges
    )
    # All five typed edges connect the contract:<id> nodes to their surfaces.
    assert ("contract:FIX", "contract:WIRE", "validates_against") in edges
    assert ("contract:WIRE", "contract:FIX", "validated_by") in edges
    assert ("contract:FIX", "code:backend/app.py", "consumed_by") in edges
    assert ("contract:WIRE", "test:tests/seed.py", "consumed_by") in edges
    assert ("contract:WIRE", "code:docs/note.json", "references") in edges
    assert ("spec:SPEC-1", "contract:WIRE", "defines") in edges
    kinds = {e[2] for e in edges}
    assert kinds == {
        "defines", "consumed_by", "validated_by", "validates_against", "references",
    }


@pytest.mark.sr("SR-076")
def test_sr076_ac1_deterministic_node_and_edge_order(tmp_path: Path) -> None:
    root = tmp_path / "project"
    _full_project(root)
    first = build_graph(root)
    second = build_graph(root)

    assert _contract_ids(first) == _contract_ids(second)
    # Edge set is sorted by (src, dst, kind), not discovery order.
    assert _edges(first) == _edges(second)
    assert _edges(first) == sorted(_edges(first))