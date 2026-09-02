"""Regenerate / check the '## Related requirements' mirror in feature dossiers.

Design decision D-P8: the block is derived from the dossier's own
``requirements:`` frontmatter, cross-checked against the trace graph's
``contains`` edges for that feature node (:mod:`coherence.trace.graph`), and
never hand-edited. Only the generator-owned span inside each
``docs/features/FEAT-*.md`` file's ``## Related requirements`` section is
ever rewritten -- everything before the heading, and anything found after
the owned span within that same section (``FEAT-017.md`` has a
hand-authored sentence there), is preserved byte for byte.

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

Review round 2 -- what changed and why (see task-7-report.md's appended fix
report for the full account):

* Owned boundary, not shape inference. ``render.py`` now emits an explicit
  end sentinel (``END_MARKER_LINE``) after the entry list. Once a file
  carries it, :func:`_locate_block` finds it with a single search and owns
  everything between the heading and that sentinel, unconditionally -- no
  more "does this line look like one of ours?" guessing, which is what let
  a hand-authored bullet placed directly after the entry list (no blank
  line separating it) get silently swallowed and deleted. A file that has
  never been generated (no sentinel yet, including all 20 real dossiers
  before this generator's first run) still needs a boundary to be derived
  once; that fallback uses a strict per-line shape match (an actual
  ``- [[SR-...]]``/``- ![[SR-...]]`` wikilink, or the exact placeholder
  line, or one of this generator's own comment lines) that a plain
  hand-authored bullet like ``- Note: also relates to legacy system X.``
  does not match, so it is never mistaken for an owned entry.
* Line-ending agnostic. Every regex in this module accepts CRLF, bare LF, or
  end-of-string (a final line with no trailing newline at all) as a line
  terminator. ``_detect_eol`` reads the file's own dominant line ending once
  and that is what ``render_related_requirements_block`` is asked to emit,
  so an LF-only checkout is processed correctly and stays LF-only; a CRLF
  file stays CRLF. Regeneration never rewrites a file's line endings as a
  side effect.
* A format error is a per-file failure, not a crash that aborts the run.
  ``MirrorFormatError`` and ``MirrorDivergenceError`` are both caught, per
  node, in both ``regenerate_all`` and ``check_all`` -- one malformed
  dossier is reported and the loop continues to the next file rather than
  raising an unhandled exception that leaves the rest of the tree
  unprocessed (and, for ``regenerate_all``, potentially half-regenerated).

Review round 3 -- what changed and why:

* Critical 1. The end-sentinel search is bounded to the
  ``## Related requirements`` section and the section must carry exactly one
  sentinel. An unbounded search silently deleted every section between the
  heading and a sentinel merely *mentioned* in later prose, and turned a
  stray sentinel inside the owned span into a permanently-green duplicated
  block. See :func:`_locate_block`.
* Important 2. The per-file catch is now unconditional, so the promise two
  bullets up ("one bad file can never abort the run") holds for unparseable
  frontmatter (``yaml.scanner.ScannerError``) and every other single-file
  failure, not only ``MirrorFormatError``. See :func:`_per_file_failure`.
* Minor 1. ``_detect_eol``'s docstring said "dominant"; the code reads the
  first line ending. The docstring was corrected -- see the function for why
  that is the right direction.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
import re

import frontmatter

from coherence.mirrors.render import (
    DEFAULT_EOL,
    END_MARKER_LINE,
    MARKER_LINE,
    PLACEHOLDER_LINE,
    render_related_requirements_block,
)
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

# A single line terminator: CRLF, bare LF, or "nothing -- end of string"
# (a file, or a generator-owned span, that ends with no trailing newline at
# all). Every pattern below ends with this so none of them is CRLF-only.
_EOL_ALT = r"(?:\r\n|\n|\Z)"

_HEADING_BLANK_RE = re.compile(
    r"^## Related requirements[ \t]*" + _EOL_ALT + r"[ \t]*" + _EOL_ALT,
    re.MULTILINE,
)

# The end sentinel, anchored to the start of its own line. Searched for only
# WITHIN the '## Related requirements' section (see `_section_end`): once
# exactly one is found there it defines the owned span unconditionally --
# whatever lies between the heading and this sentinel belongs to the
# generator regardless of its shape (a hand-tampered embed, a reordered
# entry, anything). That is what makes reintroducing `![[SR-019]]` between
# the markers still detected as a divergence rather than mistaken for
# hand-authored content outside the block. Zero or two-or-more sentinels in
# the section is an ambiguous boundary, never a guess -- see `_locate_block`.
_END_MARKER_RE = re.compile(
    r"^" + re.escape(END_MARKER_LINE) + r"[ \t]*" + _EOL_ALT, re.MULTILINE
)

# The section boundary: the next top-level ('## ') heading after the
# '## Related requirements' heading, or end of file. A '### ' subheading does
# not match, so a subsection stays inside the section.
_SECTION_END_RE = re.compile(r"^## ", re.MULTILINE)

# This generator's own "do not edit" marker line, used only to tell a
# never-generated dossier (bootstrap, no marker) apart from a generated one
# whose end sentinel has gone missing (derived content with no boundary).
_DERIVED_MARKER_RE = re.compile(
    r"^" + re.escape(MARKER_LINE) + r"[ \t]*" + _EOL_ALT, re.MULTILINE
)

# Bootstrap-only fallback (used when no end sentinel exists yet -- a dossier
# that has never been generated, or one generated by the pre-sentinel format
# this generator wrote before this fix). Deliberately strict: only this
# generator's own comment lines and actual wikilink/embed/placeholder entries
# match, so a hand-authored bullet that happens to start with "- " but is not
# one of those exact shapes (e.g. "- Note: also relates to legacy system X.")
# does not match and correctly ends the run instead of being swallowed.
_COMMENT_LINE_RE = re.compile(r"<!--[^\r\n]*-->[ \t]*" + _EOL_ALT)
_ENTRY_LINE_RE = re.compile(
    r"- (?:!?\[\[[^\[\]\r\n]+\]\]|" + re.escape(PLACEHOLDER_LINE[2:]) + r")[ \t]*" + _EOL_ALT
)


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
    error: str | None = None


def _read(path: Path) -> str:
    # Deliberately not Path.read_text(): its universal-newline handling would
    # silently rewrite every CRLF in the file to LF on read, and this module
    # must reproduce the file's own line endings exactly.
    return path.read_bytes().decode("utf-8")


def _write(path: Path, text: str) -> None:
    path.write_bytes(text.encode("utf-8"))


def _detect_eol(text: str) -> str:
    """The file's **first** line ending -- CRLF if the first newline in the
    document is preceded by a carriage return, else bare LF; the repo's
    existing convention (CRLF, ``DEFAULT_EOL``) for the degenerate case of a
    file with no newline at all. Regeneration always emits this back, never a
    different one.

    Minor 1 (review round 3): this docstring used to say "dominant line
    ending" while the code has always read the *first* one. The docstring is
    what was corrected, deliberately. First-newline is deterministic, O(1),
    and cannot itself rewrite a file's endings; true dominance (a majority
    vote) would, on a mixed-ending file, emit the majority ending into a
    block whose neighbours use the other one -- an unrequested rewrite of
    exactly the kind this module exists not to do. Nothing requires
    dominance, and every dossier this generator touches is single-convention.
    """
    idx = text.find("\n")
    if idx == -1:
        return DEFAULT_EOL
    return "\r\n" if idx > 0 and text[idx - 1] == "\r" else "\n"


def _section_end(text: str, body_start: int) -> int:
    """Offset of the next top-level ``## `` heading at or after ``body_start``,
    or ``len(text)`` at end of file. This is the hard bound on everything this
    module will ever consider part of the '## Related requirements' section.
    """
    match = _SECTION_END_RE.search(text, body_start)
    return match.start() if match is not None else len(text)


def _locate_block(text: str, path: Path) -> tuple[int, int]:
    """Return (start, end) offsets of the generator-owned span: from the
    ``## Related requirements`` heading through either (a) the section's one
    end sentinel -- the *owned* boundary, honoured unconditionally regardless
    of what lies between -- or (b) the last recognizable comment/entry line
    for a dossier that has never been generated, using a strict shape match
    that cannot mistake ordinary hand-authored prose for an owned entry.

    Critical 1 (review round 3). The sentinel search used to be unbounded: it
    took the FIRST line-anchored sentinel anywhere after the heading, however
    far down the file, and never checked how many existed. Two harms
    followed, both reproduced against real dossiers:

    * **Silent deletion.** A never-generated dossier that merely *mentions*
      the sentinel in later prose had every section in between swallowed into
      the owned span and deleted -- ``changed=True``, no error, the CLI
      printing ``regenerated:``.
    * **Permanent self-consistent duplication.** A stray sentinel inside the
      owned span made regeneration write the derived block twice, both halves
      fingerprinted and sentinel-closed, after which ``check`` found the same
      first sentinel the generator had just written and reported 0 divergent
      forever.

    Both are boundary *ambiguity*, and this module's contract is that an
    ambiguous boundary is reported, never guessed. So the search is bounded to
    the section (heading .. next ``## `` heading or EOF) and the section must
    contain **exactly one** sentinel:

    * one -> the owned span, as before;
    * two or more -> :class:`MirrorFormatError` (ambiguous end);
    * zero, with a sentinel elsewhere in the file -> :class:`MirrorFormatError`
      (the file names this generator's boundary outside the span it owns --
      the shape that used to delete data silently);
    * zero, with this generator's own marker line inside the section ->
      :class:`MirrorFormatError` (derived content with no end sentinel; the
      bootstrap shape match below is only ever correct for a dossier that has
      never been generated, and must not be used to re-guess a boundary that
      once existed);
    * zero, and none of the above -> the bootstrap shape match, unchanged,
      now also hard-bounded at the section end.

    A ``MirrorFormatError`` is caught per file by both ``regenerate_all`` and
    ``check_all``, so each of these is a reported per-file failure with the
    file left byte-for-byte untouched.
    """
    heading_match = _HEADING_BLANK_RE.search(text)
    if heading_match is None:
        raise MirrorFormatError(
            f"{path}: no '## Related requirements' heading (followed by a blank line) found"
        )
    start = heading_match.start()
    body_start = heading_match.end()
    section_end = _section_end(text, body_start)

    all_sentinels = list(_END_MARKER_RE.finditer(text))
    in_section = [m for m in all_sentinels if body_start <= m.start() < section_end]

    if len(in_section) > 1:
        raise MirrorFormatError(
            f"{path}: the '## Related requirements' section contains "
            f"{len(in_section)} '{END_MARKER_LINE}' lines; the generator-owned "
            "span has no unambiguous end. Delete the stray sentinel(s) so exactly "
            "one remains, then rerun `coherence mirrors generate`"
        )
    if len(in_section) == 1:
        return start, in_section[0].end()

    if all_sentinels:
        raise MirrorFormatError(
            f"{path}: '{END_MARKER_LINE}' appears outside the "
            "'## Related requirements' section, which itself carries none. This "
            "generator only ever owns a span inside that section, so the boundary "
            "is ambiguous and the file is left untouched. Remove or reword the "
            "out-of-section sentinel, then rerun `coherence mirrors generate`"
        )

    marker = _DERIVED_MARKER_RE.search(text)
    if marker is not None and body_start <= marker.start() < section_end:
        raise MirrorFormatError(
            f"{path}: the '## Related requirements' section carries this "
            f"generator's marker line but no '{END_MARKER_LINE}'; it is derived "
            "content with no recorded end. Restore the sentinel on its own line "
            "after the entry list, then rerun `coherence mirrors generate`"
        )

    pos = body_start
    while pos < section_end:
        m = _COMMENT_LINE_RE.match(text, pos) or _ENTRY_LINE_RE.match(text, pos)
        if m is None or m.end() == pos or m.end() > section_end:
            break
        pos = m.end()
    return start, pos


def _rebuilt_document(text: str, requirement_ids: Sequence[str], *, path: Path) -> str:
    start, end = _locate_block(text, path)
    eol = _detect_eol(text)
    tail = text[end:]
    return text[:start] + render_related_requirements_block(requirement_ids, eol=eol) + tail


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


def _per_file_failure(node: Node, exc: Exception) -> str:
    """The one place a per-file failure is turned into a report line.

    Important 2 (review round 3): only ``MirrorFormatError`` used to be
    caught, so anything else raised while processing one dossier -- most
    realistically a ``yaml.scanner.ScannerError`` out of ``frontmatter.load``
    on unparseable frontmatter, but equally an ``OSError`` on an unreadable
    file or a ``UnicodeDecodeError`` on a non-UTF-8 one -- escaped the loop
    *after earlier dossiers had already been written*, which is precisely the
    half-regenerated tree the module docstring promises can never happen.

    The catch is deliberately unconditional (``Exception``) rather than a
    hand-maintained tuple: the docstring's promise is unconditional, and a
    tuple would silently reacquire the same defect the first time a
    dependency raised a type nobody had listed. Nothing is swallowed -- the
    exception's type and message become the file's reported error, and both
    ``regenerate_all`` and ``check_all`` surface every one of them.
    """
    if isinstance(exc, (MirrorFormatError, MirrorDivergenceError)):
        return str(exc)
    return f"{node.path}: {type(exc).__name__}: {exc}"


def regenerate_all(root: Path) -> list[FeatureMirrorResult]:
    """Regenerate every feature dossier's mirror. A malformed dossier is
    reported as a per-file failure -- ``error`` set, ``changed=False``, file
    left untouched -- and processing continues with the next dossier; one bad
    file can never abort the run or leave the tree half-regenerated. That
    holds for *any* failure raised while processing a single dossier, not
    only ``MirrorFormatError`` (see :func:`_per_file_failure`).
    """
    graph = build_graph(root)
    results: list[FeatureMirrorResult] = []
    for node in feature_nodes(graph):
        try:
            ids = canonical_requirement_ids(node, graph)
            results.append(regenerate_file(node, ids))
        except Exception as exc:  # noqa: BLE001 -- see _per_file_failure
            results.append(
                FeatureMirrorResult(
                    node.id, node.path, changed=False, error=_per_file_failure(node, exc)
                )
            )
    return results


def check_all(root: Path) -> tuple[str, int]:
    graph = build_graph(root)
    nodes = feature_nodes(graph)
    errors: list[str] = []
    for node in nodes:
        try:
            ids = canonical_requirement_ids(node, graph)
            check_file(node, ids)
        except Exception as exc:  # noqa: BLE001 -- see _per_file_failure
            errors.append(_per_file_failure(node, exc))

    lines = [f"wikilink mirrors: {len(nodes)} feature dossier(s) checked"]
    if errors:
        lines.append(f"{len(errors)} divergent (the gate fails on these):")
        lines.append("")
        lines.extend(f"  ! {message}" for message in errors)
    else:
        lines.append("0 divergent -- every mirror matches its frontmatter/trace-graph derivation")
    return "\n".join(lines), (1 if errors else 0)
