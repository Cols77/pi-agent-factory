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
_ARCHITECTURE_KINDS = {"adr", "spec", "diag"}
_DEFINITION_LABELS = (
    "NEEDS",
    "SYSTEM_REQUIREMENTS",
    "SUBSYSTEM_REQUIREMENTS",
    "ARCHITECTURE_DESIGN",
    "DETAILED_DESIGN",
    "CODE",
)
_VERIFICATION_LABELS = (
    "UNIT_VERIFICATION",
    "INTEGRATION_VERIFICATION",
    "SIMULATION_VERIFICATION",
    "SYSTEM_VALIDATION",
)


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


def _empty_bands(labels: tuple[str, ...]) -> dict[str, set[str]]:
    return {label: set() for label in labels}


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
    """Walk a feature's contained requirements or an SR's whole hierarchy."""
    if anchor.kind == "feat":
        pending = [
            edge.dst
            for edge in _edges(graph, "contains")
            if edge.src == anchor.id
            and edge.dst in nodes
            and nodes[edge.dst].kind in _REQUIREMENT_KINDS
        ]
    else:
        pending = [anchor.id]

    neighbours: dict[str, set[str]] = {}
    for edge in _edges(graph, "parent_of"):
        source = nodes.get(edge.src)
        target = nodes.get(edge.dst)
        if source is None or target is None:
            continue
        if source.kind not in _REQUIREMENT_KINDS or target.kind not in _REQUIREMENT_KINDS:
            continue
        neighbours.setdefault(source.id, set()).add(target.id)
        neighbours.setdefault(target.id, set()).add(source.id)

    requirements: set[str] = set()
    visited: set[str] = set()
    while pending:
        current = pending.pop()
        if current in visited:
            continue
        visited.add(current)
        node = nodes.get(current)
        if node is None or node.kind not in _REQUIREMENT_KINDS:
            continue
        requirements.add(current)
        pending.extend(sorted(neighbours.get(current, set()), reverse=True))
    return requirements


def _requirement_bands(
    graph: Graph, requirement_ids: set[str], nodes: dict[str, Node]
) -> dict[str, set[str]]:
    """Classify roots as system requirements and their SR children as subsystem."""
    bands = _empty_bands(_DEFINITION_LABELS)
    bands["NEEDS"] = {
        node_id for node_id in requirement_ids if nodes[node_id].kind == "br"
    }
    child_srs = {
        edge.dst
        for edge in _edges(graph, "parent_of")
        if edge.src in requirement_ids
        and edge.dst in requirement_ids
        and nodes[edge.src].kind == "sr"
        and nodes[edge.dst].kind == "sr"
    }
    system_srs = {
        node_id
        for node_id in requirement_ids
        if nodes[node_id].kind == "sr" and node_id not in child_srs
    }
    bands["SYSTEM_REQUIREMENTS"] = system_srs
    bands["SUBSYSTEM_REQUIREMENTS"] = {
        node_id for node_id in requirement_ids if nodes[node_id].kind == "sr"
    } - system_srs
    return bands


def _task_ids(graph: Graph, requirement_ids: set[str], nodes: dict[str, Node]) -> set[str]:
    return {
        edge.src
        for edge in _edges(graph, "satisfies")
        if edge.dst in requirement_ids and edge.src in nodes and nodes[edge.src].kind == "task"
    }


def _design_ids(graph: Graph, scope_ids: set[str], task_ids: set[str], nodes: dict[str, Node]) -> set[str]:
    """Collect only design facts adjacent to this slice's recorded links."""
    design_ids: set[str] = set()
    for edge in _edges(graph, "source_plan"):
        if edge.src in task_ids and edge.dst in nodes and nodes[edge.dst].kind == "plan":
            design_ids.add(edge.dst)
    for edge in _edges(graph, "spec_ref"):
        if edge.src in design_ids and edge.dst in nodes and nodes[edge.dst].kind == "spec":
            design_ids.add(edge.dst)
    for edge in _edges(graph, "illustrates"):
        if edge.src in scope_ids and edge.dst in nodes and nodes[edge.dst].kind in _ARCHITECTURE_KINDS:
            design_ids.add(edge.dst)
        if edge.dst in scope_ids and edge.src in nodes and nodes[edge.src].kind in _ARCHITECTURE_KINDS:
            design_ids.add(edge.src)
    return design_ids


