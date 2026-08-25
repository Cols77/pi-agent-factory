from __future__ import annotations

from pathlib import Path

import frontmatter

from coherence.trace.model import Node, as_str_list, load_nodes


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


def _frontmatter_parts(raw: bytes) -> tuple[bytes, bytes, bytes]:
    """Return opening line, closing line, and raw body boundaries."""
    bom = b"\xef\xbb\xbf" if raw.startswith(b"\xef\xbb\xbf") else b""
    first_line_start = len(bom)
    first_line_end = raw.find(b"\n", first_line_start)
    if first_line_end < 0 or raw[first_line_start:first_line_end].rstrip(b"\r") != b"---":
        raise ValueError("document has no frontmatter")

    opening_end = first_line_end + 1
    line_start = opening_end
    while line_start <= len(raw):
        line_end = raw.find(b"\n", line_start)
        if line_end < 0:
            line_end = len(raw)
        line = raw[line_start:line_end].rstrip(b"\r")
        if line in (b"---", b"..."):
            body_start = line_end + 1 if line_end < len(raw) else line_end
            return raw[:opening_end], raw[line_start:body_start], raw[body_start:]
        if line_end == len(raw):
            break
        line_start = line_end + 1
    raise ValueError("document has no closing frontmatter delimiter")


def _write_unlink_post(path: Path, post: frontmatter.Post) -> None:
    """Write updated metadata while retaining the original body bytes."""
    raw = path.read_bytes()
    opening, closing, body = _frontmatter_parts(raw)
    serialized = frontmatter.dumps(
        frontmatter.Post("", handler=post.handler, **post.metadata)
    ).encode("utf-8")
    generated_opening_end = serialized.find(b"\n") + 1
    generated_closing_start = serialized.rfind(b"\n---")
    inner = serialized[generated_opening_end : generated_closing_start + 1]
    newline = b"\r\n" if opening.endswith(b"\r\n") else b"\n"
    if newline != b"\n":
        inner = inner.replace(b"\n", newline)
    path.write_bytes(opening + inner + closing + body)


def unlink_relation(
    root: Path,
    node_id: str,
    *,
    satisfies: str | None = None,
    upstream: str | None = None,
) -> Path:
    """Remove one declared relation without deleting or rewriting the body."""
    if (satisfies is None) == (upstream is None):
        raise ValueError("exactly one of satisfies or upstream is required")

    field = "satisfies" if satisfies is not None else "upstream"
    target = satisfies if satisfies is not None else upstream
    node = _node(root, node_id)
    post = frontmatter.load(str(node.path))
    current = as_str_list(post.metadata.get(field))
    if target not in current:
        raise ValueError(f"relation not found: {target}")

    remaining = [value for value in current if value != target]
    if remaining:
        post[field] = remaining
    else:
        del post[field]
    _write_unlink_post(node.path, post)
    return node.path


def link_satisfies(root: Path, task_id: str, sr_id: str) -> Path:
    if not (root / "requirements" / f"{sr_id}.md").is_file():
        raise ValueError(f"no such requirement: {sr_id}")
    path = _node_path(root, task_id)
    post = frontmatter.load(str(path))
    current = as_str_list(post.metadata.get("satisfies"))
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


def set_deferred(root: Path, node_id: str, reason: str, *, review_after: str | None = None) -> Path:
    if review_after is None:
        return _update_meta(_node_path(root, node_id), trace_deferred=reason)
    return _update_meta(
        _node_path(root, node_id),
        trace_deferred={"reason": reason, "review_after": review_after},
    )
