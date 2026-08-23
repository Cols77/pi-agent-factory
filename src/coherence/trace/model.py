from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import frontmatter

NodeKind = Literal[
    "br",
    "sr",
    "spec",
    "plan",
    "task",
    "adr",
    "feat",
    "metric",
    "goal",
    "run",
    "diag",
]

_HEADING_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)


@dataclass(frozen=True)
class Node:
    id: str
    kind: NodeKind
    title: str
    path: Path
    exempt: bool = False
    deferred: str | None = None
    proposed: bool = False
    diagram_file: str | None = None
    scope_error: str | None = None


def _load_post(path: Path) -> frontmatter.Post | None:
    # A malformed artifact must degrade to a filename-labelled node, never crash the
    # whole graph -- same contract doc-lister.ts:26 already honours on the TS side.
    try:
        return frontmatter.load(str(path))
    except Exception:
        return None


def _disposition(meta: dict) -> tuple[bool, str | None]:
    exempt = bool(meta.get("trace_exempt", False))
    deferred = meta.get("trace_deferred")
    return exempt, str(deferred) if deferred else None


def _first_heading(text: str, fallback: str) -> str:
    match = _HEADING_RE.search(text)
    return match.group(1).strip() if match else fallback


_JUSTIFICATION_KINDS = (
    "satisfies", "corrects", "mitigates", "implements", "maintains", "explores",
)
JUSTIFICATION_EDGE_KINDS: frozenset[str] = frozenset(_JUSTIFICATION_KINDS)


def _justification_scope_error(meta: dict) -> str | None:
    """Mirrors substrate.ledger.tasks._parse_justification's shape/kind checks,
    independently -- this module never imports substrate.ledger.tasks (stays a
    pure frontmatter reader; extract_edges/load_nodes must work without it).
    """
    raw = meta.get("justification")
    if raw is None:
        return None
    if not isinstance(raw, list):
        return "justification must be a list of single-key {kind: target_id} mappings"
    for entry in raw:
        if not isinstance(entry, dict) or len(entry) != 1:
            return f"each justification entry must be a single {{kind: target_id}} mapping, got {entry!r}"
        ((kind, _target_id),) = entry.items()
        if kind not in _JUSTIFICATION_KINDS:
            return f"unknown justification kind {kind!r} (have {_JUSTIFICATION_KINDS})"
    return None


def _id_node(path: Path, kind: NodeKind) -> Node:
    post = _load_post(path)
    if post is None or "id" not in post.metadata:
        return Node(id=path.name, kind=kind, title=path.name, path=path)
    exempt, deferred = _disposition(post.metadata)
    scope_error = _justification_scope_error(post.metadata) if kind == "task" else None
    return Node(
        id=str(post.metadata["id"]),
        kind=kind,
        title=str(post.metadata.get("title", path.name)),
        path=path,
        exempt=exempt,
        deferred=deferred,
        # The absence of a binding IS the proposed state -- read here rather than
        # from the register so build_graph never loads config or imports target code.
        proposed=kind == "sr" and "binding" not in post.metadata,
        diagram_file=str(post.metadata["diagram_file"])
        if kind == "diag" and "diagram_file" in post.metadata
        else None,
        scope_error=scope_error,
    )


def _file_node(path: Path, kind: NodeKind) -> Node:
    post = _load_post(path)
    if post is not None:
        body = post.content
    else:
        # `_load_post` already degraded a malformed/undecodable file to `None`
        # rather than raising (see its own contract comment above) -- this
        # fallback read must honour the same contract, not reopen the file
        # unguarded and crash the whole graph on one bad spec/plan.
        body = _read_text_or_empty(path)
    meta = post.metadata if post is not None else {}
    exempt, deferred = _disposition(meta)
    return Node(
        id=f"{kind}:{path.name}",
        kind=kind,
        title=_first_heading(body, path.name),
        path=path,
        exempt=exempt,
        deferred=deferred,
    )


def _glob(root: Path, *parts: str, pattern: str) -> list[Path]:
    directory = root.joinpath(*parts)
    if not directory.is_dir():
        return []
    return sorted(directory.glob(pattern))


def load_nodes(root: Path) -> list[Node]:
    nodes: list[Node] = []
    for path in _glob(root, "requirements", pattern="SR-*.md"):
        nodes.append(_id_node(path, "sr"))
    for path in _glob(root, "requirements", pattern="BR-*.md"):
        nodes.append(_id_node(path, "br"))
    for path in _glob(root, "docs", "features", pattern="FEAT-*.md"):
        nodes.append(_id_node(path, "feat"))
    for path in _glob(root, "docs", "diagrams", pattern="DIAG-*.md"):
        nodes.append(_id_node(path, "diag"))
    for path in _glob(root, "metrics", pattern="MET-*.md"):
        nodes.append(_id_node(path, "metric"))
    for path in _glob(root, "goals", pattern="GOAL-*.md"):
        nodes.append(_id_node(path, "goal"))
    for path in _glob(root, "tasks", pattern="T-*.md"):
        nodes.append(_id_node(path, "task"))
    for path in _glob(root, "docs", "superpowers", "plans", pattern="*.md"):
        nodes.append(_file_node(path, "plan"))
    for path in _glob(root, "docs", "superpowers", "specs", pattern="*.md"):
        nodes.append(_file_node(path, "spec"))
    return nodes


