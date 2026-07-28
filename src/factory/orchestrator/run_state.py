from __future__ import annotations

import json
from pathlib import Path


def read_last_run(repo_root: Path, task_id: str) -> dict | None:
    """Read a task's per-task status mirror (written by FileStatusReporter) and
    return a compact stop-point: {node, state, outcome, handoff, updated_at}.
    Returns None if the mirror is missing or unreadable/corrupt (best-effort)."""
    path = repo_root / "sessions" / ".factory-runs" / f"{task_id}.json"
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(record, dict):
        return None
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
