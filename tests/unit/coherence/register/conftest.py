"""Real-git fixtures for the register's ingestion tests.

`coherence.register.ingest` is the one module in the review path that reads
git, so its tests exercise a real temporary repository rather than a fake --
the parsing they pin down (NUL-delimited `git log` records, `git show
--name-only` output) is exactly what a fake would have to invent.
"""

from __future__ import annotations

import subprocess

import frontmatter as fm
import pytest

from coherence.register.ingest import ingest


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


def _seed_claimed_repo(repo, commit_file, implemented_by):
    """A repository whose evidence store carries one ingested claim.

    Two commits, deliberately separate: the requirement file lands first with
    NO `SR:` trailer, so the only path the claim denominator attributes to
    SR-500 is `src/claimed.py`. Committing both together would put
    `requirements/SR-500.md` in the same claim and make every assertion about
    the offender list a two-item accident.
    """
    (repo / ".factory").mkdir(exist_ok=True)
    meta = {
        "id": "SR-500",
        "title": "t",
        "statement": "s",
        "domain": "behavioral",
        "implemented_by": implemented_by,
        "verified_by": [],
    }
    commit_file(
        "requirements/SR-500.md", fm.dumps(fm.Post("body", **meta)), "docs: seed SR-500"
    )
    commit_file("src/claimed.py", "def claimed():\n    return 1\n", "feat: claimed\n\nSR: SR-500")
    ingest(repo)
    return repo


@pytest.fixture
def claims_repo(git_repo, commit_file):
    """An ingested claim on a path the claiming SR never declares -- exactly
    one `changed_but_undeclared` finding for the gate to block on."""
    return _seed_claimed_repo(git_repo, commit_file, [])


@pytest.fixture
def declared_repo(git_repo, commit_file):
    """The same claim, this time declared -- nothing for the gate to block."""
    return _seed_claimed_repo(
        git_repo,
        commit_file,
        [{"path": "src/claimed.py", "symbol": "claimed:claimed"}],
    )
