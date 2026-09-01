"""Regenerate / check the '## Related requirements' mirror in feature dossiers.

Design decision D-P8: the block is derived from the dossier's own
``requirements:`` frontmatter, cross-checked against the trace graph's
``contains`` edges for that feature node (:mod:`coherence.trace.graph`), and
never hand-edited. Only the entry-list run inside each ``docs/features/FEAT-*.md``
file's ``## Related requirements`` section is ever rewritten -- everything
before the heading, and anything found after the entry list within that same
section (``FEAT-017.md`` has a hand-authored sentence there), is preserved
byte for byte.

Finding worth recording (task brief asked for one if the graph turns out not
to add anything): for every one of the 20 feature dossiers in this repo, the
trace graph's ``contains`` edges for a ``feat`` node are extracted straight
from that same node's ``requirements:`` frontmatter field
(``coherence.trace.model.extract_edges``, the ``node.kind == "feat"`` branch)
in the same order, with no additional filtering, resolution, or enrichment.
So the graph currently contributes no information beyond the frontmatter for
this generator -- ``canonical_requirement_ids`` below still asks the graph,
but only as a standing cross-check that would fail loudly (not silently
diverge) if that ever stopped being true, e.g. if the graph ever started
deduplicating, reordering, or dropping unresolved ids.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
import re

import frontmatter

from coherence.mirrors.render import render_related_requirements_block
from coherence.trace.graph import Graph, build_graph
from coherence.trace.model import Node, as_str_list

__all__ = [
    "MirrorFormatError",
    "MirrorDivergenceError",
    "FeatureMirrorResult",
    "canonical_requirement_ids",
    "feature_nodes",
    "check_all",
    "check_file",
    "regenerate_all",
    "regenerate_file",
]

# The block being replaced is the heading, its one blank line, then a
# contiguous run of "generated-shaped" lines (HTML-comment marker/fingerprint
# lines, and "- ..." list items -- covering both a plain hand-authored entry
# and this generator's own marker/fingerprint/entry lines alike). The first
# line that is neither -- a blank line, prose, another heading -- ends the
# block and everything from there to EOF is preserved verbatim. This matters
# for real data: FEAT-017.md has a hand-authored sentence
# ("Shared contracts consumed by this feature: ...") after its entry list,
# which a naive "heading to EOF" replacement would silently delete.
_BLOCK_START_RE = re.compile(r"(?m)^## Related requirements\r\n\r\n")
_CONSUMABLE_LINE_RE = re.compile(r"(?:<!--.*-->|- .*)\r\n")


class MirrorFormatError(ValueError):
    """The dossier's '## Related requirements' section, or its frontmatter's
    agreement with the trace graph, is not in the expected shape."""


class MirrorDivergenceError(ValueError):
    """The on-disk '## Related requirements' block does not match its
    frontmatter/trace-graph derivation. Message names the offending file.
    """


@dataclass(frozen=True)
class FeatureMirrorResult:
    feature_id: str
    path: Path
    changed: bool


def _read(path: Path) -> str:
    # Deliberately not Path.read_text(): its universal-newline handling would
    # silently rewrite every CRLF in the file to LF on read, and this module
    # must reproduce the file's own CRLF endings exactly.
    return path.read_bytes().decode("utf-8")


def _write(path: Path, text: str) -> None:
    path.write_bytes(text.encode("utf-8"))


def _locate_block(text: str, path: Path) -> re.Match[str]:
    match = _BLOCK_START_RE.search(text)
    if match is None:
        raise MirrorFormatError(
            f"{path}: no '## Related requirements' heading (followed by a blank line) found"
        )
    return match


def _preserved_tail(text: str, block_body_start: int) -> str:
    """Everything after the entry-list run that this generator does not own
    -- hand-authored prose, or anything else -- returned untouched so it can
    be re-appended after the freshly rendered block.
    """
    pos = 0
    while True:
        m = _CONSUMABLE_LINE_RE.match(text, block_body_start + pos)
        if m is None:
            break
        pos = m.end() - block_body_start
    return text[block_body_start + pos :]


def _rebuilt_document(text: str, requirement_ids: Sequence[str], *, path: Path) -> str:
    match = _locate_block(text, path)
    tail = _preserved_tail(text, match.end())
    return text[: match.start()] + render_related_requirements_block(requirement_ids) + tail


def frontmatter_requirement_ids(path: Path) -> list[str]:
    """The dossier's own ``requirements:`` frontmatter, in its own order --
    the canonical order per the task brief (frontmatter order is canonical
    unless there is a reason to sort, and there is none here).
    """
    post = frontmatter.load(str(path))
    return as_str_list(post.metadata.get("requirements"))


def _graph_requirement_ids(node: Node, graph: Graph) -> list[str]:
    return [edge.dst for edge in graph.edges if edge.src == node.id and edge.kind == "contains"]


def feature_nodes(graph: Graph) -> list[Node]:
    """All ``feat`` nodes, sorted by id (``FEAT-001`` .. ``FEAT-020``) so
    regeneration order is stable and independent of the graph builder's own
    filesystem traversal order.
    """
    return sorted((n for n in graph.nodes if n.kind == "feat"), key=lambda n: n.id)


def canonical_requirement_ids(node: Node, graph: Graph) -> list[str]:
    """The frontmatter's ``requirements:`` list, cross-checked against the
    trace graph's ``contains`` edges for this feature node.

    Frontmatter is the source used to render the mirror (see module
    docstring for why the graph currently adds nothing beyond it for these
    20 dossiers). The cross-check exists so a future divergence between the
    two -- the graph extractor changing behaviour, for instance -- raises
    immediately instead of quietly changing what gets written.
    """
    frontmatter_ids = frontmatter_requirement_ids(node.path)
    graph_ids = _graph_requirement_ids(node, graph)
    if frontmatter_ids != graph_ids:
        raise MirrorFormatError(
            f"{node.path}: trace graph 'contains' edges {graph_ids!r} disagree with "
            f"frontmatter requirements {frontmatter_ids!r}"
        )
    return frontmatter_ids


def regenerate_file(node: Node, requirement_ids: Sequence[str]) -> FeatureMirrorResult:
    """Rewrite ``node.path``'s '## Related requirements' block in place.

    Idempotent: if the on-disk block already matches the derivation, the
    file is not written at all (``changed=False``) -- not merely written
    with identical bytes, but left untouched, so repeated runs never even
    dirty the file's mtime for an already-correct dossier.
    """
    original = _read(node.path)
    updated = _rebuilt_document(original, requirement_ids, path=node.path)
    if updated == original:
        return FeatureMirrorResult(node.id, node.path, changed=False)
    _write(node.path, updated)
    return FeatureMirrorResult(node.id, node.path, changed=True)


def check_file(node: Node, requirement_ids: Sequence[str]) -> None:
    """Raise :class:`MirrorDivergenceError` (naming the file) if the on-disk
    block does not byte-for-byte match what regeneration would produce.

    This single full-block comparison is deliberately what catches
    *everything*: a hand-edited entry, a reordered list, an embed
    (``![[...]]``) substituted for a link, a missing/altered marker line, or
    a fingerprint comment that no longer matches its own content -- all of
    them change the rebuilt tail, so all of them fail this one check.
    """
    original = _read(node.path)
    expected = _rebuilt_document(original, requirement_ids, path=node.path)
    if expected != original:
        raise MirrorDivergenceError(
            f"{node.path}: '## Related requirements' block does not match its "
            "frontmatter/trace-graph derivation -- regenerate with "
            "`coherence mirrors generate`"
        )


def regenerate_all(root: Path) -> list[FeatureMirrorResult]:
    graph = build_graph(root)
    results = []
    for node in feature_nodes(graph):
        ids = canonical_requirement_ids(node, graph)
        results.append(regenerate_file(node, ids))
    return results


def check_all(root: Path) -> tuple[str, int]:
    graph = build_graph(root)
    nodes = feature_nodes(graph)
    errors: list[str] = []
    for node in nodes:
        ids = canonical_requirement_ids(node, graph)
        try:
            check_file(node, ids)
        except MirrorDivergenceError as exc:
            errors.append(str(exc))

    lines = [f"wikilink mirrors: {len(nodes)} feature dossier(s) checked"]
    if errors:
        lines.append(f"{len(errors)} divergent (the gate fails on these):")
        lines.append("")
        lines.extend(f"  ! {message}" for message in errors)
    else:
        lines.append("0 divergent -- every mirror matches its frontmatter/trace-graph derivation")
    return "\n".join(lines), (1 if errors else 0)
