from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path

from factory.validation.kb_validator import parse_entry


def _iter_entries(kb_dir: Path):
    for path in sorted(kb_dir.glob("kb-*.md")):
        yield parse_entry(path)


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
