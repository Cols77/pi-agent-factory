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


def _id_node(path: Path, kind: NodeKind) -> Node:
    post = _load_post(path)
    if post is None or "id" not in post.metadata:
        return Node(id=path.name, kind=kind, title=path.name, path=path)
    exempt, deferred = _disposition(post.metadata)
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
    )


def _file_node(path: Path, kind: NodeKind) -> Node:
    post = _load_post(path)
    body = post.content if post is not None else path.read_text(encoding="utf-8")
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


EdgeKind = Literal["source_plan", "satisfies", "upstream", "spec_ref"]

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
            for sr_id in as_str_list(meta.get("satisfies")):
                add(Edge(node.id, sr_id, "satisfies"))
            for upstream_id in as_str_list(meta.get("upstream")):
                add(Edge(node.id, upstream_id, "upstream"))
        elif node.kind == "plan":
            post = _load_post(node.path)
            body = post.content if post is not None else node.path.read_text(encoding="utf-8")
            for filename in _SPEC_REF_RE.findall(body):
                add(Edge(node.id, f"spec:{filename}", "spec_ref"))

    return edges
