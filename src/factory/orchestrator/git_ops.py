from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Protocol


class GitOps(Protocol):
    def head_commit(self, repo_root: Path) -> str: ...
    def commit_all(self, repo_root: Path, message: str) -> bool: ...
    def commit_paths(self, repo_root: Path, paths: list[Path], message: str) -> bool: ...
    def changed_files(self, repo_root: Path, start_commit: str) -> list[str]: ...
    def changed_files_between(
        self, repo_root: Path, start_commit: str, end_commit: str
    ) -> list[str]: ...
    def binary_diff(
        self, repo_root: Path, start_commit: str, end_commit: str | None = None
    ) -> bytes: ...


class SubprocessGitOps:
    def head_commit(self, repo_root: Path) -> str:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo_root, capture_output=True, text=True, check=True,
        )
        return result.stdout.strip()

    def commit_all(self, repo_root: Path, message: str) -> bool:
        # Best-effort: stage and commit any working-tree changes. A git failure
        # (e.g. a path git refuses, such as the Windows reserved name `nul` that
        # its readdir can pick up) must NOT crash the orchestrator and strand a
        # human's approve mid-pipeline -- warn and continue without a commit.
        try:
            subprocess.run(["git", "add", "-A"], cwd=repo_root, check=True)
            staged = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=repo_root)
            if staged.returncode == 0:
                return False
            subprocess.run(["git", "commit", "-q", "-m", message], cwd=repo_root, check=True)
            return True
        except subprocess.CalledProcessError as exc:
            print(
                f"factory: warning: commit_all failed, completing without a commit: {exc}",
                file=sys.stderr,
            )
            return False

    def commit_paths(self, repo_root: Path, paths: list[Path], message: str) -> bool:
        root = repo_root.resolve()
        relative: list[str] = []
        for path in paths:
            resolved = path.resolve() if path.is_absolute() else (root / path).resolve()
            try:
                relative.append(resolved.relative_to(root).as_posix())
            except ValueError as exc:
                raise ValueError(f"evidence path is outside repository: {path}") from exc
        if not relative:
            return False
        subprocess.run(["git", "add", "--", *relative], cwd=root, check=True)
        staged = subprocess.run(
            ["git", "diff", "--cached", "--quiet", "--", *relative], cwd=root
        )
        if staged.returncode == 0:
            return False
        subprocess.run(
            ["git", "commit", "-q", "-m", message, "--", *relative], cwd=root, check=True
        )
        return True

    def changed_files(self, repo_root: Path, start_commit: str) -> list[str]:
        # A single-ref diff (`git diff <ref>`, no `..HEAD`) compares that ref
        # to the current working tree, not just to HEAD -- so this picks up
        # both committed changes since start_commit AND uncommitted
        # working-tree changes. Review's changed_files call happens with no
        # commit in between (dev's work may still be uncommitted at that
        # point), so `{start_commit}..HEAD` would silently return an empty
        # list in that case.
        result = subprocess.run(
            ["git", "diff", "--name-only", start_commit],
            cwd=repo_root, capture_output=True, text=True, check=True,
        )
        return [line for line in result.stdout.splitlines() if line.strip()]

    def changed_files_between(
        self, repo_root: Path, start_commit: str, end_commit: str
    ) -> list[str]:
        result = subprocess.run(
            ["git", "diff", "--name-only", start_commit, end_commit],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
        return [line for line in result.stdout.splitlines() if line.strip()]

    def binary_diff(
        self, repo_root: Path, start_commit: str, end_commit: str | None = None
    ) -> bytes:
        args = ["git", "diff", "--binary", start_commit]
        if end_commit is not None:
            args.append(end_commit)
        result = subprocess.run(args, cwd=repo_root, capture_output=True, check=True)
        return result.stdout


class FakeGitOps:
    def __init__(
        self, head: str = "0" * 40, has_uncommitted: bool = False,
        changed_files_result: list[str] | None = None,
    ) -> None:
        self.head = head
        self.has_uncommitted = has_uncommitted
        self.commit_messages: list[str] = []
        self.committed_paths: list[list[Path]] = []
        self._changed_files_result = changed_files_result or []

    def head_commit(self, repo_root: Path) -> str:
        return self.head

    def commit_all(self, repo_root: Path, message: str) -> bool:
        if self.has_uncommitted:
            self.commit_messages.append(message)
            return True
        return False

    def commit_paths(self, repo_root: Path, paths: list[Path], message: str) -> bool:
        self.committed_paths.append(list(paths))
        self.commit_messages.append(message)
        return bool(paths)

    def changed_files(self, repo_root: Path, start_commit: str) -> list[str]:
        return self._changed_files_result

    def changed_files_between(
        self, repo_root: Path, start_commit: str, end_commit: str
    ) -> list[str]:
        return self._changed_files_result

    def binary_diff(
        self, repo_root: Path, start_commit: str, end_commit: str | None = None
    ) -> bytes:
        return b""
