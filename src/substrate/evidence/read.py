from __future__ import annotations

import json
from pathlib import Path

from substrate.evidence.model import (
    is_spec20_run_manifest,
    migrate_manifest,
    validate_run_manifest,
)

# No write function lives here (or anywhere under substrate.evidence):
# factory.evidence.manifests.write_run_manifest remains the sole atomic
# writer. substrate only reads and normalises what is already on disk.


def load_run_manifest(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"invalid evidence manifest: {path}")
    if is_spec20_run_manifest(value):
        # Tolerant: unknown fields are preserved untouched; a malformed bundle
        # degrades to a scope_errors-carrying Run in the registry (Task 2).
        return value
    migrated = migrate_manifest(value)
    validate_run_manifest(migrated)
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
