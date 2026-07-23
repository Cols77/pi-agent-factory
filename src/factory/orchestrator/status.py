from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
            "updated_at": _now(),
        }
        # Find existing entry for this node (same node name) and update it,
        # or append if this is a new node in the pipeline
        replaced = False
        for i, existing in enumerate(self._pipeline):
            if existing["node"] == node:
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
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_name(self.path.name + ".tmp")
        tmp_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        os.replace(tmp_path, self.path)


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
            }
        )
