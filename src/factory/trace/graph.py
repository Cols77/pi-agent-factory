from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from factory.trace.gaps import Gap, find_gaps
from factory.trace.health import Health, compute_health
from factory.trace.model import Edge, Node, extract_edges, load_nodes
from factory.trace.validation_status import SrStatus, load_validation


@dataclass(frozen=True)
class Graph:
    nodes: list[Node]
    edges: list[Edge]
    gaps: list[Gap]
    validation: dict[str, SrStatus]
    health: Health


def build_graph(root: Path) -> Graph:
    nodes = load_nodes(root)
    edges = extract_edges(root, nodes)
    validation = load_validation(root)
    gaps = find_gaps(nodes, edges, validation)
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
            "classes": [asdict(c) for c in graph.health.classes],
        },
    }
