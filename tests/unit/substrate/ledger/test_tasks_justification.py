import pytest
from pathlib import Path

from substrate.ledger.tasks import InvalidJustificationError, Justification, load_tasks

pytestmark = pytest.mark.unit


def _write_task(root: Path, name: str, frontmatter_extra: str) -> Path:
    (root / "tasks").mkdir(exist_ok=True)
    path = root / "tasks" / name
    path.write_text(
        f"---\nid: T-900\ntitle: t\nstatus: todo\ndod:\n- 'done'\n{frontmatter_extra}---\nbody\n",
        encoding="utf-8",
    )
    return path


def test_legacy_satisfies_becomes_typed_justification(tmp_path):
    _write_task(tmp_path, "T-900.md", "satisfies:\n- SR-001\n")
    task = load_tasks(tmp_path / "tasks")[0]
    assert task.satisfies == ["SR-001"]
    assert task.justification == [Justification("satisfies", "SR-001")]


def test_explicit_justification_corrects(tmp_path):
    _write_task(
        tmp_path, "T-900.md", "justification:\n- corrects: NC-0001\n"
    )
    task = load_tasks(tmp_path / "tasks")[0]
    assert task.satisfies == []  # corrects is not a satisfies-kind entry
    assert task.justification == [Justification("corrects", "NC-0001")]


def test_justification_mixed_kinds(tmp_path):
    _write_task(
        tmp_path,
        "T-900.md",
        "justification:\n- satisfies: SR-002\n- mitigates: FR-EXAMPLE\n",
    )
    task = load_tasks(tmp_path / "tasks")[0]
    assert task.satisfies == ["SR-002"]
    assert task.justification == [
        Justification("satisfies", "SR-002"),
        Justification("mitigates", "FR-EXAMPLE"),
    ]


def test_unknown_justification_kind_raises(tmp_path):
    _write_task(tmp_path, "T-900.md", "justification:\n- rejects: SR-001\n")
    with pytest.raises(InvalidJustificationError):
        load_tasks(tmp_path / "tasks")


def test_multi_key_justification_entry_raises(tmp_path):
    _write_task(
        tmp_path, "T-900.md", "justification:\n- satisfies: SR-001\n  corrects: NC-0001\n"
    )
    with pytest.raises(InvalidJustificationError):
        load_tasks(tmp_path / "tasks")
