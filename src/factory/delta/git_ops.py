"""Read-only git queries for the context delta (Inc 7 Task 2).

Every function degrades deterministically instead of raising: a git failure
or an unresolvable commit yields `None`/`[]`/`False`. The delta pipeline
composes these; it never invents history.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

PathSpec = str | Path


def _posix(path: PathSpec) -> str:
    """Git wants forward-slash paths everywhere; Path on Windows yields backslashes."""
    return path.as_posix() if isinstance(path, Path) else path


def _run(root: Path, *args: str) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None


def head_commit(root: Path) -> str | None:
    """Current HEAD sha, or None when git cannot answer."""
    result = _run(root, "rev-parse", "HEAD")
    return result.stdout.strip() if result is not None else None


def commit_iso(root: Path, commit: str) -> str | None:
    """ISO-8601 author date of a commit, or None (degrade on git failure)."""
    result = _run(root, "show", "-s", "--format=%aI", commit)
    return result.stdout.strip() if result is not None else None


def is_ancestor(root: Path, ancestor: str, descendant: str) -> bool:
    """True iff `ancestor` is an ancestor of (or equal to) `descendant`."""
    result = _run(root, "merge-base", "--is-ancestor", ancestor, descendant)
    return result is not None and result.returncode == 0


def commit_exists(root: Path, commit: str) -> bool:
    """True iff `commit` resolves in the repo."""
    return _run(root, "rev-parse", "--verify", "--quiet", f"{commit}^{{commit}}") is not None


def changed_files_since(root: Path, since: str, paths: list[PathSpec]) -> list[str]:
    """Files (repo-relative) changed in `since..HEAD`, restricted to `paths`."""
    if not paths:
        return []
    result = _run(
        root, "log", f"{since}..HEAD", "--name-only", "--format=", "--", *[_posix(p) for p in paths]
    )
    if result is None:
        return []
    return sorted({line for line in result.stdout.splitlines() if line})


def added_files_since(root: Path, since: str, paths: list[PathSpec]) -> list[str]:
    """Files added in `since..HEAD`, restricted to `paths` (A-only diff)."""
    if not paths:
        return []
    result = _run(
        root,
        "log",
        f"{since}..HEAD",
        "--diff-filter=A",
        "--name-only",
        "--format=",
        "--",
        *[_posix(p) for p in paths],
    )
    if result is None:
        return []
    return sorted({line for line in result.stdout.splitlines() if line})


def merge_subjects_since(root: Path, since: str, paths: list[PathSpec]) -> list[str]:
    """Merge-commit subjects in `since..HEAD` touching `paths`, newest last."""
    if not paths:
        return []
    result = _run(
        root, "log", f"{since}..HEAD", "--first-parent", "--merges", "--format=%s", "--", *[_posix(p) for p in paths]
    )
    if result is None:
        return []
    return [line for line in reversed(result.stdout.splitlines()) if line]


def read_file_at(root: Path, commit: str, relpath: PathSpec) -> str | None:
    """File content at a commit, or None when missing/unreadable."""
    result = _run(root, "show", f"{commit}:{_posix(relpath)}")
    return result.stdout if result is not None else None
