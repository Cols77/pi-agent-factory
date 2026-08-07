from __future__ import annotations

import json
from pathlib import Path

from factory.validation.kb_validator import parse_entry, validate_entry


def build_index_payload(kb_dir: Path) -> dict:
    index: dict[str, dict] = {}
    for path in sorted(kb_dir.glob("kb-*.md")):
        e = parse_entry(path)
        if validate_entry(e, path):
            continue  # skip entries that fail schema/filename validation
        scope = e.get("scope", {})
        index[str(e["id"])] = {
            "files": scope.get("files", []),
            "error_signatures": scope.get("error_signatures", []),
            "tags": e.get("tags", []),
            "status": e.get("status"),
        }
    return index


def build_index(kb_dir: Path) -> dict:
    index = build_index_payload(kb_dir)
    (kb_dir / "index.json").write_text(
        json.dumps(index, indent=2, sort_keys=True), encoding="utf-8"
    )
    return index
