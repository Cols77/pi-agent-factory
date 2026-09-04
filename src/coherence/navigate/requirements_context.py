"""Read-only, complete project requirement context for semantic reviewers.

This module is deliberately a projection over the register and trace model.  It
never writes artifacts, runs commands, or accepts a path supplied by a caller.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import frontmatter

from coherence.register import register
from coherence.trace import model as trace_model


def _source_anchors(raw: object) -> list[str]:
    if raw is None:
        return []
    values = raw if isinstance(raw, list) else [raw]
    return sorted({str(value) for value in values if str(value).strip()})


def _tokens(statement: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]{3,}", statement.lower()))


def _status(req: register.Requirement, node, incoming: list) -> str:
    if node.deferred:
        return "deferred"
    if any(edge.kind == "satisfies" for edge in incoming):
        return "satisfied"
    if req.binding is None:
        return "proposed"
    return "active"


def _diagnostic(path: Path, error: str) -> dict[str, str]:
    return {"path": str(path), "error": error}


def query_requirements_context(repo_root: Path) -> dict:
    """Return every valid, non-deleted SR and its recorded trace context.

    Invalid files are diagnosed and excluded rather than converted into guessed
    requirements.  The digest covers exactly the canonical ``requirements``
    array, making it suitable for binding a later review packet.
    """
    requirements_dir = repo_root / "requirements"
    diagnostics: list[dict[str, str]] = []
    requirements: list[register.Requirement] = []
    deleted: list[Path] = []
    for path in sorted(requirements_dir.glob("SR-*.md")) if requirements_dir.is_dir() else []:
        try:
            post = frontmatter.load(str(path))
            if bool(post.metadata.get("deleted", False)):
                deleted.append(path)
                continue
            requirements.append(register.parse_requirement(path))
        except (OSError, UnicodeDecodeError, ValueError, TypeError) as exc:
            diagnostics.append(_diagnostic(path, str(exc)))

    try:
        nodes = trace_model.load_nodes(repo_root)
        edges = trace_model.extract_edges(repo_root, nodes)
    except (OSError, ValueError) as exc:
        diagnostics.append(_diagnostic(repo_root, f"trace context unavailable: {exc}"))
        nodes, edges = [], []

    by_id = {node.id: node for node in nodes if node.kind == "sr"}
    feature_ids = {node.id for node in nodes if node.kind == "feat"}
    task_ids = {node.id for node in nodes if node.kind == "task"}
    items: list[dict] = []
    for req in sorted(requirements, key=lambda item: item.id):
        node = by_id.get(req.id)
        if node is None:
            diagnostics.append(_diagnostic(req.path, f"trace node missing for {req.id}"))
            continue
        incoming = [edge for edge in edges if edge.dst == req.id]
        outgoing = [edge for edge in edges if edge.src == req.id]
        relationships = {
            "upstream": sorted(req.upstream),
            "downstream": sorted(edge.src for edge in incoming if edge.kind == "upstream"),
            "features": sorted(edge.src for edge in incoming if edge.kind == "contains" and edge.src in feature_ids),
            "tasks": sorted(edge.src for edge in incoming if edge.kind == "satisfies" and edge.src in task_ids),
            "graph": [
                {"src": edge.src, "dst": edge.dst, "kind": edge.kind}
                for edge in sorted(incoming + outgoing, key=lambda e: (e.src, e.kind, e.dst))
            ],
        }
        try:
            sha256 = hashlib.sha256(req.path.read_bytes()).hexdigest()
        except OSError:
            sha256 = None
            diagnostics.append(_diagnostic(req.path, "requirement source could not be read"))
        source = []
        try:
            source = _source_anchors(frontmatter.load(str(req.path)).metadata.get("source"))
        except (OSError, ValueError):
            pass
        status = _status(req, node, incoming)
        items.append(
            {
                "id": req.id,
                "title": req.title,
                "statement": req.statement,
                "content": req.body,
                "domain": req.domain,
                "status": status,
                "lifecycle": status,
                "source_anchors": source,
                "relationships": relationships,
                "trace_metadata": {
                    "domain": req.domain,
                    "statement_tokens": sorted(_tokens(req.statement)),
                    "upstream": sorted(req.upstream),
                    "binding": req.binding is not None,
                    "source_sha256": sha256,
                },
            }
        )

    duplicate_candidates: list[dict] = []
    contradiction_candidates: list[dict] = []
    for index, left in enumerate(items):
        left_tokens = set(left["trace_metadata"]["statement_tokens"])
        for right in items[index + 1 :]:
            overlap = left_tokens & set(right["trace_metadata"]["statement_tokens"])
            if len(overlap) < 2 or left["domain"] != right["domain"]:
                continue
            candidate = {"ids": [left["id"], right["id"]], "shared_terms": sorted(overlap)}
            duplicate_candidates.append(candidate)
            if ("not" in left_tokens) != ("not" in set(right["trace_metadata"]["statement_tokens"])):
                contradiction_candidates.append(candidate)

    result = {
        "schema": "coherence.requirements-context.v1",
        "requirements": items,
        "diagnostics": diagnostics
        + [{"path": str(path), "error": "requirement marked deleted"} for path in deleted],
        "candidates": {
            "duplicates": duplicate_candidates,
            "contradictions": contradiction_candidates,
        },
        "deferred": {"token_efficient_retrieval": True},
    }
    canonical = json.dumps(items, sort_keys=True, separators=(",", ":"))
    result["context_digest"] = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return result


__all__ = ["query_requirements_context"]
