from __future__ import annotations

from pathlib import Path

import frontmatter

from factory.validation.schema_validator import SCHEMA_DIR, validate

_SCHEMA = SCHEMA_DIR / "kb_entry.schema.json"


def parse_entry(path: Path) -> dict:
    post = frontmatter.load(str(path))
    metadata = dict(post.metadata)
    # YAML auto-types unquoted date-like scalars (e.g. `created: 2026-07-16`)
    # into datetime.date objects, but the schema declares these as strings.
    for key in ("created", "last_seen"):
        if key in metadata and not isinstance(metadata[key], str):
            metadata[key] = str(metadata[key])
    return metadata


def validate_entry(data: dict, path: Path) -> list[str]:
    """Validate already-parsed frontmatter `data` (from `path`) against the
    KB entry schema plus filename/id consistency."""
    errors = validate(data, _SCHEMA)
    entry_id = data.get("id")
    if isinstance(entry_id, str):
        stem = Path(path).stem
        if stem != entry_id and not stem.startswith(f"{entry_id}-"):
            errors.append(f"filename {Path(path).name} does not start with id {entry_id}")
    return errors


def validate_entry_file(path: Path) -> list[str]:
    return validate_entry(parse_entry(path), path)
