import pytest
from factory.orchestrator.ledger import load_tasks, next_todo, set_status

pytestmark = pytest.mark.unit


def _write(tmp_path, name, status="todo"):
    (tmp_path / name).write_text(
        f"---\nid: {name.split('-')[0]}-{name.split('-')[1]}\ntitle: t\n"
        f"status: {status}\ndod:\n  - x\n---\nbody\n",
        encoding="utf-8",
    )


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
