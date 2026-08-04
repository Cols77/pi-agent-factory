from __future__ import annotations

from pathlib import Path

import frontmatter

from factory.trace.model import Node, load_nodes


def _node(root: Path, node_id: str) -> Node:
    for node in load_nodes(root):
        if node.id == node_id:
            return node
    raise LookupError(f"unknown node: {node_id}")


def _node_path(root: Path, node_id: str) -> Path:
    return _node(root, node_id).path


def _update_meta(path: Path, **fields: object) -> Path:
    post = frontmatter.load(str(path))
    for key, value in fields.items():
        post[key] = value
    path.write_text(frontmatter.dumps(post), encoding="utf-8")
    return path


def link_satisfies(root: Path, task_id: str, sr_id: str) -> Path:
    if not (root / "requirements" / f"{sr_id}.md").is_file():
        raise ValueError(f"no such requirement: {sr_id}")
    path = _node_path(root, task_id)
    post = frontmatter.load(str(path))
    existing = post.metadata.get("satisfies") or []
    if isinstance(existing, str):
        existing = [existing]
    current = [str(s) for s in existing]
    if sr_id not in current:
        current.append(sr_id)
    return _update_meta(path, satisfies=current)


def link_spec(root: Path, plan_id: str, spec_filename: str) -> Path:
    if not (root / "docs" / "superpowers" / "specs" / spec_filename).is_file():
        raise ValueError(f"no such spec: {spec_filename}")
    path = _node_path(root, plan_id)
    reference = f"docs/superpowers/specs/{spec_filename}"
    text = path.read_text(encoding="utf-8")
    if reference not in text:
        suffix = "" if text.endswith("\n") else "\n"
        text = f"{text}{suffix}\nSpec: {reference}\n"
        path.write_text(text, encoding="utf-8")
    return path


def link_source_plan(root: Path, task_id: str, plan_filename: str) -> Path:
    plan_path = root / "docs" / "superpowers" / "plans" / plan_filename
    if not plan_path.is_file():
        raise ValueError(f"no such plan: {plan_filename}")
    return _update_meta(
        _node_path(root, task_id),
        source_plan=f"docs/superpowers/plans/{plan_filename}",
    )


def set_exempt(root: Path, node_id: str, reason: str) -> Path:
    node = _node(root, node_id)
    if node.kind in ("sr", "br"):
        raise ValueError(f"{node_id} cannot be exempted; defer it instead")
    return _update_meta(node.path, trace_exempt=True, trace_exempt_reason=reason)


def set_deferred(root: Path, node_id: str, reason: str) -> Path:
    return _update_meta(_node_path(root, node_id), trace_deferred=reason)
