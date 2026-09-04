"""Real-git fixtures for the register's ingestion tests.

`coherence.register.ingest` is the one module in the review path that reads
git, so its tests exercise a real temporary repository rather than a fake --
the parsing they pin down (NUL-delimited `git log` records, `git show
--name-only` output) is exactly what a fake would have to invent.
"""

from __future__ import annotations

import subprocess

import pytest


def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def git_repo(tmp_path):
    """A real temporary git repository with an initial commit."""
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "requirements").mkdir()
    _git(repo.parent, "init", "-q", repo.name)
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "README.md").write_text("seed\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "seed")
    return repo


@pytest.fixture
def commit_file(git_repo):
    """Write a file and commit it with the given message; return the sha."""

    def _commit(relpath, content, message):
        target = git_repo / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        _git(git_repo, "add", "-A")
        _git(git_repo, "commit", "-q", "-m", message)
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=git_repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

    return _commit
