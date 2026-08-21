from __future__ import annotations

import warnings

from substrate.ledger.tasks import (
    Task,
    TaskNotFoundError,
    TaskNotTodoError,
    format_task_board,
    get_task,
    load_tasks,
    next_todo,
    set_status,
)

warnings.warn(
    "factory.orchestrator.ledger is deprecated; import substrate.ledger.tasks",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "Task",
    "TaskNotFoundError",
    "TaskNotTodoError",
    "format_task_board",
    "get_task",
    "load_tasks",
    "next_todo",
    "set_status",
]
