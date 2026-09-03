from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from substrate.codemap.build import file_signatures
from substrate.codemap.model import CodeIndex
from substrate.codemap.store import ensure_fresh

# SR-050/AC-1: "Each requirement an implementation slice changes carries
# typed implementation and validation references whose repository-relative
# paths resolve inside the project and whose symbol or pytest node
# identifiers resolve to real definitions, with no line number used as
# identity." (requirements/SR-050.md)
#
# This module resolves the structured relations the source design names
# (docs/superpowers/specs/2026-08-31-sr-code-validation-traceability-design.md
# #canonical-relations):
#
#   implemented_by: [{path: <repo-relative>, symbol: <dotted.module>:<name>}]
#   verified_by:    [{path: <repo-relative>, test: <path>::<node>[::<node>]}]
#
# against the actual repository. It deliberately reuses the existing code
# map (substrate.codemap: ensure_fresh/file_signatures) for symbol and
# pytest-node resolution rather than building a second parser -- the index
# already carries every function/class/method name substrate discovers, in
# every source_dir the project profile configures (which includes tests/,
# see .pi/factory/project-profile.json).
#
# This is a plain string-list ``verified_by: [T-001]`` (a task/run id, not a
# structured relation) IS NOT handled here -- that shape is the pre-existing
# graph edge coherence.trace.model.edges_from_frontmatter._verified_by_edges
# reads. A caller with raw frontmatter can hold both fields at once; this
# resolver only ever inspects dict entries, so it naturally ignores plain
# strings without help from the caller.

_RELATION_FIELDS: tuple[str, ...] = ("implemented_by", "verified_by")

# A bare integer segment after the ``:``/``::`` separator is a line number,
# not a stable symbol or pytest-node identity -- the source design forbids
# using one as identity ("It does not use line numbers as identity.").
_LINE_SEGMENT_RE = re.compile(r"^\d+$")


@dataclass(frozen=True)
class ReferenceIssue:
    """One declared implemented_by/verified_by entry that failed to resolve."""

    field: str  # "implemented_by" | "verified_by"
    index: int
    detail: str


@dataclass(frozen=True)
class RelationResolution:
    """Result of resolving every implemented_by/verified_by entry an SR
    node's frontmatter declares. ``ok`` is True only when every declared
    structured entry resolved; an SR with no structured relations at all
    resolves ok (AC-1 constrains declared references, it does not itself
    require that any exist)."""

    issues: tuple[ReferenceIssue, ...]

    @property
    def ok(self) -> bool:
        return not self.issues


def _confined_path(root: Path, raw: str) -> Path | None:
    """Repository-relative path that resolves inside the project, else None.

    Mirrors the root-confinement convention already used by
    ``coherence.navigate.snapshots`` and ``coherence.policy.compiler``: an
    absolute path or any ``".."`` path segment is rejected on the string
    alone, before the filesystem is ever consulted.
    """
    candidate = Path(raw)
    if candidate.is_absolute() or ".." in candidate.parts:
        return None
    full = root / candidate
    if not full.is_file():
        return None
    return candidate


def _has_line_identity(value: str, sep: str) -> bool:
    """True when any segment after the first ``sep`` split is a bare
    integer (e.g. ``"path.py:42"`` or ``"path.py::113"``) -- a line number
    masquerading as a name/node id, not identity the design allows."""
    segments = value.split(sep)[1:]
    return any(_LINE_SEGMENT_RE.match(seg.strip()) for seg in segments if seg.strip())


def _module_from_path(rel_path: str) -> str:
    """Best-effort dotted module name for a repo-relative source path,
    matching the design's own example (``src/coherence/navigate/feature.py``
    -> ``coherence.navigate.feature``): drop a leading ``src`` segment (the
    project's package root) and the file suffix."""
    parts = list(Path(rel_path).with_suffix("").parts)
    if parts and parts[0] == "src":
        parts = parts[1:]
    return ".".join(parts)


def _resolve_symbol(index: CodeIndex, rel_path: str, symbol: str) -> str | None:
    """Return an error detail, or None when ``symbol`` resolves inside
    ``rel_path``. ``symbol`` must be ``<dotted.module>:<name>`` per the
    design; ``<name>`` may itself be dotted (``Class.method``), in which
    case only the leaf is matched against the index (the index does not
    qualify method names by their owning class)."""
    if _has_line_identity(symbol, ":"):
        return f"symbol {symbol!r} uses a line number as identity, not a stable name"
    module_part, sep, name_part = symbol.rpartition(":")
    if not sep or not module_part.strip() or not name_part.strip():
        return f"symbol {symbol!r} must be '<dotted.module>:<name>'"
    expected_module = _module_from_path(rel_path)
    if module_part.strip() != expected_module:
        return f"symbol {symbol!r} module does not match path {rel_path!r} (expected {expected_module!r})"
    leaf = name_part.strip().rsplit(".", 1)[-1]
    sigs = file_signatures(index, rel_path) or []
    names = {s["name"] for s in sigs}
    if leaf not in names:
        return f"symbol {symbol!r} does not resolve to a definition in {rel_path}"
    return None