EdgeKind = Literal[
    "source_plan",
    "satisfies",
    "upstream",
    "spec_ref",
    "parent_of",
    "verified_by",
    "demonstrates",
    "evaluates",
    "contains",
    "illustrates",
    # Typed lifecycle relationships (spec §4): intent, design, assurance, change.
    "derives",
    "decomposes",
    "refines",
    "allocates",
    "implements",
    "verifies",
    "validates",
    "mitigates",
    "evidences",
    "corrects",
    "impacts",
    "supersedes",
    # Task-justification-only kinds (substrate.ledger.tasks._JUSTIFICATION_KINDS)
    # that spec §4's lifecycle list does not itself name -- added so every
    # legal justification entry maps to a real edge kind (see Task 7 Decision 1).
    "maintains",
    "explores",
]

_SPEC_REF_RE = re.compile(r"docs/superpowers/specs/([A-Za-z0-9._-]+\.md)")


@dataclass(frozen=True)
class Edge:
    src: str
    dst: str
    kind: EdgeKind


def as_str_list(value: object) -> list[str]:
    """Coerce a frontmatter field that may be absent, scalar, or a list."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value]
    return []


def _read_text_or_empty(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def edges_from_frontmatter(src_id: str, meta: dict) -> list[Edge]:
    """Return declared V-cycle relationship edges without resolving their endpoints."""
    edges: list[Edge] = []
    for dst in as_str_list(meta.get("parent_of")):
        edges.append(Edge(src_id, dst, "parent_of"))
    for parent in as_str_list(meta.get("child_of")):
        edges.append(Edge(parent, src_id, "parent_of"))
    edge_fields: tuple[tuple[str, EdgeKind], ...] = (
        ("verified_by", "verified_by"),
        ("demonstrates", "demonstrates"),
        ("evaluates", "evaluates"),
        ("contains", "contains"),
        ("illustrates", "illustrates"),
    )
    for field, kind in edge_fields:
        for dst in as_str_list(meta.get(field)):
            edges.append(Edge(src_id, dst, kind))
    return edges


def _edges_from_justification(node_id: str, meta: dict) -> list[Edge]:
    """Task-node justification edges (spec §4 "typed task justification").
    Legacy `satisfies:` frontmatter with no `justification:` key is read as
    shorthand for `justification: [{satisfies: ...}]`, producing byte-
    identical `satisfies` edges to before this change. A malformed or
    unsupported-kind entry produces no edge here -- it is already recorded on
    the node as `scope_error` by `_id_node`/`_justification_scope_error`."""
    raw = meta.get("justification")
    if raw is None:
        return [Edge(node_id, sr_id, "satisfies") for sr_id in as_str_list(meta.get("satisfies"))]
    if not isinstance(raw, list):
        return []
    edges: list[Edge] = []
    for entry in raw:
        if not isinstance(entry, dict) or len(entry) != 1:
            continue
        ((kind, target_id),) = entry.items()
        if kind not in _JUSTIFICATION_KINDS:
            continue
        edges.append(Edge(node_id, str(target_id), kind))  # type: ignore[arg-type]
    return edges


def extract_edges(root: Path, nodes: list[Node]) -> list[Edge]:
    edges: list[Edge] = []
    seen: set[Edge] = set()

    def add(edge: Edge) -> None:
        if edge not in seen:
            seen.add(edge)
            edges.append(edge)

    for node in nodes:
        if node.kind in ("task", "sr", "br"):
            post = _load_post(node.path)
            if post is None:
                continue
            meta = post.metadata
            source_plan = meta.get("source_plan")
            if source_plan:
                add(Edge(node.id, f"plan:{Path(str(source_plan)).name}", "source_plan"))
            if node.kind == "task":
                for edge in _edges_from_justification(node.id, meta):
                    add(edge)
            else:
                for sr_id in as_str_list(meta.get("satisfies")):
                    add(Edge(node.id, sr_id, "satisfies"))
            for upstream_id in as_str_list(meta.get("upstream")):
                add(Edge(node.id, upstream_id, "upstream"))
            for edge in edges_from_frontmatter(node.id, meta):
                add(edge)
        elif node.kind in ("feat", "metric", "goal", "run", "diag"):
            post = _load_post(node.path)
            if post is None:
                continue
            if node.kind == "feat":
                for requirement_id in as_str_list(post.metadata.get("requirements")):
                    add(Edge(node.id, requirement_id, "contains"))
            elif node.kind == "goal":
                for requirement_id in as_str_list(post.metadata.get("requirements")):
                    add(Edge(node.id, requirement_id, "demonstrates"))
                metric_id = post.metadata.get("metric")
                if isinstance(metric_id, str):
                    add(Edge(node.id, metric_id, "evaluates"))
            for edge in edges_from_frontmatter(node.id, post.metadata):
                add(edge)
        elif node.kind == "plan":
            post = _load_post(node.path)
            body = post.content if post is not None else _read_text_or_empty(node.path)
            for filename in _SPEC_REF_RE.findall(body):
                add(Edge(node.id, f"spec:{filename}", "spec_ref"))

    return edges
