"""Ref normalisation and the label index projection.

The repository carries two live spellings for document refs:
`trace/model.py:86` builds `spec:<basename>`, `system/coverage.py:70` builds
`spec:<repo-relative-path>`. `bundles.py:203` already documents that both
denote one file. This module is the single place that resolves either
spelling -- and bare ids like `T-060` -- to one canonical form.

The browser never parses a ref. It looks one up here.
"""
from __future__ import annotations

from pathlib import Path

from factory.trace import model as trace_model

# Kinds whose identity is the file, not a symbol: their canonical ref uses
# the repo-relative POSIX path instead of the bare id. Every other kind
# `trace_model.load_nodes` emits (sr, br, task, feat, metric, goal, diag)
# canonicalises on its bare id -- there is no third category to branch on,
# so that's an unconditional `else`, not a fallback for an unhandled case.
_PATH_KINDS = frozenset({"spec", "plan"})


def _relative_posix(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def canonical_ref(root: Path, node: trace_model.Node) -> str:
    if node.kind in _PATH_KINDS:
        # node.path is always absolute (trace_model.load_nodes globs from
        # `root`), so no join against `root` is needed here.
        return f"{node.kind}:{_relative_posix(root, node.path)}"
    return f"{node.kind}:{node.id}"


def build_alias_map(root: Path, nodes: list[trace_model.Node] | None = None) -> dict[str, str]:
    """Every non-canonical spelling encountered, mapped to its canonical ref.

    Includes the bare id, the `<kind>:<basename>` form the trace graph emits,
    and the canonical ref itself (so a lookup is one dict access either way).
    """
    if nodes is None:
        nodes = trace_model.load_nodes(root)
    aliases: dict[str, str] = {}
    for node in nodes:
        canonical = canonical_ref(root, node)
        aliases[canonical] = canonical
        aliases[node.id] = canonical
        if node.kind in _PATH_KINDS:
            # `_file_node` already sets id = "<kind>:<basename>"
            # (trace/model.py:86), so node.id is ALREADY the basename spelling.
            # Prefixing it again would mint junk keys like "spec:spec:foo.md".
            aliases[f"{node.kind}:{Path(node.path).name}"] = canonical
        else:
            aliases[f"{node.kind}:{node.id}"] = canonical
    return aliases


def normalize_ref(
    root: Path, raw: str, aliases: dict[str, str] | None = None
) -> str | None:
    """Resolve a raw ref or bare id to its canonical form, or None.

    Never guesses: an input with no recorded artifact behind it returns None
    so the renderer can say so plainly.
    """
    if aliases is None:
        aliases = build_alias_map(root)
    return aliases.get(raw.strip())