def _resolve_test(index: CodeIndex, rel_path: str, test: str) -> str | None:
    """Return an error detail, or None when ``test`` resolves inside
    ``rel_path``. ``test`` must be a pytest node id whose file segment
    matches the entry's own ``path``."""
    if _has_line_identity(test, "::"):
        return f"test {test!r} uses a line number as identity, not a pytest node id"
    parts = test.split("::")
    test_path, node_parts = parts[0], parts[1:]
    if test_path != rel_path:
        return f"test {test!r} path does not match declared path {rel_path!r}"
    if not node_parts:
        return f"test {test!r} must be a pytest node id '<path>::<name>[::<name>...]'"
    leaf = node_parts[-1].strip()
    if not leaf:
        return f"test {test!r} must be a pytest node id '<path>::<name>[::<name>...]'"
    sigs = file_signatures(index, rel_path) or []
    names = {s["name"] for s in sigs}
    if leaf not in names:
        return f"test {test!r} does not resolve to a definition in {rel_path}"
    return None


def resolve_sr_relations(root: Path, meta: dict) -> RelationResolution:
    """Resolve every ``implemented_by``/``verified_by`` structured-relation
    entry an SR's raw frontmatter declares (SR-050/AC-1). A non-dict entry
    (the legacy plain-string ``verified_by: [T-001]`` graph edge) is not
    this resolver's concern and is silently skipped -- see the module
    docstring.
    """
    issues: list[ReferenceIssue] = []
    # Two passes: first validate/confine every declared path and collect the
    # exact set that needs symbol/test-node resolution, THEN build the code
    # map off exactly that file set. `ensure_fresh`'s default discovery walks
    # the project profile's source_dirs (["src"] with no profile at all) --
    # a declared `path` under `tests/` (or any dir the profile omits) would
    # never be indexed by an implicit, no-args `ensure_fresh(root)` call, so
    # passing the declared files explicitly is what makes every dir the
    # relations may legitimately point at (production AND test code)
    # resolvable, not just whatever a profile happens to list.
    pending: list[tuple[str, int, dict, str]] = []  # (field, index, entry, rel_str)
    needed_files: set[str] = set()
    seen: set[tuple[str, str, str]] = set()  # (field, path, symbol-or-test) already declared
    for field in _RELATION_FIELDS:
        raw = meta.get(field)
        if raw is None:
            continue
        if not isinstance(raw, list):
            issues.append(ReferenceIssue(field, 0, f"{field} must be a list of mappings"))
            continue
        for i, entry in enumerate(raw):
            if not isinstance(entry, dict):
                continue  # legacy string-list shape (or malformed scalar) -- not ours
            raw_path = entry.get("path")
            if not raw_path or not str(raw_path).strip():
                issues.append(ReferenceIssue(field, i, f"{field}[{i}] missing required 'path'"))
                continue
            rel_path = _confined_path(root, str(raw_path))
            if rel_path is None:
                issues.append(
                    ReferenceIssue(
                        field, i, f"{field}[{i}] path {raw_path!r} does not resolve inside the project"
                    )
                )
                continue
            rel_str = rel_path.as_posix()
            if field == "implemented_by" and not entry.get("symbol"):
                issues.append(ReferenceIssue(field, i, f"{field}[{i}] missing required 'symbol'"))
                continue
            # File-only verified_by (the design's allowance for non-pytest
            # harnesses -- just `path`, no `test`) needs no symbol/test
            # resolution, but still participates in duplicate detection
            # below, keyed on an empty identity segment.
            file_only = field == "verified_by" and not str(entry.get("test") or "").strip()
            identity = "" if file_only else str(entry.get("symbol") or entry.get("test") or "")
            key = (field, rel_str, identity)
            if key in seen:
                issues.append(ReferenceIssue(field, i, f"{field}[{i}] duplicates an earlier declaration"))
                continue
            seen.add(key)
            if file_only:
                continue
            pending.append((field, i, entry, rel_str))
            needed_files.add(rel_str)

    if not pending:
        return RelationResolution(issues=tuple(issues))

    index = ensure_fresh(root, files=sorted(needed_files))
    for field, i, entry, rel_str in pending:
        if field == "implemented_by":
            detail = _resolve_symbol(index, rel_str, str(entry["symbol"]))
        else:
            detail = _resolve_test(index, rel_str, str(entry["test"]))
        if detail is not None:
            issues.append(ReferenceIssue(field, i, detail))
    return RelationResolution(issues=tuple(issues))


__all__ = ["ReferenceIssue", "RelationResolution", "resolve_sr_relations"]
