from __future__ import annotations

import copy
import json
from pathlib import Path

from factory.validation.schema_validator import SCHEMA_DIR, validate

MANIFEST_SCHEMA_VERSION = 2
_SCHEMA = SCHEMA_DIR / "evidence_manifest.schema.json"


def migrate_manifest(manifest: dict) -> dict:
    version = manifest.get("schema_version")
    if version == MANIFEST_SCHEMA_VERSION:
        return manifest
    if version != 1:
        raise ValueError(f"unsupported evidence manifest schema version: {version}")
    migrated = copy.deepcopy(manifest)
    inputs = migrated.get("inputs", {})
    dependencies: list[dict] = []
    task = inputs.get("task", {})
    if isinstance(task.get("path"), str) and isinstance(task.get("sha256"), str):
        dependencies.append(
            {
                "name": f"task:{migrated.get('task_id', 'unknown')}",
                "kind": "file",
                "digest": "sha256:" + task["sha256"],
                "source": task["path"],
            }
        )
    for requirement in inputs.get("requirements", []):
        if not isinstance(requirement, dict):
            continue
        if all(isinstance(requirement.get(key), str) for key in ("id", "path", "sha256")):
            dependencies.append(
                {
                    "name": f"requirement:{requirement['id']}",
                    "kind": "file",
                    "digest": "sha256:" + requirement["sha256"],
                    "source": requirement["path"],
                }
            )
    config_digest = inputs.get("factory_config_sha256")
    if isinstance(config_digest, str):
        dependencies.append(
            {
                "name": "factory-config",
                "kind": "file",
                "digest": "sha256:" + config_digest,
                "source": ".factory/factory.yaml",
            }
        )
    migrated["schema_version"] = MANIFEST_SCHEMA_VERSION
    migrated["dependencies"] = sorted(dependencies, key=lambda item: item["name"])
    return migrated


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
    migrated = migrate_manifest(value)
    _validate(migrated)
    return migrated


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
