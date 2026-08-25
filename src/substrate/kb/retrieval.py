# src/substrate/kb/retrieval.py
"""Pure KB readers: load and select entries by touched files / failure
signatures. This module is a reader/index only -- nothing here decides
whether a gate passes or fails; that stays factory's job (wiring KB hits
into a gate outcome is out of scope for substrate.kb entirely)."""
from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path
from typing import Iterable

from substrate.codemap.imports import ReachabilityResult
from substrate.validators.kb import parse_entry, validate_entry


def _iter_valid_entries(kb_dir: Path):
    """Yield parsed, schema/filename-valid entries from `kb_dir`, in stable
    (sorted-by-filename) order. Entries that fail validation are skipped
    silently -- callers that care about validation errors should use
    substrate.validators.kb directly."""
    for path in sorted(kb_dir.glob("kb-*.md")):
        entry = parse_entry(path)
        if validate_entry(entry, path):
            continue  # skip entries that fail schema/filename validation
        yield entry


def load_entries(kb_dir: Path, ids: Iterable[str] | None = None) -> list[dict]:
    """Load parsed, valid KB entries from `kb_dir`.

    When `ids` is None, returns every valid entry (sorted by filename). When
    `ids` is given, returns only entries whose id is in `ids`, in the same
    sorted-by-filename order (not the order of `ids`) -- deterministic and
    independent of caller-supplied ordering.
    """
    wanted = set(ids) if ids is not None else None
    return [
        entry
        for entry in _iter_valid_entries(kb_dir)
        if wanted is None or str(entry.get("id")) in wanted
    ]


def select_entries(
    kb_dir: Path,
    touched_files: list[str],
    signatures: list[str],
    reachable_symbols: Iterable[str] | ReachabilityResult = (),
    *,
    diagnostics: list[str] | None = None,
) -> list[str]:
    """Return the sorted ids of active entries whose scope matches a
    touched-file glob, a failure signature substring, or a reachable canonical
    qualified symbol.

    `reachable_symbols` is either:
      - an iterable of canonical fully-qualified symbol names (e.g.
        `factory.module.function`) that were already resolved by the caller, or
      - a `ReachabilityResult` from `substrate.codemap.imports.reachable_symbols`.

    When a `ReachabilityResult` is supplied and its `status` is NOT
    "resolved" (stale/missing/unsupported), symbol scope is treated as
    unmatched: a staleness diagnostic from the result is surfaced via
    `diagnostics` (if given) and NO symbol hit is claimed. There is NEVER a
    file-glob/text fallback for a symbol scope -- a stale codemap cannot be
    papered over by globbing the symbol's name against touched files.

    Legacy `files` globs and `error_signatures` matching are unchanged and
    still work independently of symbol scope. When `reachable_symbols` is empty
    (the default), symbol scope is simply never matched.
    """
    if isinstance(reachable_symbols, ReachabilityResult):
        if reachable_symbols.status != "resolved":
            if diagnostics is not None:
                diagnostics.extend(list(reachable_symbols.diagnostics))
            reachable: set[str] = set()
        else:
            reachable = set(reachable_symbols.symbols)
    else:
        reachable = set(reachable_symbols or ())

    hits: set[str] = set()
    for entry in _iter_valid_entries(kb_dir):
        if entry.get("status") != "active":
            continue
        scope = entry.get("scope", {})
        globs = scope.get("files", [])
        sigs = scope.get("error_signatures", [])
        symbols = scope.get("symbols", [])

        file_hit = any(fnmatch(tf, g) for tf in touched_files for g in globs)
        sig_hit = any(s in provided for s in sigs for provided in signatures)
        # Canonical qualified match ONLY -- a scope symbol must equal a reachable
        # symbol exactly; never globbed or substring-matched.
        sym_hit = any(sym in reachable for sym in symbols)

        if file_hit or sig_hit or sym_hit:
            hits.add(str(entry["id"]))
    return sorted(hits)


def list_kb_titles(kb_dir: Path) -> list[tuple[str, str]]:
    """Return (id, title) for every entry in `kb_dir`, including inactive
    ones -- used for duplicate-avoidance awareness, not task relevance, so
    unlike select_entries it does not filter by status or validity."""
    titles: list[tuple[str, str]] = []
    for path in sorted(kb_dir.glob("kb-*.md")):
        entry = parse_entry(path)
        entry_id = entry.get("id")
        title = entry.get("title")
        if entry_id is not None and title is not None:
            titles.append((str(entry_id), str(title)))
    return titles
