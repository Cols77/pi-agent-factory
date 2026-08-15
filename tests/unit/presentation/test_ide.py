"""Task 3 — IDE adapter: sanitized URI, traversal guard, line handling."""
from __future__ import annotations

from pathlib import Path

import pytest

from factory.presentation.ide import build_ide_uri, resolve_repo_file

pytestmark = pytest.mark.unit


def _repo(tmp_path: Path, *, exists: bool = True) -> Path:
    src = tmp_path / "src" / "navigation"
    src.mkdir(parents=True)
    f = src / "reacquisition.py"
    if exists:
        f.write_text("# target_reacquired\n", encoding="utf-8")
    return tmp_path


def test_resolve_repo_file_returns_absolute_path_inside_root(tmp_path):
    repo = _repo(tmp_path)
    abs_path, reason = resolve_repo_file(repo, "src/navigation/reacquisition.py")
    assert reason is None
    assert abs_path.is_absolute()
    assert abs_path == (repo / "src/navigation/reacquisition.py").resolve()


def test_resolve_repo_file_blocks_traversal(tmp_path):
    repo = _repo(tmp_path)
    abs_path, reason = resolve_repo_file(repo, "../../etc/passwd")
    assert abs_path is None
    assert "traversal blocked" in reason


def test_resolve_repo_file_blocks_absolute_path(tmp_path):
    repo = _repo(tmp_path)
    abs_path, reason = resolve_repo_file(repo, str((tmp_path / "x.py").resolve()))
    assert abs_path is None
    assert "absolute" in reason


def test_resolve_repo_file_missing_file(tmp_path):
    repo = _repo(tmp_path, exists=False)
    abs_path, reason = resolve_repo_file(repo, "src/navigation/reacquisition.py")
    assert abs_path is None
    assert "not found" in reason


def test_build_ide_uri_points_at_vscode_file(tmp_path):
    repo = _repo(tmp_path)
    abs_path, _ = resolve_repo_file(repo, "src/navigation/reacquisition.py")
    assert abs_path is not None
    uri = build_ide_uri(abs_path)
    assert uri.startswith("vscode://file/")
    assert str(abs_path).replace("\\", "/") in uri


def test_build_ide_uri_does_not_append_line_when_invalid(tmp_path):
    repo = _repo(tmp_path)
    abs_path, _ = resolve_repo_file(repo, "src/navigation/reacquisition.py")
    assert abs_path is not None
    assert build_ide_uri(abs_path, "abc") == build_ide_uri(abs_path)
    assert build_ide_uri(abs_path, 0) == build_ide_uri(abs_path)


def test_build_ide_uri_appends_line(tmp_path):
    repo = _repo(tmp_path)
    abs_path, _ = resolve_repo_file(repo, "src/navigation/reacquisition.py")
    assert abs_path is not None
    assert build_ide_uri(abs_path, 184).endswith("?line=184")
