from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import frontmatter

_REQUIRED = ("id", "title", "status", "dod")


@dataclass
class Task:
    id: str
    title: str
    status: str
    dod: list[str]
    body: str
    path: Path


def _parse(path: Path) -> Task:
    post = frontmatter.load(str(path))
    meta = post.metadata
    missing = [k for k in _REQUIRED if k not in meta]
    if missing:
        raise ValueError(f"{path.name}: missing required field(s): {missing}")
    # Normalize dod: if it's a scalar string, wrap it in a list; if already a list, use as-is
    dod_value = meta["dod"]
    if isinstance(dod_value, str):
        dod = [dod_value]
    else:
        dod = list(dod_value)  # type: ignore[arg-type]
    return Task(
        id=str(meta["id"]),
        title=str(meta["title"]),
        status=str(meta["status"]),
        dod=dod,
        body=post.content,
        path=path,
    )


def load_tasks(tasks_dir: Path) -> list[Task]:
    return sorted((_parse(p) for p in tasks_dir.glob("T-*.md")), key=lambda t: t.id)


def next_todo(tasks: list[Task]) -> Task | None:
    return next((t for t in tasks if t.status == "todo"), None)


def set_status(task: Task, status: str) -> None:
    post = frontmatter.load(str(task.path))
    post["status"] = status
    task.path.write_text(frontmatter.dumps(post), encoding="utf-8")
    task.status = status
