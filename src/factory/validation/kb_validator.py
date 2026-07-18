from __future__ import annotations

from pathlib import Path

import frontmatter

from factory.validation.schema_validator import SCHEMA_DIR, validate

_SCHEMA = SCHEMA_DIR / "kb_entry.schema.json"


def parse_entry(path: Path) -> dict:
    post = frontmatter.load(str(path))
    return dict(post.metadata)


def validate_entry_file(path: Path) -> list[str]:
    data = parse_entry(path)
    errors = validate(data, _SCHEMA)
    entry_id = data.get("id")
    if isinstance(entry_id, str) and not Path(path).stem.startswith(entry_id):
        errors.append(f"filename {Path(path).name} does not start with id {entry_id}")
    return errors
