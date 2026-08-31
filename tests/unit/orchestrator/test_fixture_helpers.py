from __future__ import annotations

import os
from pathlib import Path
import stat
import warnings

import pytest

from . import _repo_fixtures as repo_fixtures
from . import _skill_fixtures as skill_fixtures


@pytest.mark.unit
def test_copy_repo_seed_rejects_prepopulated_destination_without_merging(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    stale = root / "stale.txt"
    stale.write_text("keep", encoding="utf-8")

    monkeypatch.setattr(repo_fixtures, "_seed_for", lambda name: pytest.fail("seed was used"))

    with pytest.raises(FileExistsError, match="empty"):
        repo_fixtures.copy_repo_seed(root, "git_ops")

    assert stale.read_text(encoding="utf-8") == "keep"
    assert not (root / "a.txt").exists()


@pytest.mark.unit
def test_copy_repo_seed_rejects_symlink_destination(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    link = tmp_path / "repo-link"
    try:
        os.symlink(source, link, target_is_directory=True)
    except (NotImplementedError, OSError):
        link.mkdir()
        monkeypatch.setattr(Path, "is_symlink", lambda path: path == link)

    monkeypatch.setattr(repo_fixtures, "_seed_for", lambda name: pytest.fail("seed was used"))

    with pytest.raises(ValueError, match="symlink"):
        repo_fixtures.copy_repo_seed(link, "git_ops")


@pytest.mark.unit
def test_copy_repo_seed_rejects_non_directory_destination(tmp_path, monkeypatch):
    root = tmp_path / "repo-file"
    root.write_text("keep", encoding="utf-8")

    monkeypatch.setattr(repo_fixtures, "_seed_for", lambda name: pytest.fail("seed was used"))

    with pytest.raises(NotADirectoryError, match="directory"):
        repo_fixtures.copy_repo_seed(root, "git_ops")

    assert root.read_text(encoding="utf-8") == "keep"


@pytest.mark.unit
def test_write_skill_stubs_rejects_prepopulated_destination_without_merging(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    destination = root / ".pi" / "skills"
    destination.mkdir(parents=True)
    stale = destination / "stale"
    stale.write_text("keep", encoding="utf-8")
    monkeypatch.setattr(skill_fixtures, "_skill_seed", lambda: pytest.fail("seed was used"))

    with pytest.raises(FileExistsError, match="empty"):
        skill_fixtures.write_skill_stubs(root)

    assert stale.read_text(encoding="utf-8") == "keep"
    assert not (destination / skill_fixtures.SKILL_NAMES[0]).exists()


@pytest.mark.unit
def test_repo_seed_build_failure_removes_partial_tree(tmp_path, monkeypatch):
    seed = tmp_path / "repo-seed"
    monkeypatch.setattr(repo_fixtures.tempfile, "mkdtemp", lambda **kwargs: str(seed))
    monkeypatch.setattr(
        repo_fixtures,
        "write_skill_stubs",
        lambda root: (_ for _ in ()).throw(RuntimeError("skill setup failed")),
    )
    spec = repo_fixtures._RepoSpec(
        files=(("src/x.py", "x = 1\n"),),
        commit_message="init",
        user_email="t@example.com",
        user_name="t",
        include_skill_stubs=True,
    )

    with pytest.raises(RuntimeError, match="skill setup failed"):
        repo_fixtures._build_seed("partial", spec)

    assert not seed.exists()


@pytest.mark.unit
def test_skill_seed_build_failure_removes_partial_tree(tmp_path, monkeypatch):
    seed = tmp_path / "skill-seed"

    def fake_mkdtemp(**kwargs):
        seed.mkdir()
        return str(seed)

    monkeypatch.setattr(skill_fixtures.tempfile, "mkdtemp", fake_mkdtemp)
    original_write_text = Path.write_text
    writes = 0

    def fail_after_first_write(self, data, encoding=None, errors=None, newline=None):
        nonlocal writes
        result = original_write_text(self, data, encoding=encoding, errors=errors, newline=newline)
        writes += 1
        if writes == 1:
            raise RuntimeError("skill write failed")
        return result

    monkeypatch.setattr(Path, "write_text", fail_after_first_write)
    monkeypatch.setattr(skill_fixtures, "_SKILL_SEED", None)

    with pytest.raises(RuntimeError, match="skill write failed"):
        skill_fixtures._skill_seed()

    assert not seed.exists()
    assert skill_fixtures._SKILL_SEED is None


@pytest.mark.unit
def test_cleanup_seed_dirs_continues_and_reports_failures(monkeypatch):
    first = Path("first-seed")
    second = Path("second-seed")
    monkeypatch.setattr(repo_fixtures, "_SEED_DIRS", {"first": first, "second": second})
    removed = []
    reports = []

    def remove(path):
        if path == first:
            raise OSError("first cleanup failed")
        removed.append(path)

    monkeypatch.setattr(repo_fixtures, "_remove_tree", remove)
    monkeypatch.setattr(warnings, "warn", lambda message, *args, **kwargs: reports.append(str(message)))

    repo_fixtures._cleanup_seed_dirs()

    assert removed == [second]
    assert len(reports) == 1
    assert "first-seed" in reports[0]
    assert "first cleanup failed" in reports[0]


@pytest.mark.unit
def test_remove_tree_passes_readonly_retry_handler_without_ignore_errors(tmp_path, monkeypatch):
    root = tmp_path / "seed"
    root.mkdir()
    captured = {}

    def fake_rmtree(path, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(skill_fixtures.shutil, "rmtree", fake_rmtree)
    skill_fixtures._remove_tree(root)

    assert "ignore_errors" not in captured
    assert captured["onerror"] is skill_fixtures._remove_readonly


@pytest.mark.unit
def test_readonly_retry_handler_restores_write_permission_before_retry(tmp_path):
    target = tmp_path / "readonly.txt"
    target.write_text("content", encoding="utf-8")
    target.chmod(stat.S_IREAD)
    observed_modes = []

    def remove(path):
        observed_modes.append(Path(path).stat().st_mode)
        Path(path).unlink()

    skill_fixtures._remove_readonly(remove, str(target), (PermissionError, PermissionError("denied"), None))

    assert observed_modes[0] & stat.S_IWRITE
    assert not target.exists()


@pytest.mark.unit
def test_repo_seed_cleanup_failure_does_not_hide_build_failure(tmp_path, monkeypatch):
    seed = tmp_path / "repo-seed"
    monkeypatch.setattr(repo_fixtures.tempfile, "mkdtemp", lambda **kwargs: str(seed))
    monkeypatch.setattr(
        repo_fixtures,
        "write_skill_stubs",
        lambda root: (_ for _ in ()).throw(RuntimeError("build failed")),
    )
    monkeypatch.setattr(
        repo_fixtures,
        "_remove_tree",
        lambda path: (_ for _ in ()).throw(OSError("cleanup failed")),
    )
    spec = repo_fixtures._RepoSpec(
        files=(("src/x.py", "x = 1\n"),),
        commit_message="init",
        user_email="t@example.com",
        user_name="t",
        include_skill_stubs=True,
    )

    with pytest.raises(RuntimeError, match="build failed") as exc_info:
        repo_fixtures._build_seed("partial", spec)

    assert any("cleanup failed" in note for note in exc_info.value.__notes__)
