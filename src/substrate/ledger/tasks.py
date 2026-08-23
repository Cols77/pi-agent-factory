from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import frontmatter

_REQUIRED = ("id", "title", "status", "dod")
_JUSTIFICATION_KINDS = (
    "satisfies", "corrects", "mitigates", "implements", "maintains", "explores",
)


class InvalidJustificationError(ValueError):
    pass


@dataclass(frozen=True)
class Justification:
    kind: str
    target_id: str


def _parse_justification(meta: dict) -> list[Justification]:
    raw = meta.get("justification")
    if raw is None:
        # Legacy shorthand: satisfies: [...] means justification: [{satisfies: ...}].
        satisfies_value = meta.get("satisfies") or []
        if isinstance(satisfies_value, str):
            satisfies_value = [satisfies_value]
        return [Justification("satisfies", str(s)) for s in satisfies_value]
    if not isinstance(raw, list):
        raise InvalidJustificationError(
            "justification must be a list of single-key {kind: target_id} mappings"
        )
    out: list[Justification] = []
    for entry in raw:
        if not isinstance(entry, dict) or len(entry) != 1:
            raise InvalidJustificationError(
                f"each justification entry must be a single mapping, got {entry!r}"
            )
        ((kind, target_id),) = entry.items()
        if kind not in _JUSTIFICATION_KINDS:
            raise InvalidJustificationError(
                f"unknown justification kind {kind!r} (have {_JUSTIFICATION_KINDS})"
            )
        out.append(Justification(str(kind), str(target_id)))
    return out


@dataclass
class Task:
    id: str
    title: str
    status: str
    dod: list[str]
    body: str
    path: Path
    satisfies: list[str] = field(default_factory=list)
    # Read here rather than re-parsed in factory.system.story, for the same
    # reason `satisfies` is: the ledger is the one place task frontmatter is
    # parsed. A task written before these fields existed simply has None.
    source_plan: str | None = None
    source_task: int | None = None
    justification: list[Justification] = field(default_factory=list)


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
    justification = _parse_justification(meta)
    satisfies = [j.target_id for j in justification if j.kind == "satisfies"]
    source_plan_value = meta.get("source_plan")
    source_plan = str(source_plan_value) if source_plan_value else None
    # A hand-edited task file can carry anything here. A non-integer is not a
    # section number, so it is absent rather than an error: the plan section is
    # optional context, never a gate.
    try:
        source_task = int(meta["source_task"]) if meta.get("source_task") is not None else None
    except (TypeError, ValueError):
        source_task = None
    return Task(
        id=str(meta["id"]),
        title=str(meta["title"]),
        status=str(meta["status"]),
        dod=dod,
        body=post.content,
        path=path,
        satisfies=satisfies,
        source_plan=source_plan,
        source_task=source_task,
        justification=justification,
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
