from __future__ import annotations

from dataclasses import dataclass, field
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
    satisfies: list[str] = field(default_factory=list)


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
    satisfies_value = meta.get("satisfies") or []
    if isinstance(satisfies_value, str):
        satisfies = [satisfies_value]
    else:
        satisfies = [str(s) for s in satisfies_value]
    return Task(
        id=str(meta["id"]),
        title=str(meta["title"]),
        status=str(meta["status"]),
        dod=dod,
        body=post.content,
        path=path,
        satisfies=satisfies,
    )


def load_tasks(tasks_dir: Path) -> list[Task]:
    return sorted((_parse(p) for p in tasks_dir.glob("T-*.md")), key=lambda t: t.id)


def next_todo(tasks: list[Task]) -> Task | None:
    return next((t for t in tasks if t.status == "todo"), None)


def get_task(tasks: list[Task], task_id: str) -> Task | None:
    return next((t for t in tasks if t.id == task_id), None)


class TaskNotFoundError(RuntimeError):
    def __init__(self, task_id: str) -> None:
        super().__init__(f"task not found: {task_id}")
        self.task_id = task_id


class TaskNotTodoError(RuntimeError):
    def __init__(self, task_id: str, status: str) -> None:
        super().__init__(
            f"task {task_id} is not todo (status: {status}); "
            "pass --force to re-run it anyway (e.g. to resume the pipeline after manual work)"
        )
        self.task_id = task_id
        self.status = status


def set_status(task: Task, status: str) -> None:
    post = frontmatter.load(str(task.path))
    post["status"] = status
    task.path.write_text(frontmatter.dumps(post), encoding="utf-8")
    task.status = status


_STATUS_ORDER = ("todo", "done", "rejected", "escalated")


def format_task_board(tasks: list[Task]) -> str:
    if not tasks:
        return "no tasks"

    by_status: dict[str, list[Task]] = {}
    for t in tasks:
        by_status.setdefault(t.status, []).append(t)

    order = [s for s in _STATUS_ORDER if s in by_status]
    order += sorted(s for s in by_status if s not in _STATUS_ORDER)

    lines: list[str] = []
    for status in order:
        group = by_status[status]
        lines.append(f"{status.upper()} ({len(group)})")
        lines.extend(f"  {t.id}  {t.title}" for t in group)
        lines.append("")
    return "\n".join(lines).rstrip("\n")
