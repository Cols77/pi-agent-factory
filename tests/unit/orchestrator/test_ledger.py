from pathlib import Path

import pytest
from factory.orchestrator.ledger import Task, format_task_board, load_tasks, next_todo, set_status

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
