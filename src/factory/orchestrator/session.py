from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from factory.orchestrator.types import TaskResult
from factory.validation.session_validator import validate_session


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_record(
    session_id: str, model_backend: str, results: list[TaskResult], git_info: dict
) -> dict:
    tasks = []
    for r in results:
        tasks.append(
            {
                "task_id": r.task_id,
                "title": r.title,
                "outcome": r.outcome,
                "iterations": r.iterations,
                "nodes": [
                    {"node": e.node, "result": e.result, "attempts": e.attempts, "extra": e.extra} for e in r.events
                ],
                "commits": [],
                "dod": {"met": r.dod_met},
            }
        )
    return {
        "session_id": session_id,
        "started_at": _now(),
        "ended_at": _now(),
        "model_backend": model_backend,
        "git": git_info,
        "tasks": tasks,
        "kb_changes": {"added": [], "updated": [], "pruned": []},
        "escalations": [t["task_id"] for t in tasks if t["outcome"] == "escalated"],
        "resume": {"next_task": None, "hint": ""},
    }


def write_session(sessions_dir: Path, record: dict) -> Path:
    errors = validate_session(record)
    if errors:
        raise ValueError(f"invalid session record: {errors}")
    sessions_dir.mkdir(parents=True, exist_ok=True)
    path = sessions_dir / f"{record['session_id']}.session.json"
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")

    digest = [f"# Session {record['session_id']}", ""]
    for t in record["tasks"]:
        digest.append(f"- {t['task_id']} ({t['outcome']}, {t['iterations']} iters): {t.get('title', '')}")
    (sessions_dir / "latest.md").write_text("\n".join(digest) + "\n", encoding="utf-8")
    return path
