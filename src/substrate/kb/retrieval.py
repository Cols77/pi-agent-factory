# src/substrate/kb/retrieval.py
"""Pure KB readers: load and select entries by touched files / failure
signatures. This module is a reader/index only -- nothing here decides
whether a gate passes or fails; that stays factory's job (wiring KB hits
into a gate outcome is out of scope for substrate.kb entirely)."""
from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path
from typing import Iterable

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


def select_entries(kb_dir: Path, touched_files: list[str], signatures: list[str]) -> list[str]:
    """Return the sorted ids of active entries whose scope matches either a
    touched-file glob or a failure signature substring."""
    hits: set[str] = set()
    for entry in _iter_valid_entries(kb_dir):
        if entry.get("status") != "active":
            continue
        scope = entry.get("scope", {})
        globs = scope.get("files", [])
        sigs = scope.get("error_signatures", [])

        file_hit = any(fnmatch(tf, g) for tf in touched_files for g in globs)
        sig_hit = any(s in provided for s in sigs for provided in signatures)

        if file_hit or sig_hit:
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
