from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path

from factory.validation.kb_validator import parse_entry, validate_entry


def _iter_entries(kb_dir: Path):
    for path in sorted(kb_dir.glob("kb-*.md")):
        entry = parse_entry(path)
        if validate_entry(entry, path):
            continue  # skip entries that fail schema/filename validation
        yield entry


def select_entries(kb_dir: Path, touched_files: list[str], signatures: list[str]) -> list[str]:
    hits: set[str] = set()
    for entry in _iter_entries(kb_dir):
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
    titles: list[tuple[str, str]] = []
    for path in sorted(kb_dir.glob("kb-*.md")):
        entry = parse_entry(path)
        entry_id = entry.get("id")
        title = entry.get("title")
        if entry_id is not None and title is not None:
            titles.append((str(entry_id), str(title)))
    return titles
