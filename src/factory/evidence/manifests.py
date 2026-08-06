from __future__ import annotations

import json
from pathlib import Path

from factory.validation.schema_validator import SCHEMA_DIR, validate

MANIFEST_SCHEMA_VERSION = 1
_SCHEMA = SCHEMA_DIR / "evidence_manifest.schema.json"


def _validate(manifest: dict) -> None:
    errors = validate(manifest, _SCHEMA)
    if errors:
        raise ValueError(f"invalid evidence manifest: {'; '.join(errors)}")


def write_run_manifest(evidence_dir: Path, manifest: dict) -> Path:
    _validate(manifest)
    runs = evidence_dir / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    path = runs / f"{manifest['run_id']}.json"
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def load_run_manifest(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"invalid evidence manifest: {path}")
    _validate(value)
    return value


def list_run_manifests(evidence_dir: Path, task_id: str | None = None) -> list[dict]:
    out: list[dict] = []
    for path in sorted((evidence_dir / "runs").glob("*.json")):
        try:
            manifest = load_run_manifest(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if task_id is None or manifest["task_id"] == task_id:
            out.append(manifest)
    return sorted(out, key=lambda item: (item["ended_at"], item["run_id"]), reverse=True)
