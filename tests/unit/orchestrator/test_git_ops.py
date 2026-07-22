from __future__ import annotations

import subprocess
import pytest
from factory.orchestrator.git_ops import FakeGitOps, SubprocessGitOps

pytestmark = pytest.mark.unit


def _init_repo(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "a.txt").write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
    return tmp_path


def test_subprocess_git_ops_head_commit_matches_rev_parse(tmp_path):
    repo = _init_repo(tmp_path)
    expected = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert SubprocessGitOps().head_commit(repo) == expected


def test_subprocess_git_ops_commit_all_returns_false_when_nothing_to_commit(tmp_path):
    repo = _init_repo(tmp_path)
    assert SubprocessGitOps().commit_all(repo, "no-op") is False


def test_subprocess_git_ops_commit_all_commits_uncommitted_changes(tmp_path):
    repo = _init_repo(tmp_path)
    (repo / "a.txt").write_text("two\n", encoding="utf-8")
    before = SubprocessGitOps().head_commit(repo)
    committed = SubprocessGitOps().commit_all(repo, "review: address direct edits during human review")
    assert committed is True
    after = SubprocessGitOps().head_commit(repo)
    assert after != before
    log = subprocess.run(
        ["git", "log", "-1", "--pretty=%s"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert log == "review: address direct edits during human review"


def test_fake_git_ops_records_commit_messages_only_when_has_uncommitted():
    clean = FakeGitOps(head="abc123", has_uncommitted=False)
    assert clean.head_commit(None) == "abc123"
    assert clean.commit_all(None, "msg") is False
    assert clean.commit_messages == []

    dirty = FakeGitOps(head="def456", has_uncommitted=True)
    assert dirty.commit_all(None, "msg") is True
    assert dirty.commit_messages == ["msg"]


def test_subprocess_git_ops_changed_files_lists_modified_paths(tmp_path):
    repo = _init_repo(tmp_path)
    start = SubprocessGitOps().head_commit(repo)
    (repo / "a.txt").write_text("two\n", encoding="utf-8")
    (repo / "b.txt").write_text("new\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "change"], cwd=repo, check=True)

    files = SubprocessGitOps().changed_files(repo, start)

    assert sorted(files) == ["a.txt", "b.txt"]


def test_subprocess_git_ops_changed_files_empty_when_nothing_changed(tmp_path):
    repo = _init_repo(tmp_path)
    start = SubprocessGitOps().head_commit(repo)
    assert SubprocessGitOps().changed_files(repo, start) == []


def test_fake_git_ops_returns_scripted_changed_files():
    fake = FakeGitOps(changed_files_result=["src/a.py", "src/b.py"])
    assert fake.changed_files(None, "abc123") == ["src/a.py", "src/b.py"]


def test_fake_git_ops_changed_files_defaults_to_empty():
    assert FakeGitOps().changed_files(None, "abc123") == []
