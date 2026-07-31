from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# Bounded retry for the atomic rename below. On Windows, os.replace() maps to
# MoveFileExW(MOVEFILE_REPLACE_EXISTING), which fails with ERROR_ACCESS_DENIED
# (WinError 5) when another process holds the destination open without
# FILE_SHARE_DELETE -- e.g. a reader that opened the file with Python's default
# share mode, an editor, or a file watcher. The lock is normally transient, so a
# few retries with a short backoff let the write succeed without crashing the
# orchestrator run. Status is best-effort observer telemetry; it must never abort
# the pipeline, which is why a persistent lock is tolerated (warn + continue).
_STATUS_WRITE_ATTEMPTS = 5
_STATUS_WRITE_BACKOFF_S = 0.05


def _atomic_write_json(path: Path, payload: dict) -> None:
    """Write *payload* as JSON to *path* atomically, tolerating transient
    Windows ERROR_ACCESS_DENIED (WinError 5) renames. On a persistent lock,
    drop the temp file and warn instead of raising -- the run continues."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"factory: warning: could not create status directory {path.parent}: {exc}", file=sys.stderr)
        return
    tmp_path = path.with_name(path.name + ".tmp")
    # Write the payload to the temp file first, outside the rename retry loop.
    try:
        tmp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError as exc:
        print(f"factory: warning: could not write status temp file {tmp_path}: {exc}", file=sys.stderr)
        return
    last_exc: OSError | None = None
    for _ in range(_STATUS_WRITE_ATTEMPTS):
        try:
            os.replace(tmp_path, path)
            return
        except OSError as exc:
            last_exc = exc
            time.sleep(_STATUS_WRITE_BACKOFF_S)
    # Persistent lock: clean up the temp file and move on.
    try:
        tmp_path.unlink()
    except OSError:
        pass
    if last_exc is not None:
        print(f"factory: warning: could not write status file {path}: {last_exc}", file=sys.stderr)


class StatusReporter(Protocol):
    def report(
        self,
        *,
        task_id: str,
        node: str,
        node_state: str,
        attempt: int,
        max_attempts: int,
        snippet: str = "",
        outcome: str | None = None,
        handoff: str | None = None,
        session_id: str | None = None,
        summary: str | None = None,
        start_commit: str | None = None,
        already_done: bool = False,
        deliverables: list[str] | None = None,
    ) -> None: ...


class NullStatusReporter:
    def report(
        self,
        *,
        task_id: str,
        node: str,
        node_state: str,
        attempt: int,
        max_attempts: int,
        snippet: str = "",
        outcome: str | None = None,
        handoff: str | None = None,
        session_id: str | None = None,
        summary: str | None = None,
        start_commit: str | None = None,
        already_done: bool = False,
        deliverables: list[str] | None = None,
    ) -> None:
        pass


@dataclass
class FileStatusReporter:
    path: Path
    session_id: str
    started_at: str = field(default_factory=_now)
    _pipeline: list[dict] = field(default_factory=list)

    def report(
        self,
        *,
        task_id: str,
        node: str,
        node_state: str,
        attempt: int,
        max_attempts: int,
        snippet: str = "",
        outcome: str | None = None,
        handoff: str | None = None,
        session_id: str | None = None,
        summary: str | None = None,
        start_commit: str | None = None,
        already_done: bool = False,
        deliverables: list[str] | None = None,
    ) -> None:
        # Update or append the pipeline entry for this node
        entry = {
            "node": node,
            "node_state": node_state,
            "attempt": attempt,
            "max_attempts": max_attempts,
            "snippet": snippet,
            "outcome": outcome,
            "handoff": handoff,
            "session_id": session_id,
            "summary": summary,
            "start_commit": start_commit,
            "already_done": already_done,
            "deliverables": deliverables or [],
            "updated_at": _now(),
        }
        # Find existing entry for this node (same node name) and update it,
        # or append if this is a new node in the pipeline
        replaced = False
        for i, existing in enumerate(self._pipeline):
            if existing["node"] == node:
                # Sticky identity fields: once captured for a node, a later
                # report that omits them (e.g. the reject/escalate paths, or a
                # snippet update) must NOT clobber them back to None. The
                # dashboard needs session_id to open the live session and
                # start_commit to open the review browser; both are captured
                # mid-run and would otherwise be lost on the node's final report.
                for sticky in ("session_id", "start_commit"):
                    if entry[sticky] is None and existing.get(sticky) is not None:
                        entry[sticky] = existing[sticky]
                self._pipeline[i] = entry
                replaced = True
                break
        if not replaced:
            self._pipeline.append(entry)

        record = {
            "session_id": self.session_id,
            "task_id": task_id,
            "current_node": node,
            "current_state": node_state,
            "pipeline": self._pipeline,
            "started_at": self.started_at,
            "updated_at": _now(),
        }
        _atomic_write_json(self.path, record)
        # Mirror the record to a per-task file so a stopped/killed run's state
        # survives the next run overwriting the single global status slot. The
        # picker reads these to show where each task last stopped. Best-effort:
        # _atomic_write_json already swallows OSError and warns, never raising.
        mirror_path = self.path.parent / ".factory-runs" / f"{task_id}.json"
        _atomic_write_json(mirror_path, record)


class FakeStatusReporter:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def report(
        self,
        *,
        task_id: str,
        node: str,
        node_state: str,
        attempt: int,
        max_attempts: int,
        snippet: str = "",
        outcome: str | None = None,
        handoff: str | None = None,
        session_id: str | None = None,
        summary: str | None = None,
        start_commit: str | None = None,
        already_done: bool = False,
        deliverables: list[str] | None = None,
    ) -> None:
        self.calls.append(
            {
                "task_id": task_id,
                "node": node,
                "node_state": node_state,
                "attempt": attempt,
                "max_attempts": max_attempts,
                "snippet": snippet,
                "outcome": outcome,
                "handoff": handoff,
                "session_id": session_id,
                "summary": summary,
                "start_commit": start_commit,
                "already_done": already_done,
                "deliverables": deliverables or [],
            }
        )
