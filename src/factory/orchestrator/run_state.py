from __future__ import annotations

import json
from pathlib import Path


def _load_record(path: Path) -> dict | None:
    """Read a JSON status record from *path*, or None if missing/corrupt/not a dict."""
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return record if isinstance(record, dict) else None


def _extract(record: dict) -> dict:
    """Compress a full status record into a stop-point summary."""
    node = record.get("current_node")
    pipeline = record.get("pipeline", [])
    if not isinstance(pipeline, list):
        pipeline = []
    # Reason: the handoff on the current node's own pipeline entry.
    handoff = None
    for entry in pipeline:
        if isinstance(entry, dict) and entry.get("node") == node:
            handoff = entry.get("handoff")
    # Outcome: the last non-null outcome recorded across the pipeline.
    outcome = None
    for entry in pipeline:
        if isinstance(entry, dict) and entry.get("outcome"):
            outcome = entry["outcome"]
    return {
        "node": node,
        "state": record.get("current_state"),
        "outcome": outcome,
        "handoff": handoff,
        "updated_at": record.get("updated_at"),
    }


def read_last_run(repo_root: Path, task_id: str) -> dict | None:
    """Return a task's last-run stop-point {node, state, outcome, handoff,
    updated_at}, or None if there's no run state for it.

    Prefers the per-task mirror (written by FileStatusReporter on every report).
    Falls back to the global status slot when no mirror exists AND that slot's
    task_id matches -- this covers a run that predates per-task mirroring, or a
    mirror write that failed while the global write succeeded. Best-effort:
    never raises on a missing or corrupt file."""
    mirror = repo_root / "sessions" / ".factory-runs" / f"{task_id}.json"
    record = _load_record(mirror)
    if record is None:
        # Fallback to the global slot only if it's THIS task's run (it holds the
        # most-recent run and must not be misattributed to a different task).
        global_status = _load_record(repo_root / "sessions" / ".factory-status.json")
        if global_status is None or global_status.get("task_id") != task_id:
            return None
        record = global_status
    return _extract(record)
