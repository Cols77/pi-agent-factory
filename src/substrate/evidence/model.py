from __future__ import annotations

import copy

from substrate.validators.schema import SCHEMA_DIR, validate

MANIFEST_SCHEMA_VERSION = 2
_SCHEMA = SCHEMA_DIR / "evidence_manifest.schema.json"
_RUN_SCHEMA = SCHEMA_DIR / "run.schema.json"
# Spec §20 simulation run bundles identify themselves with a `run` key and no
# `task_id`; v1 orchestration manifests use `run_id`/`task_id`. The two shapes
# live side by side under evidence/runs/ (directory bundles + flat files).


def is_spec20_run_manifest(manifest: dict) -> bool:
    return "run" in manifest and "task_id" not in manifest


def migrate_manifest(manifest: dict) -> dict:
    version = manifest.get("schema_version")
    if version == MANIFEST_SCHEMA_VERSION:
        return manifest
    # A manifest with no schema_version is a legacy v1-shaped record written
    # before the field was introduced (KB-0004 saw finalize crash on such a
    # skew: "schema_version: 2 was expected"). Migrate it through the v1 path;
    # schema validation still rejects garbage afterwards, loudly and at
    # preflight with the file's location.
    if version != 1 and version is not None:
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


def validate_run_manifest(manifest: dict) -> None:
    errors = validate(manifest, _SCHEMA)
    if errors:
        raise ValueError(f"invalid evidence manifest: {'; '.join(errors)}")


def validate_spec20_manifest(manifest: dict) -> None:
    errors = validate(manifest, _RUN_SCHEMA)
    if errors:
        raise ValueError(f"invalid run manifest: {'; '.join(errors)}")
