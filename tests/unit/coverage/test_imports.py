# tests/unit/coverage/test_imports.py
from pathlib import Path

import pytest

from factory.coverage.imports import compute_overlap, transitive_imports

pytestmark = pytest.mark.unit


def _tree(root: Path) -> None:
    """A small project with an absolute import chain."""
    (root / "src").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "src" / "drone").mkdir()
    (root / "src" / "drone" / "__init__.py").write_text("")
    (root / "src" / "drone" / "priority_filter.py").write_text(
        "def preempt():\n    return True\n"
    )
    (root / "tests" / "test_preempt.py").write_text(
        "from drone.priority_filter import preempt\n\ndef test_preempt():\n"
        "    assert preempt()\n"
    )


def test_transitive_imports_reaches_implementation(tmp_path: Path) -> None:
    _tree(tmp_path)
    reached, _ = transitive_imports(tmp_path, tmp_path / "tests" / "test_preempt.py")
    assert (tmp_path / "src" / "drone" / "priority_filter.py") in reached


def test_compute_overlap_true(tmp_path: Path) -> None:
    _tree(tmp_path)
    result = compute_overlap(
        tmp_path, "tests/test_preempt.py", ["src/drone/priority_filter.py"],
    )
    assert result.ok
    assert "src/drone/priority_filter.py" in result.overlap


def test_compute_overlap_false_when_imports_nothing(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_empty.py").write_text(
        "def test_nothing():\n    assert True\n"
    )
    result = compute_overlap(
        tmp_path, "tests/test_empty.py", ["src/drone/priority_filter.py"],
    )
    assert not result.ok
    assert result.overlap == ()


def test_seed_file_is_not_self_overlap(tmp_path: Path) -> None:
    _tree(tmp_path)
    result = compute_overlap(
        tmp_path,
        "tests/test_preempt.py",
        ["src/drone/priority_filter.py", "tests/test_preempt.py"],
    )
    # The test file itself was changed; it must not count as overlap.
    assert result.ok
    assert "tests/test_preempt.py" not in result.overlap
    assert "src/drone/priority_filter.py" in result.overlap


def test_relative_import_resolution(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("")
    (tmp_path / "pkg" / "a.py").write_text("from . import b\n")
    (tmp_path / "pkg" / "b.py").write_text("X = 1\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_rel.py").write_text(
        "from pkg.a import b\n"
    )
    reached, _ = transitive_imports(tmp_path, tmp_path / "tests" / "test_rel.py")
    assert (tmp_path / "pkg" / "a.py") in reached
    assert (tmp_path / "pkg" / "b.py") in reached


def test_node_id_selection_stripped(tmp_path: Path) -> None:
    _tree(tmp_path)
    result = compute_overlap(
        tmp_path, "tests/test_preempt.py::test_preempt",
        ["src/drone/priority_filter.py"],
    )
    assert result.ok


def test_missing_selection_is_honest_false(tmp_path: Path) -> None:
    result = compute_overlap(tmp_path, "tests/does_not_exist.py", ["x.py"])
    assert not result.ok
    assert result.test_source is None


def test_unresolved_imports_are_honest(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_extern.py").write_text(
        "import numpy\n\ndef test():\n    pass\n"
    )
    result = compute_overlap(tmp_path, "tests/test_extern.py", ["x.py"])
    assert not result.ok
    assert "numpy" in result.unresolved
