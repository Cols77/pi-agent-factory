from pathlib import Path

import pytest
from factory.orchestrator.ledger import (
    Task,
    TaskNotFoundError,
    TaskNotTodoError,
    format_task_board,
    get_task,
    load_tasks,
    next_todo,
    set_status,
)
from substrate.ledger.tasks import Task as SubstrateTask
from substrate.ledger.tasks import load_tasks as substrate_load_tasks
from substrate.ledger.tasks import set_status as substrate_set_status

pytestmark = pytest.mark.unit


def _write(tmp_path, name, status="todo"):
    (tmp_path / name).write_text(
        f"---\nid: {name.split('-')[0]}-{name.split('-')[1]}\ntitle: t\n"
        f"status: {status}\ndod:\n  - x\n---\nbody\n",
        encoding="utf-8",
    )


def _task(id_, title, status):
    return Task(id=id_, title=title, status=status, dod=["x"], body="", path=Path(f"{id_}.md"))


def test_load_and_next_todo(tmp_path):
    _write(tmp_path, "T-002-b.md", status="done")
    _write(tmp_path, "T-001-a.md", status="todo")
    tasks = load_tasks(tmp_path)
    assert [t.id for t in tasks] == ["T-001", "T-002"]
    assert next_todo(tasks).id == "T-001"


def test_missing_required_field_raises(tmp_path):
    (tmp_path / "T-003-x.md").write_text("---\nid: T-003\n---\nb\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_tasks(tmp_path)


def test_set_status_rewrites(tmp_path):
    _write(tmp_path, "T-001-a.md")
    task = load_tasks(tmp_path)[0]
    set_status(task, "done")
    assert load_tasks(tmp_path)[0].status == "done"


def test_scalar_dod_normalized_to_list(tmp_path):
    # Write a task file with scalar (non-list) dod value
    (tmp_path / "T-001-a.md").write_text(
        "---\nid: T-001\ntitle: t\nstatus: todo\ndod: single scalar value\n---\nbody\n",
        encoding="utf-8",
    )
    tasks = load_tasks(tmp_path)
    assert tasks[0].dod == ["single scalar value"]


def test_format_task_board_groups_by_status_with_counts():
    tasks = [
        _task("T-001", "First task", "todo"),
        _task("T-002", "Second task", "done"),
        _task("T-003", "Third task", "todo"),
    ]
    board = format_task_board(tasks)
    assert "TODO (2)" in board
    assert "DONE (1)" in board
    assert "T-001  First task" in board
    assert "T-003  Third task" in board
    assert "T-002  Second task" in board
    assert board.index("TODO (2)") < board.index("DONE (1)")


def test_format_task_board_empty_ledger():
    assert format_task_board([]) == "no tasks"


def test_format_task_board_preserves_input_order_within_group():
    tasks = [_task("T-002", "b", "todo"), _task("T-001", "a", "todo")]
    board = format_task_board(tasks)
    assert board.index("T-002") < board.index("T-001")


def test_get_task_found():
    tasks = [_task("T-001", "a", "todo"), _task("T-002", "b", "done")]
    assert get_task(tasks, "T-002").title == "b"


def test_get_task_not_found_returns_none():
    tasks = [_task("T-001", "a", "todo")]
    assert get_task(tasks, "T-999") is None


def test_task_not_found_error_message():
    err = TaskNotFoundError("T-999")
    assert err.task_id == "T-999"
    assert "T-999" in str(err)


def test_task_not_todo_error_message():
    err = TaskNotTodoError("T-001", "done")
    assert err.task_id == "T-001"
    assert err.status == "done"
    assert "T-001" in str(err) and "done" in str(err)


def _write_task(tasks_dir: Path, text: str) -> None:
    tasks_dir.mkdir(parents=True, exist_ok=True)
    (tasks_dir / "T-001-x.md").write_text(text, encoding="utf-8")


def test_task_carries_source_plan_and_source_task(tmp_path):
    _write_task(
        tmp_path / "tasks",
        "---\nid: T-001\ntitle: t\nstatus: todo\ndod:\n- d\n"
        "source_plan: docs/superpowers/plans/p.md\nsource_task: 3\n---\nbody\n",
    )

    task = load_tasks(tmp_path / "tasks")[0]

    assert task.source_plan == "docs/superpowers/plans/p.md"
    assert task.source_task == 3


def test_task_without_source_fields_defaults_to_none(tmp_path):
    _write_task(tmp_path / "tasks", "---\nid: T-001\ntitle: t\nstatus: todo\ndod:\n- d\n---\nbody\n")

    task = load_tasks(tmp_path / "tasks")[0]

    assert task.source_plan is None
    assert task.source_task is None


def test_non_integer_source_task_becomes_none(tmp_path):
    _write_task(
        tmp_path / "tasks",
        "---\nid: T-001\ntitle: t\nstatus: todo\ndod:\n- d\nsource_task: not-a-number\n---\nbody\n",
    )

    assert load_tasks(tmp_path / "tasks")[0].source_task is None


# --- Parity: factory.orchestrator.ledger (deprecated shim) vs
# substrate.ledger.tasks (the real implementation the shim re-exports). ---


def test_substrate_ledger_tasks_is_the_same_class_the_shim_re_exports():
    # The shim re-exports the substrate class object directly (no parallel
    # redefinition) -- so an old Task and a "new" Task are literally the
    # same type, not merely structurally equal.
    assert Task is SubstrateTask


def test_load_tasks_parity_with_substrate(tmp_path):
    _write(tmp_path, "T-002-b.md", status="done")
    _write(tmp_path, "T-001-a.md", status="todo")
    assert load_tasks(tmp_path) == substrate_load_tasks(tmp_path)


def test_load_tasks_parity_with_substrate_including_satisfies_and_source_fields(tmp_path):
    _write_task(
        tmp_path / "tasks",
        "---\nid: T-001\ntitle: t\nstatus: todo\ndod:\n- d\n"
        "satisfies:\n  - SR-001\nsource_plan: docs/superpowers/plans/p.md\nsource_task: 3\n---\nbody\n",
    )
    old = load_tasks(tmp_path / "tasks")
    new = substrate_load_tasks(tmp_path / "tasks")
    assert old == new
    assert old[0].satisfies == new[0].satisfies == ["SR-001"]


def test_status_write_parity_between_old_and_new_set_status(tmp_path):
    _write(tmp_path, "T-001-a.md")
    task_via_old = load_tasks(tmp_path)[0]
    set_status(task_via_old, "done")
    reread_via_old = load_tasks(tmp_path)[0]
    reread_via_new = substrate_load_tasks(tmp_path)[0]
    assert reread_via_old == reread_via_new == task_via_old

    _write(tmp_path, "T-002-b.md")
    task_via_new = substrate_load_tasks(tmp_path)[1]
    substrate_set_status(task_via_new, "done")
    assert load_tasks(tmp_path)[1].status == "done"
    assert substrate_load_tasks(tmp_path)[1] == load_tasks(tmp_path)[1]
