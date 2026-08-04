from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import frontmatter

NodeKind = Literal["br", "sr", "spec", "plan", "task"]

_HEADING_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)


@dataclass(frozen=True)
class Node:
    id: str
    kind: NodeKind
    title: str
    path: Path
    exempt: bool = False
    deferred: str | None = None


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
    for path in _glob(root, "tasks", pattern="T-*.md"):
        nodes.append(_id_node(path, "task"))
    for path in _glob(root, "docs", "superpowers", "plans", pattern="*.md"):
        nodes.append(_file_node(path, "plan"))
    for path in _glob(root, "docs", "superpowers", "specs", pattern="*.md"):
        nodes.append(_file_node(path, "spec"))
    return nodes
