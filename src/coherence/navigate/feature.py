"""Deterministic, trace-backed feature dossiers."""
from __future__ import annotations

import subprocess
from pathlib import Path

from coherence.navigate.models import SystemScopeRef
from coherence.navigate.story import query_story
from coherence.navigate.vcycle import VCycleSlice, vcycle_slice
from coherence.trace import model as trace_model
from coherence.trace import validation_status
from coherence.trace.graph import Graph, build_graph
from coherence.trace.model import Node

_REQUIREMENT_KINDS = {"br", "sr"}
_DESIGN_KINDS = {"adr", "plan", "spec"}


def _scope_errors():
    """Import query-owned scope errors without a module import cycle."""
    from coherence.navigate.queries import ScopeKindError, ScopeNotFoundError

    return ScopeKindError, ScopeNotFoundError


def _feature_or_raise(graph: Graph, feature_id: str) -> Node:
    scope_kind_error, scope_not_found_error = _scope_errors()
    if not feature_id.startswith("FEAT-") or ":" in feature_id:
        raise scope_kind_error(f"feature_context requires an exact FEAT-* id, got: {feature_id!r}")
    feature = next(
        (node for node in graph.nodes if node.kind == "feat" and node.id == feature_id),
        None,
    )
    if feature is None:
        raise scope_not_found_error(f"feature not found: {feature_id!r}")
    return feature


def _node_fact(node: Node) -> dict:
    return {"id": node.id, "kind": node.kind, "title": node.title, "path": str(node.path)}


def _contained_requirements(graph: Graph, feature: Node) -> list[Node]:
    nodes = {node.id: node for node in graph.nodes}
    ids = {
        edge.dst
        for edge in graph.edges
        if edge.kind == "contains"
        and edge.src == feature.id
        and edge.dst in nodes
        and nodes[edge.dst].kind in _REQUIREMENT_KINDS
    }
    return sorted((nodes[node_id] for node_id in ids), key=lambda node: node.id)


def _slice_nodes(slice_: VCycleSlice, labels: set[str]) -> list[Node]:
    nodes = {
        (node.id, node.kind, str(node.path)): node
        for side in slice_.definition + slice_.verification
        if side.label in labels
        for node in side.nodes
    }
    return sorted(nodes.values(), key=lambda node: (node.kind, node.id, str(node.path)))


def _design_records(slice_: VCycleSlice) -> list[dict]:
    return [
        _node_fact(node)
        for node in _slice_nodes(slice_, {"ARCHITECTURE_DESIGN", "DETAILED_DESIGN"})
        if node.kind in _DESIGN_KINDS
    ]


def _implementation(root: Path, slice_: VCycleSlice) -> list[dict]:
    entries: list[dict] = []
    for task in _slice_nodes(slice_, {"DETAILED_DESIGN"}):
        if task.kind != "task":
            continue
        story = query_story(root, SystemScopeRef(kind="task", ref=f"task:{task.id}"))
        entries.append({"task": story["task"], "runs": story["runs"]})
    return entries


def _implementation_files(implementation: list[dict]) -> list[str]:
    files: set[str] = set()
    for entry in implementation:
        for run in entry["runs"]:
            changed_files = run["implementation"]["changed_files"]
            if changed_files is not None:
                files.update(changed_files)
    return sorted(files)


def _verification(requirements: list[Node], root: Path) -> list[dict]:
    statuses = validation_status.load_validation(root)
    verification: list[dict] = []
    for requirement in requirements:
        status = statuses.get(requirement.id)
        verification.append(
            {
                "id": requirement.id,
                "state": status.state if status is not None else "never_validated",
                "stale": status.stale if status is not None else False,
            }
        )
    return verification


def _safe_evidenced_path(root: Path, path: str) -> str | None:
    """Normalize an evidence path only when it remains confined to ``root``."""
    try:
        resolved_root = root.resolve()
        resolved_path = (resolved_root / path).resolve()
        if resolved_path == resolved_root or resolved_root not in resolved_path.parents:
            return None
        return resolved_path.relative_to(resolved_root).as_posix()
    except (OSError, RuntimeError):
        return None


def _recent_changes(root: Path, implementation_files: list[str], limit: int = 5) -> list[dict]:
    """Recent recorded commits for evidenced paths, or no records when git cannot answer."""
    paths = sorted(
        {
            safe_path
            for path in implementation_files
            if (safe_path := _safe_evidenced_path(root, path)) is not None
        }
    )
    if not paths or limit <= 0:
        return []
    pathspecs = [f":(literal){path}" for path in paths]
    try:
        completed = subprocess.run(
            ["git", "log", "-n", str(limit), "--format=%H%x00%aI%x00%s", "--", *pathspecs],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return []

    changes: list[dict] = []
    seen_commits: set[str] = set()
    for line in completed.stdout.splitlines():
        commit, separator, remainder = line.partition("\x00")
        authored_at, separator, subject = remainder.partition("\x00")
        if not commit or not separator or commit in seen_commits:
            continue
        seen_commits.add(commit)
        changes.append({"commit": commit, "authored_at": authored_at, "subject": subject})
    return changes[:limit]


def feature_context(root: Path, feature_id: str) -> dict:
    """Return a deterministic dossier for one exact feature id.

    All returned facts originate in the trace graph or the loaders it already
    composes. Simulation runs are intentionally absent until their loader is
    introduced by the later increment.
    """
    graph = build_graph(root)
    feature = _feature_or_raise(graph, feature_id)
    post = trace_model._load_post(feature.path)
    intent = post.content.strip() if post is not None else ""
    requirements = _contained_requirements(graph, feature)
    slice_ = vcycle_slice(root, f"feat:{feature.id}")
    implementation = _implementation(root, slice_)
    implementation_files = _implementation_files(implementation)

    return {
        "id": feature.id,
        "title": feature.title,
        "intent": intent,
        "requirements": [_node_fact(requirement) for requirement in requirements],
        "design_records": _design_records(slice_),
        "implementation": implementation,
        "implementation_files": implementation_files,
        "verification": _verification(requirements, root),
        "goal_ids": [goal.id for goal in slice_.goals],
        "metric_ids": [metric.id for metric in slice_.metrics],
        "latest_simulation_evidence": None,
        "recent_changes": _recent_changes(root, implementation_files),
    }

