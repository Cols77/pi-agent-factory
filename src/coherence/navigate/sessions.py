from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SessionRun:
    """One task-run as recorded in sessions/*.session.json.

    Thinner than an evidence manifest by nature: it has no commit range, no
    changed files and no patch, because none was recorded. Callers must render
    `implementation` as `missing` rather than deriving it from `git.head`.
    """

    run_id: str
    task_id: str
    started_at: str | None
    ended_at: str | None
    outcome: str
    nodes: list[dict]
    dod_met: bool | None
    path: Path


def load_session_runs(repo_root: Path, task_id: str) -> list[SessionRun]:
    """Recorded runs for one task, oldest first. Never raises on bad input."""
    sessions_dir = repo_root / "sessions"
    if not sessions_dir.is_dir():
        return []
    runs: list[SessionRun] = []
    for path in sorted(sessions_dir.glob("*.session.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        try:
            tasks = payload.get("tasks") or []
            if not isinstance(tasks, list):
                continue
            for entry in tasks:
                if not isinstance(entry, dict) or entry.get("task_id") != task_id:
                    continue
                dod = entry.get("dod")
                nodes = entry.get("nodes") or []
                if not isinstance(nodes, list):
                    continue
                runs.append(
                    SessionRun(
                        run_id=str(payload.get("session_id") or path.stem),
                        task_id=task_id,
                        started_at=payload.get("started_at"),
                        ended_at=payload.get("ended_at"),
                        outcome=str(entry.get("outcome") or "unknown"),
                        nodes=list(nodes),
                        dod_met=dod.get("met") if isinstance(dod, dict) else None,
                        path=path,
                    )
                )
        except TypeError:
            continue
    runs.sort(key=lambda r: (r.started_at or "", r.run_id))
    return runs

