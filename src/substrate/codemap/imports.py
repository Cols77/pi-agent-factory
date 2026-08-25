"""Python import-edge tracking for the durable code map.

Two layers live here, sharing a single traversal implementation
(`_closure_walk`) so the older, narrower answer can never drift from the
newer, structured one by hand-synchronization error:

- `compute_overlap`/`transitive_imports` -- the original coverage-binding
  algorithm (moved here from `factory.coverage.imports`). Given a test
  selection and a set of changed files, does the test's import closure touch
  any of them? `transitive_imports` is now a thin projection of
  `_closure_walk` that keeps only the (reached_files, unresolved_modules)
  pair the old callers depend on and discards the edge list -- the answer is
  identical to the pre-move implementation by construction, not by two
  hand-kept-in-sync loops.
- `build_import_closure` -- a structured view over the same traversal,
  returning `ImportClosure(files, status, diagnostics)` for one or more root
  files. Unlike `transitive_imports`, the roots themselves are included in
  `files`, and unresolved imports or unsupported (non-Python) roots are
  reported as an explicit status rather than silently folded into "no
  overlap".

Import edges discovered while building a closure are also persisted beside
the fingerprinted `CodeIndex` data (`.factory/code-index/`), so a later
consumer can read them back without re-parsing. That store is a write-through
side artifact only: `build_import_closure` always recomputes from source, so
a missing or stale edges file (an index directory written before this module
existed, for instance) never changes the answer -- it is simply not there to
read yet, and the reader tolerates that.
"""
from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from substrate.codemap.build import LATEST_STEM, fingerprint_for, index_dir
from substrate.codemap.store import load_latest

EDGES_LATEST_STEM = "imports-latest.json"


@dataclass(frozen=True)
class ImportEdge:
    source: str
    target: str
    kind: str


@dataclass(frozen=True)
class ImportClosure:
    files: tuple[str, ...]
    status: str
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True)
class OverlapResult:
    ok: bool
    test_source: str | None
    reached_files: tuple[str, ...]
    changed_files: tuple[str, ...]
    overlap: tuple[str, ...]
    unresolved: tuple[str, ...]


@dataclass(frozen=True)
class ReachabilityResult:
    """Outcome of computing which canonical qualified symbols are reachable
    from a set of changed files through the codemap import graph.

    `status` is one of:
      - "resolved": symbols reflect a FRESH codemap snapshot walked across the
        changed files' import closure. `symbols` is trustworthy.
      - "stale":   a codemap snapshot exists but its content fingerprint no
        longer matches the source. Callers must emit a staleness diagnostic and
        claim NO symbol hit -- do not fall back to a file glob.
      - "missing": no codemap snapshot has been built. Same conservative rule.
      - "unsupported": a changed file is not Python (no import traversal).
        Same conservative rule.
    `symbols` is canonical fully-qualified names (package.module.name). It is
    ALWAYS empty when status is not "resolved".
    """

    status: str
    symbols: tuple[str, ...] = ()
    diagnostics: tuple[str, ...] = ()
    snapshot_ref: str | None = None


