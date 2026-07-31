import pytest
from factory.orchestrator.ledger import load_tasks

pytestmark = pytest.mark.unit


def _write(tmp_path, name, extra=""):
    (tmp_path / name).write_text(
        f"---\nid: {name[:-3]}\ntitle: t\nstatus: todo\ndod:\n  - x\n{extra}---\nbody\n",
        encoding="utf-8",
    )


def test_satisfies_absent_defaults_empty(tmp_path):
    _write(tmp_path, "T-001.md")
    assert load_tasks(tmp_path)[0].satisfies == []


def test_satisfies_list(tmp_path):
    _write(tmp_path, "T-002.md", extra="satisfies:\n  - SR-001\n  - SR-002\n")
    assert load_tasks(tmp_path)[0].satisfies == ["SR-001", "SR-002"]


def test_satisfies_scalar_wrapped(tmp_path):
    _write(tmp_path, "T-003.md", extra="satisfies: SR-001\n")
    assert load_tasks(tmp_path)[0].satisfies == ["SR-001"]
