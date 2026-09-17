from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from coherence.contracts.catalog import load_contract_catalog
from coherence.contracts.compiler import compile_contracts
from coherence.trace.contracts import contract_edges, contract_gaps, contract_nodes
from coherence.trace.gaps import Gap, _KIND_ORDER, find_gaps
from coherence.trace.health import Health, compute_health
from coherence.trace.model import Edge, Node, extract_edges, load_nodes
from coherence.trace.validation_status import SrStatus, load_validation
from substrate.documents.adr import load_adrs


@dataclass(frozen=True)
class Graph:
    nodes: list[Node]
    edges: list[Edge]
    gaps: list[Gap]
    validation: dict[str, SrStatus]
    health: Health


def _adr_nodes(root: Path) -> list[Node]:
    return [
        Node(id=adr_id, kind="adr", title=doc.title or doc.path.name, path=doc.path)
        for adr_id, doc in sorted(load_adrs(root).items())
    ]


def build_graph(root: Path) -> Graph:
    nodes = load_nodes(root) + _adr_nodes(root)
    edges = extract_edges(root, nodes)
    validation = load_validation(root)
    gaps = find_gaps(nodes, edges, validation)

    # Optional-contract-artifacts (task 5): compose the contract compiler's
    # closure into the trace graph. Only a project that opts in with a
    # .factory/contracts.yaml (closure.present) gains contract nodes, edges and
    # findings; a project without a catalog is byte-identical to before.
    closure = compile_contracts(load_contract_catalog(root), root)
    if closure.present:
        contract_ns = contract_nodes(closure, root)
        nodes = nodes + contract_ns
        edges = edges + contract_edges(closure)
        gaps = gaps + contract_gaps(closure, root)
        # Keep the whole gap list deterministically ordered by (kind, node_id);
        # the no-catalog path re-sorts an already-sorted list, a no-op.
        gaps.sort(key=lambda gap: (_KIND_ORDER[gap.kind], gap.node_id))

    return Graph(nodes, edges, gaps, validation, compute_health(nodes, gaps))


def graph_to_dict(graph: Graph) -> dict:
    return {
        "nodes": [{**asdict(n), "path": str(n.path)} for n in graph.nodes],
        "edges": [asdict(e) for e in graph.edges],
        "gaps": [asdict(g) for g in graph.gaps],
        "validation": {k: asdict(v) for k, v in graph.validation.items()},
        "health": {
            "percent": graph.health.percent,
            "satisfied": graph.health.satisfied,
            "expected": graph.health.expected,
            "dangling": graph.health.dangling,
            "deferred": graph.health.deferred,
            "proposed": graph.health.proposed,
            "classes": [asdict(c) for c in graph.health.classes],
        },
    }