def _import_edges(source: str) -> list[tuple[str, int, str]]:
    """(module_name, relative_level, kind) triples from the AST.

    level 0 = absolute. kind is "import" for `import x`, "from" for
    `from x import y` (level 0), "relative" for `from . import y` /
    `from .x import y` (level > 0).
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    edges: list[tuple[str, int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                edges.append((alias.name, 0, "import"))
        elif isinstance(node, ast.ImportFrom):
            kind = "relative" if node.level else "from"
            if node.module:
                edges.append((node.module, node.level, kind))
            elif node.level:
                # "from . import b" has module=None; the name lives in aliases.
                for alias in node.names:
                    edges.append((alias.name, node.level, kind))
    return edges


def _module_candidates(root: Path, module: str, level: int, origin: Path) -> list[Path]:
    """Candidate files for an import, in resolution order.

    Relative imports are anchored on the importing file's package directory.
    The src/ layout is tried as a second candidate root.
    """
    base = origin.parent if origin is not None else root
    if level > 0:
        for _ in range(level - 1):
            base = base.parent
    parts = module.split(".") if module else []
    if level > 0 and base != root:
        rel = base.relative_to(root)
        parts = list(rel.parts) + parts
    dotted = ".".join(parts)
    rel_path = dotted.replace(".", "/")
    candidates: list[Path] = []
    for anchor in (root, root / "src"):
        candidates.append(anchor / f"{rel_path}.py")
        candidates.append(anchor / rel_path / "__init__.py")
    return candidates


def _resolve_import(root: Path, module: str, level: int, origin: Path) -> Path | None:
    for cand in _module_candidates(root, module, level, origin):
        try:
            if cand.is_file():
                return cand.resolve()
        except OSError:
            continue
    return None


def _norm(p: Path) -> str:
    return p.as_posix().lstrip("./")


def _closure_walk(
    root: Path, source_file: Path
) -> tuple[set[Path], set[str], list[ImportEdge]]:
    """The single BFS traversal both transitive_imports and
    build_import_closure are built on: walks every file reachable from
    source_file, resolving each import via _resolve_import, and records
    every edge encountered (resolved or not) as an ImportEdge.

    Returns (reached_files, unresolved_modules, edges). Files outside the
    project root are unresolved and stop the walk. source_file itself is
    excluded from reached.
    """
    root_resolved = root.resolve()
    reached: set[Path] = set()
    unresolved: set[str] = set()
    edges: list[ImportEdge] = []
    seen: set[Path] = set()
    queue: list[Path] = [source_file.resolve()]
    while queue:
        cur = queue.pop(0)
        if cur in seen or not cur.exists():
            continue
        seen.add(cur)
        try:
            text = cur.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        try:
            src_rel = _norm(cur.relative_to(root_resolved))
        except ValueError:
            src_rel = _norm(cur)
        for module, level, kind in _import_edges(text):
            resolved = _resolve_import(root, module, level, cur)
            if resolved is None:
                unresolved.add(module)
                edges.append(ImportEdge(source=src_rel, target=module, kind=kind))
                continue
            try:
                resolved.relative_to(root_resolved)
            except ValueError:
                continue
            tgt_rel = _norm(resolved.relative_to(root_resolved))
            edges.append(ImportEdge(source=src_rel, target=tgt_rel, kind=kind))
            if resolved in seen:
                continue
            reached.add(resolved)
            queue.append(resolved)
    # Exclude the seed itself
    reached.discard(source_file.resolve())
    return reached, unresolved, edges


def transitive_imports(root: Path, source_file: Path) -> tuple[set[Path], set[str]]:
    """All project files transitively imported from source_file.

    Returns (reached_files, unresolved_modules). Files outside the project
    root are unresolved and stop the walk. The source_file itself is excluded
    from reached.

    A thin projection of _closure_walk: keeps its (reached, unresolved) pair
    and discards the edge list, so this old, narrower answer is guaranteed
    identical to build_import_closure's traversal by construction.
    """
    reached, unresolved, _edges = _closure_walk(root, source_file)
    return reached, unresolved


def compute_overlap(root: Path, selection: str, changed_files: Iterable[str]) -> OverlapResult:
    """Phase 1: does the binding test selection reach any changed file?

    selection is a pytest selection (path or node id). The leading path is
    resolved relative to the project root; the transitive import closure is
    intersected with changed_files (repo-relative paths).
    """
    changed = tuple(_norm(Path(c)) for c in changed_files)
    if "::" in selection:
        selection = selection.split("::", 1)[0]
    source = root / selection.lstrip("/")
    if not source.exists():
        return OverlapResult(False, None, (), changed, (), ())
    reached, unresolved = transitive_imports(root, source)
    root_resolved = root.resolve()
    reached_rel = tuple(
        sorted(_norm(p.relative_to(root_resolved)) for p in reached)
    )
    overlap = tuple(sorted(set(reached_rel) & set(changed)))
    return OverlapResult(
        ok=bool(overlap),
        test_source=_norm(source),
        reached_files=reached_rel,
        changed_files=changed,
        overlap=overlap,
        unresolved=tuple(sorted(unresolved)),
    )


def build_import_closure(repo_root: Path, roots: Iterable[str]) -> ImportClosure:
    """Structured import closure over one or more root files.

    `files` is the sorted union of the (existing, Python) roots plus every
    file transitively reached from them -- unlike `transitive_imports`, the
    roots are included, not excluded.

    `status` is:
      - "unsupported" when any root exists but is not a Python source. A
        signature extractor existing elsewhere (tree-sitter) does not mean
        this layer claims transitive coverage for it; the root is reported
        on its own with no traversal.
      - "unresolved" when any root is missing on disk (a "selection missing"
        diagnostic) or any encountered import could not be resolved to a
        project file (an "unresolved import" diagnostic).
      - "resolved" otherwise.
    Unsupported takes precedence over unresolved when a root set mixes both,
    since "we don't know" is the more conservative signal.
    """
    repo_root = Path(repo_root)
    root_list = [str(r) for r in roots]
    diagnostics: list[str] = []

    missing = [r for r in root_list if not (repo_root / r).exists()]
    for r in missing:
        diagnostics.append(f"selection missing: {r}")

    present = [r for r in root_list if r not in missing]
    unsupported = [r for r in present if Path(r).suffix != ".py"]
    for r in unsupported:
        diagnostics.append(f"unsupported source type: {r}")

    python_roots = [r for r in present if r not in unsupported]

    files: set[str] = set(python_roots) | set(unsupported)
    unresolved_modules: set[str] = set()
    edges: list[ImportEdge] = []

    root_resolved = repo_root.resolve()
    for root_rel in python_roots:
        reached, unresolved, walk_edges = _closure_walk(repo_root, repo_root / root_rel)
        unresolved_modules |= unresolved
        edges.extend(walk_edges)
        for p in reached:
            files.add(_norm(p.relative_to(root_resolved)))

    for module in sorted(unresolved_modules):
        diagnostics.append(f"unresolved import: {module}")

    if unsupported:
        status = "unsupported"
    elif missing or unresolved_modules:
        status = "unresolved"
    else:
        status = "resolved"

    try:
        _save_edges(repo_root, sorted(files), tuple(edges))
    except OSError:
        pass

    return ImportClosure(files=tuple(sorted(files)), status=status, diagnostics=tuple(diagnostics))


def _edges_path(repo_root: Path, fingerprint: str) -> Path:
    safe = fingerprint.replace(":", "_")
    return index_dir(repo_root) / f"{safe}.imports.json"


def _atomic_json(path: Path, data: dict) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _save_edges(repo_root: Path, files: list[str], edges: tuple[ImportEdge, ...]) -> Path:
    """Persist edges beside the fingerprinted CodeIndex data, keyed by the
    same content-fingerprint convention as substrate.codemap.build. A
    write-through side artifact only -- build_import_closure never reads
    this back to decide its answer."""
    fp = fingerprint_for(files, repo_root) if files else "no-files"
    d = index_dir(repo_root)
    d.mkdir(parents=True, exist_ok=True)
    edge_file = _edges_path(repo_root, fp)
    _atomic_json(
        edge_file,
        {
            "schema": 1,
            "fingerprint": fp,
            "edges": [{"source": e.source, "target": e.target, "kind": e.kind} for e in edges],
        },
    )
    _atomic_json(d / EDGES_LATEST_STEM, {"schema": 1, "fingerprint": fp, "path": edge_file.name})
    return edge_file


def _load_edges(repo_root: Path, files: list[str]) -> tuple[ImportEdge, ...] | None:
    """Backward-compatible reader: an index directory written before edge
    storage existed (or a missing/corrupt edges file) yields None rather
    than raising, so callers fall back to recomputing from source."""
    fp = fingerprint_for(files, repo_root) if files else "no-files"
    edge_file = _edges_path(repo_root, fp)
    if not edge_file.exists():
        return None
    try:
        data = json.loads(edge_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if data.get("fingerprint") != fp:
        return None
    raw_edges = data.get("edges")
    if raw_edges is None:
        return None
    try:
        return tuple(
            ImportEdge(source=e["source"], target=e["target"], kind=e["kind"]) for e in raw_edges
        )
    except (KeyError, TypeError):
        return None


def _module_of(rel: str) -> str:
    """Canonical dotted module path for a repo-relative source file.

    A `src/` layout contributes no package segment, so `src/factory/module.py`
    becomes `factory.module` (matching the KB scope convention). `__init__.py`
    collapses to its package (`pkg/__init__.py` -> `pkg`).
    """
    base = rel[:-3] if rel.endswith(".py") else rel
    parts = [p for p in base.split("/") if p not in ("src", "")]
    return ".".join(parts)


def _qualified_symbols(index, files: Iterable[str]) -> set[str]:
    """Canonical fully-qualified names for every signature in `files`, drawn
    from the (fresh) codemap snapshot: `module_of(file).signature_name`."""
    from substrate.codemap.build import file_signatures

    out: set[str] = set()
    for rel in files:
        sigs = file_signatures(index, rel) or []
        module = _module_of(rel)
        for s in sigs:
            name = s.get("name")
            if name:
                out.add(f"{module}.{name}")
    return out


def reachable_symbols(
    repo_root: Path, changed_files: Iterable[str]
) -> ReachabilityResult:
    """Return the canonical qualified symbols reachable from the changed files
    across the codemap import graph.

    The answer is only ever trusted when a FRESH codemap snapshot exists:

      - "missing"  -- no snapshot has been built. A staleness diagnostic is
        returned and NO symbols are claimed.
      - "stale"    -- a snapshot exists but its content fingerprint no longer
        matches the source. Same conservative rule.
      - "unsupported" -- a changed file is not Python. Same conservative rule.
      - "resolved" -- the snapshot is fresh; `symbols` holds the fully-qualified
        names defined in every file reachable (by import) from the changed
        files, so a symbol that MOVED to another file is still found as long as
        the changed file reaches it through the import graph.

    Callers (e.g. KB retrieval) must NEVER glob a symbol scope against file
    paths as a fallback when status is stale/missing/unsupported.
    """
    root = Path(repo_root)
    changed = [_norm(Path(str(c))) for c in changed_files if c]
    changed = [c for c in changed if c]
    diagnostics: list[str] = []

    missing_files = [c for c in changed if not (root / c).exists()]
    for c in missing_files:
        diagnostics.append(f"selection missing: {c}")

    unsupported = [c for c in changed if Path(c).suffix != ".py"]
    for c in unsupported:
        diagnostics.append(f"unsupported source type: {c}")

    index = load_latest(root)
    if index is None:
        diagnostics.append(
            f"codemap snapshot missing: {index_dir(root) / LATEST_STEM}"
        )
        return ReachabilityResult(status="missing", diagnostics=tuple(diagnostics))

    from substrate.codemap.build import is_fresh

    if not is_fresh(index, root):
        diagnostics.append(
            "codemap snapshot stale (fingerprint mismatch); "
            "symbol reachability unavailable"
        )
        return ReachabilityResult(
            status="stale",
            diagnostics=tuple(diagnostics),
            snapshot_ref=index.fingerprint,
        )

    # Snapshot is fresh. Unsupported changed roots still block symbol claims.
    if unsupported:
        return ReachabilityResult(
            status="unsupported",
            diagnostics=tuple(diagnostics),
            snapshot_ref=index.fingerprint,
        )

    python_changed = [c for c in changed if Path(c).suffix == ".py"]
    if not python_changed:
        return ReachabilityResult(
            status="resolved",
            symbols=(),
            diagnostics=tuple(diagnostics),
            snapshot_ref=index.fingerprint,
        )

    closure = build_import_closure(root, python_changed)
    if closure.status == "unsupported":
        return ReachabilityResult(
            status="unsupported",
            diagnostics=closure.diagnostics + tuple(diagnostics),
            snapshot_ref=index.fingerprint,
        )

    if closure.status == "unresolved":
        # Unresolved imports are surfaced as diagnostics but do not block the
        # resolved answer: we still trust the closure we were able to walk from
        # a fresh snapshot. (Only stale/missing/unsupported suppress symbols.)
        diagnostics.extend(closure.diagnostics)

    symbols = _qualified_symbols(index, closure.files)
    return ReachabilityResult(
        status="resolved",
        symbols=tuple(sorted(symbols)),
        diagnostics=tuple(diagnostics),
        snapshot_ref=index.fingerprint,
    )
