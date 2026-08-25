# src/substrate/kb/index.py
"""Build the on-disk `kb/index.json` summary from KB entry frontmatter."""
from __future__ import annotations

import json
from pathlib import Path

from substrate.validators.kb import parse_entry, validate_entry


def build_index_payload(kb_dir: Path) -> dict:
    """Return the index payload for every valid KB entry under `kb_dir`,
    without writing anything to disk. Entries that fail schema/filename
    validation are skipped rather than raising -- a single malformed entry
    must not block indexing the rest of the KB."""
    index: dict[str, dict] = {}
    for path in sorted(kb_dir.glob("kb-*.md")):
        e = parse_entry(path)
        if validate_entry(e, path):
            continue  # skip entries that fail schema/filename validation
        scope = e.get("scope", {})
        index[str(e["id"])] = {
            "files": scope.get("files", []),
            "error_signatures": scope.get("error_signatures", []),
            "symbols": scope.get("symbols", []),
            "tags": e.get("tags", []),
            "status": e.get("status"),
        }
    return index


def build_index(kb_dir: Path) -> dict:
    """Compute the index payload and persist it to `kb_dir/index.json`."""
    index = build_index_payload(kb_dir)
    (kb_dir / "index.json").write_text(
        json.dumps(index, indent=2, sort_keys=True), encoding="utf-8"
    )
    return index