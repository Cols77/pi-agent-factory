from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schemas"


def validate_against(instance: dict, schema: dict) -> list[str]:
    """Validate `instance` against an in-memory JSON `schema` dict.

    Returns a list of human-readable error strings; empty means valid.
    """
    validator = Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.path))
    return [f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}" for e in errors]


def validate(instance: dict, schema_path: Path | str) -> list[str]:
    """Validate `instance` against the JSON schema at `schema_path`.

    Returns a list of human-readable error strings; empty means valid.
    """
    schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    return validate_against(instance, schema)
