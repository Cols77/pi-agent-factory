# src/factory/coverage/imports.py
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class OverlapResult:
    ok: bool
    test_source: str | None
    reached_files: tuple[str, ...]
    changed_files: tuple[str, ...]
    overlap: tuple[str, ...]
    unresolved: tuple[str, ...]


def _import_edges(source: str) -> list[tuple[str, int]]:
    """(module_name, relative_level) pairs from the AST; level 0 = absolute."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    edges: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                edges.append((alias.name, 0))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                edges.append((node.module, node.level))
            elif node.level:
                # "from . import b" has module=None; the name lives in aliases.
                for alias in node.names:
                    edges.append((alias.name, node.level))
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


def transitive_imports(root: Path, source_file: Path) -> tuple[set[Path], set[str]]:
    """All project files transitively imported from source_file.

    Returns (reached_files, unresolved_modules). Files outside the project
    root are unresolved and stop the walk. The source_file itself is excluded
    from reached.
    """
    root_resolved = root.resolve()
    reached: set[Path] = set()
    unresolved: set[str] = set()
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
        for module, level in _import_edges(text):
            resolved = _resolve_import(root, module, level, cur)
            if resolved is None:
                unresolved.add(module)
                continue
            try:
                resolved.relative_to(root_resolved)
            except ValueError:
                continue
            if resolved in seen:
                continue
            reached.add(resolved)
            queue.append(resolved)
    # Exclude the seed itself
    reached.discard(source_file.resolve())
    return reached, unresolved


def _norm(p: Path) -> str:
    return p.as_posix().lstrip("./")


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
