"""Typed, read-only V-cycle slices assembled from the trace graph."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from factory.trace.graph import Graph, build_graph
from factory.trace.model import Edge, Node


@dataclass(frozen=True)
class VCycleSide:
    label: str
    nodes: list[Node]


@dataclass(frozen=True)
class VCycleSlice:
    anchor: str
    definition: list[VCycleSide]
    verification: list[VCycleSide]
    goals: list[Node]
    metrics: list[Node]
    runs: list[Node]


_REQUIREMENT_KINDS = {"sr", "br"}
_DESIGN_KINDS = {"adr", "spec", "plan", "diag"}


def _node_map(graph: Graph) -> dict[str, Node]:
    """Return a deterministic node lookup for an already-built graph."""
    nodes: dict[str, Node] = {}
    for node in sorted(graph.nodes, key=lambda item: (item.id, item.kind, str(item.path))):
        nodes.setdefault(node.id, node)
    return nodes


def _edges(graph: Graph, kind: str) -> list[Edge]:
    return sorted(
        (edge for edge in graph.edges if edge.kind == kind),
        key=lambda edge: (edge.src, edge.dst),
    )


def _nodes_for(ids: set[str], nodes: dict[str, Node]) -> list[Node]:
    return sorted(
        (nodes[node_id] for node_id in ids if node_id in nodes),
        key=lambda node: node.id,
    )


def _resolve_anchor(nodes: dict[str, Node], anchor_ref: str) -> Node:
    """Resolve only an exact ``feat:`` or ``sr:`` scope reference."""
    kind, separator, node_id = anchor_ref.partition(":")
    if not separator or kind not in {"feat", "sr"} or not node_id:
        raise ValueError(f"invalid vcycle anchor: {anchor_ref!r}")
    node = nodes.get(node_id)
    if node is None or node.kind != kind:
        raise ValueError(f"vcycle anchor does not resolve: {anchor_ref!r}")
    return node


def _requirement_ids(graph: Graph, anchor: Node, nodes: dict[str, Node]) -> set[str]:
    """Follow only recorded containment and child requirement relationships."""
    structural_edges = [
        edge for edge in graph.edges if edge.kind in {"contains", "parent_of"}
    ]
    outgoing: dict[str, list[Edge]] = {}
    for edge in structural_edges:
        outgoing.setdefault(edge.src, []).append(edge)
    for linked in outgoing.values():
        linked.sort(key=lambda edge: edge.dst)

    requirements: set[str] = {anchor.id} if anchor.kind in _REQUIREMENT_KINDS else set()
    visited = {anchor.id}
    pending = [anchor.id]
    while pending:
        source = pending.pop()
        for edge in outgoing.get(source, []):
            target = nodes.get(edge.dst)
            if target is None or target.kind not in _REQUIREMENT_KINDS:
                continue
            requirements.add(target.id)
            if target.id not in visited:
                visited.add(target.id)
                pending.append(target.id)
    return requirements


def _task_ids(graph: Graph, requirement_ids: set[str], nodes: dict[str, Node]) -> set[str]:
    return {
        edge.src
        for edge in _edges(graph, "satisfies")
        if edge.dst in requirement_ids and nodes.get(edge.src, None) is not None
        and nodes[edge.src].kind == "task"
    }


def _design_ids(graph: Graph, scope_ids: set[str], task_ids: set[str], nodes: dict[str, Node]) -> set[str]:
    """Collect only design facts adjacent to this slice's recorded links."""
    design_ids: set[str] = set()
    for edge in _edges(graph, "source_plan"):
        if edge.src in task_ids and nodes.get(edge.dst, None) is not None:
            if nodes[edge.dst].kind == "plan":
                design_ids.add(edge.dst)
    for edge in _edges(graph, "spec_ref"):
        if edge.src in design_ids and nodes.get(edge.dst, None) is not None:
            if nodes[edge.dst].kind == "spec":
                design_ids.add(edge.dst)
    for edge in _edges(graph, "illustrates"):
        if edge.src in scope_ids and nodes.get(edge.dst, None) is not None:
            if nodes[edge.dst].kind in _DESIGN_KINDS:
                design_ids.add(edge.dst)
        if edge.dst in scope_ids and nodes.get(edge.src, None) is not None:
            if nodes[edge.src].kind in _DESIGN_KINDS:
                design_ids.add(edge.src)
    return design_ids


def _verification_ids(graph: Graph, scope_ids: set[str], task_ids: set[str], nodes: dict[str, Node]) -> set[str]:
    sources = scope_ids | task_ids
    return {
        edge.dst
        for edge in _edges(graph, "verified_by")
        if edge.src in sources and edge.dst in nodes
    }


def _related_ids(graph: Graph, kind: str, source_ids: set[str], target_kind: str, nodes: dict[str, Node]) -> set[str]:
    """Find nodes of one kind joined to the constrained local source set."""
    related: set[str] = set()
    for edge in _edges(graph, kind):
        source = nodes.get(edge.src)
        target = nodes.get(edge.dst)
        if edge.src in source_ids and target is not None and target.kind == target_kind:
            related.add(target.id)
        if edge.dst in source_ids and source is not None and source.kind == target_kind:
            related.add(source.id)
    return related


def _slice(graph: Graph, anchor_ref: str) -> VCycleSlice:
    nodes = _node_map(graph)
    anchor = _resolve_anchor(nodes, anchor_ref)
    requirement_ids = _requirement_ids(graph, anchor, nodes)
    scope_ids = requirement_ids | {anchor.id}
    task_ids = _task_ids(graph, requirement_ids, nodes)
    design_ids = _design_ids(graph, scope_ids, task_ids, nodes)
    verification_ids = _verification_ids(graph, scope_ids, task_ids, nodes)
    goal_ids = _related_ids(graph, "demonstrates", scope_ids, "goal", nodes)
    metric_ids = _related_ids(graph, "evaluates", scope_ids | goal_ids, "metric", nodes)

    requirements = _nodes_for(requirement_ids, nodes)
    design = _nodes_for(design_ids, nodes)
    implementation = _nodes_for(task_ids, nodes)
    verification = _nodes_for(verification_ids, nodes)
    goals = _nodes_for(goal_ids, nodes)
    metrics = _nodes_for(metric_ids, nodes)
    runs: list[Node] = []
    return VCycleSlice(
        anchor=anchor_ref,
        definition=[
            VCycleSide("requirements", requirements),
            VCycleSide("design", design),
            VCycleSide("implementation", implementation),
        ],
        verification=[
            VCycleSide("verification", verification),
            VCycleSide("goals", goals),
            VCycleSide("metrics", metrics),
            VCycleSide("runs", runs),
        ],
        goals=goals,
        metrics=metrics,
        runs=runs,
    )


def vcycle_slice(root: Path, anchor_ref: str) -> VCycleSlice:
    """Build a deterministic V-cycle slice rooted at an exact feature or SR ref."""
    return _slice(build_graph(root), anchor_ref)