def _verification_band(
    source_id: str,
    architecture_ids: set[str],
    subsystem_ids: set[str],
    unit_source_ids: set[str],
) -> str:
    """Place evidence by the recorded scope role it verifies, never by a guessed type."""
    if source_id in unit_source_ids:
        return "UNIT_VERIFICATION"
    if source_id in architecture_ids:
        return "INTEGRATION_VERIFICATION"
    if source_id in subsystem_ids:
        return "SIMULATION_VERIFICATION"
    return "SYSTEM_VALIDATION"


def _verification_bands(
    graph: Graph,
    requirement_ids: set[str],
    scope_ids: set[str],
    detailed_design_ids: set[str],
    architecture_ids: set[str],
    subsystem_ids: set[str],
    nodes: dict[str, Node],
) -> tuple[dict[str, set[str]], set[str], set[str]]:
    bands = _empty_bands(_VERIFICATION_LABELS)
    for edge in _edges(graph, "verified_by"):
        if edge.src in (scope_ids | detailed_design_ids | architecture_ids) and edge.dst in nodes:
            bands[
                _verification_band(
                    edge.src, architecture_ids, subsystem_ids, detailed_design_ids
                )
            ].add(edge.dst)

    goals: set[str] = set()
    for edge in _edges(graph, "demonstrates"):
        source = nodes.get(edge.src)
        if source is not None and source.kind == "goal" and edge.dst in requirement_ids:
            goals.add(edge.src)
            bands["SIMULATION_VERIFICATION"].add(edge.src)

    metrics: set[str] = set()
    for edge in _edges(graph, "evaluates"):
        source = nodes.get(edge.src)
        target = nodes.get(edge.dst)
        if source is not None and source.kind == "goal" and edge.src in goals:
            if target is not None and target.kind == "metric":
                metrics.add(edge.dst)
                bands["SIMULATION_VERIFICATION"].add(edge.dst)
    return bands, goals, metrics


def _slice(graph: Graph, anchor_ref: str) -> VCycleSlice:
    nodes = _node_map(graph)
    anchor = _resolve_anchor(nodes, anchor_ref)
    requirement_ids = _requirement_ids(graph, anchor, nodes)
    scope_ids = requirement_ids | {anchor.id}
    task_ids = _task_ids(graph, requirement_ids, nodes)
    definition = _requirement_bands(graph, requirement_ids, nodes)
    design_ids = _design_ids(graph, scope_ids, task_ids, nodes)
    definition["ARCHITECTURE_DESIGN"] = {
        node_id for node_id in design_ids if nodes[node_id].kind in _ARCHITECTURE_KINDS
    }
    definition["DETAILED_DESIGN"] = {
        node_id for node_id in design_ids if nodes[node_id].kind == "plan"
    } | task_ids

    verification, goal_ids, metric_ids = _verification_bands(
        graph,
        requirement_ids,
        scope_ids,
        definition["DETAILED_DESIGN"],
        definition["ARCHITECTURE_DESIGN"],
        definition["SUBSYSTEM_REQUIREMENTS"],
        nodes,
    )
    goals = _nodes_for(goal_ids, nodes)
    metrics = _nodes_for(metric_ids, nodes)
    runs: list[Node] = []
    return VCycleSlice(
        anchor=anchor_ref,
        definition=[
            VCycleSide(label, _nodes_for(definition[label], nodes)) for label in _DEFINITION_LABELS
        ],
        verification=[
            VCycleSide(label, _nodes_for(verification[label], nodes))
            for label in _VERIFICATION_LABELS
        ],
        goals=goals,
        metrics=metrics,
        runs=runs,
    )


def vcycle_slice(root: Path, anchor_ref: str) -> VCycleSlice:
    """Build a deterministic V-cycle slice rooted at an exact feature or SR ref."""
    return _slice(build_graph(root), anchor_ref)
