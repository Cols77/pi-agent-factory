from __future__ import annotations

from substrate.validators.schema import SCHEMA_DIR, validate

_SCHEMA = SCHEMA_DIR / "session_record.schema.json"


def validate_session(record: dict) -> list[str]:
    errors = validate(record, _SCHEMA)
    if errors:
        return errors

    semantic: list[str] = []
    for task in record.get("tasks", []):
        if task.get("outcome") == "completed":
            dod = task.get("dod") or {}
            if dod.get("met") is not True:
                semantic.append(f"task {task.get('task_id')}: completed but dod.met is not true")
    return semantic
