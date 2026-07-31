import pytest
from factory.orchestrator.ledger import load_tasks
from factory.polish.finding import Finding
from factory.polish.routing import route

pytestmark = pytest.mark.unit


def test_route_creates_parseable_task_with_sr(tmp_path):
    tasks = tmp_path / "tasks"
    f = Finding(usecase="shark_warning", description="drone ignored out-of-zone swimmer",
                snapshot={"t": 20.0}, sr="SR-001", artifacts=["shot.png"])
    path = route(f, tasks)
    assert path.name == "T-001.md"
    t = load_tasks(tasks)[0]
    assert t.id == "T-001"
    assert "shark_warning" in t.title
    assert t.status == "todo"
    assert t.satisfies == ["SR-001"]
    assert any("no longer exhibits" in d for d in t.dod)
    assert "drone ignored out-of-zone swimmer" in t.body
    assert '"t": 20.0' in t.body  # snapshot embedded


def test_route_without_sr_has_empty_satisfies(tmp_path):
    tasks = tmp_path / "tasks"
    route(Finding("uc", "first"), tasks)
    p2 = route(Finding("uc", "second"), tasks)
    assert p2.name == "T-002.md"           # sequential ids
    assert load_tasks(tasks)[0].satisfies == []


def test_route_coexists_with_existing_task_ids(tmp_path):
    tasks = tmp_path / "tasks"
    tasks.mkdir()
    (tasks / "T-041.md").write_text(
        "---\nid: T-041\ntitle: t\nstatus: todo\ndod:\n  - x\n---\nbody\n", encoding="utf-8"
    )
    path = route(Finding("uc", "d"), tasks)
    assert path.name == "T-042.md"
