from __future__ import annotations

import copy
import json
from pathlib import Path

from factory.validation.schema_validator import SCHEMA_DIR, validate

MANIFEST_SCHEMA_VERSION = 2
_SCHEMA = SCHEMA_DIR / "evidence_manifest.schema.json"
_RUN_SCHEMA = SCHEMA_DIR / "run.schema.json"
# Spec §20 simulation run bundles identify themselves with a `run` key and no
# `task_id`; v1 orchestration manifests use `run_id`/`task_id`. The two shapes
# live side by side under evidence/runs/ (directory bundles + flat files).

def _is_spec20_run_manifest(manifest: dict) -> bool:
    return "run" in manifest and "task_id" not in manifest


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


def _validate_spec20(manifest: dict) -> None:
    errors = validate(manifest, _RUN_SCHEMA)
    if errors:
        raise ValueError(f"invalid run manifest: {'; '.join(errors)}")


def _write_json_atomic(path: Path, manifest: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    tmp.replace(path)


def write_run_manifest(evidence_dir: Path, manifest: dict) -> Path:
    """Write a run manifest: §20 simulation bundles as RUN-<run>/manifest.json,
    v1 orchestration manifests as flat runs/<run_id>.json. Additive; v1 callers
    and files are unchanged."""
    runs = evidence_dir / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    if _is_spec20_run_manifest(manifest):
        defaults = {"feature": None, "requirements": [], "commit": None, "result": None}
        normalized = {**defaults, **manifest}
        _validate_spec20(normalized)
        path = runs / normalized["run"] / "manifest.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_json_atomic(path, normalized)
        return path
    _validate(manifest)
    path = runs / f"{manifest['run_id']}.json"
    _write_json_atomic(path, manifest)
    return path


def load_run_manifest(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"invalid evidence manifest: {path}")
    if _is_spec20_run_manifest(value):
        # Tolerant: unknown fields are preserved untouched; a malformed bundle
        # degrades to a scope_errors-carrying Run in the registry (Task 2).
        return value
    migrated = migrate_manifest(value)
    _validate(migrated)
    return migrated


def _run_sort_key(item: dict) -> tuple:
    """Deterministic order for mixed shapes: §20 runs sort by `run` id, v1 runs
    by ended_at then run_id. Missing keys never crash listing."""
    if "run" in item:
        return (item.get("ended_at") or "", item.get("run") or "")
    return (item.get("ended_at") or "", item.get("run_id") or "")


def list_run_manifests(evidence_dir: Path, task_id: str | None = None) -> list[dict]:
    out: list[dict] = []
    runs = evidence_dir / "runs"
    paths = sorted(runs.glob("*.json")) + sorted(runs.glob("*/manifest.json"))
    for path in paths:
        try:
            manifest = load_run_manifest(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if task_id is None:
            out.append(manifest)
        elif "task_id" in manifest and manifest["task_id"] == task_id:
            out.append(manifest)
    return sorted(out, key=_run_sort_key, reverse=True)
