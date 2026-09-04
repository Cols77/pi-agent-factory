"""Neutral, read-only git commit-range reads.

Lives in substrate because both layers need it and neither may depend on the
other: `factory.orchestrator.git_ops.SubprocessGitOps` exposes these through
the `GitOps` protocol (its methods delegate straight here, so there is exactly
one implementation of each command), and `coherence.register.ingest` consumes
them through the `CommitReader` protocol below without importing `factory.*` --
a layering `tests/unit/requirements/test_coherence_parity.py` enforces.

Read-only by construction: nothing here writes, stages, or commits.
`substrate.freshness.fingerprint.fingerprint_git_tree` already established
this shape of neutral git read.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Protocol


class CommitReader(Protocol):
    """The git reads commit-claim ingestion needs, and nothing more.

    Structural, so `factory.orchestrator.git_ops.SubprocessGitOps` (and its
    `FakeGitOps` twin) satisfy it without inheriting from anything.
    """

    def head_commit(self, repo_root: Path) -> str: ...
    def commits_between(
        self, repo_root: Path, start_commit: str, end_commit: str
    ) -> list[tuple[str, str, str]]: ...
    def changed_files_in_commit(self, repo_root: Path, commit: str) -> list[str]: ...
    def is_ancestor(self, repo_root: Path, commit: str, descendant: str) -> bool: ...
    def root_commit(self, repo_root: Path) -> str | None: ...


def head_commit(repo_root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def commits_between(
    repo_root: Path, start_commit: str, end_commit: str
) -> list[tuple[str, str, str]]:
    """(sha, subject, body) oldest-first for start..end, exclusive of start.

    NUL-delimited fields with a record separator between commits, so a subject
    or body containing any printable character cannot break parsing.
    """
    result = subprocess.run(
        [
            "git", "log", "--reverse", "--format=%H%x00%s%x00%b%x1e",
            f"{start_commit}..{end_commit}",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    commits: list[tuple[str, str, str]] = []
    for raw in result.stdout.split("\x1e"):
        record = raw.strip("\n")
        if not record:
            continue
        sha, _, rest = record.partition("\x00")
        subject, _, body = rest.partition("\x00")
        commits.append((sha, subject, body))
    return commits


def changed_files_in_commit(repo_root: Path, commit: str) -> list[str]:
    result = subprocess.run(
        ["git", "show", "--pretty=format:", "--name-only", commit],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def is_ancestor(repo_root: Path, commit: str, descendant: str) -> bool:
    """True when `commit` is reachable from `descendant`.

    False (not an error) when either ref is unknown: a manifest can name a
    commit that history rewriting or a branch switch has since removed, and the
    caller's job is to report that, not to crash.
    """
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, descendant],
        cwd=repo_root,
        capture_output=True,
    )
    return result.returncode == 0


def root_commit(repo_root: Path) -> str | None:
    """The oldest commit reachable from HEAD, or None in an empty repository."""
    result = subprocess.run(
        ["git", "rev-list", "--max-parents=0", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    shas = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return shas[-1] if shas else None


class SubprocessCommitReader:
    """`CommitReader` over the module functions above."""

    def head_commit(self, repo_root: Path) -> str:
        return head_commit(repo_root)

    def commits_between(
        self, repo_root: Path, start_commit: str, end_commit: str
    ) -> list[tuple[str, str, str]]:
        return commits_between(repo_root, start_commit, end_commit)

    def changed_files_in_commit(self, repo_root: Path, commit: str) -> list[str]:
        return changed_files_in_commit(repo_root, commit)

    def is_ancestor(self, repo_root: Path, commit: str, descendant: str) -> bool:
        return is_ancestor(repo_root, commit, descendant)

    def root_commit(self, repo_root: Path) -> str | None:
        return root_commit(repo_root)


__all__ = [
    "CommitReader",
    "SubprocessCommitReader",
    "changed_files_in_commit",
    "commits_between",
    "head_commit",
    "is_ancestor",
    "root_commit",
]
