from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Protocol


class GitOps(Protocol):
    def head_commit(self, repo_root: Path) -> str: ...
    def commit_all(self, repo_root: Path, message: str) -> bool: ...
    def changed_files(self, repo_root: Path, start_commit: str) -> list[str]: ...


class SubprocessGitOps:
    def head_commit(self, repo_root: Path) -> str:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo_root, capture_output=True, text=True, check=True,
        )
        return result.stdout.strip()

    def commit_all(self, repo_root: Path, message: str) -> bool:
        subprocess.run(["git", "add", "-A"], cwd=repo_root, check=True)
        staged = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=repo_root)
        if staged.returncode == 0:
            return False
        subprocess.run(["git", "commit", "-q", "-m", message], cwd=repo_root, check=True)
        return True

    def changed_files(self, repo_root: Path, start_commit: str) -> list[str]:
        result = subprocess.run(
            ["git", "diff", "--name-only", f"{start_commit}..HEAD"],
            cwd=repo_root, capture_output=True, text=True, check=True,
        )
        return [line for line in result.stdout.splitlines() if line.strip()]


class FakeGitOps:
    def __init__(
        self, head: str = "0" * 40, has_uncommitted: bool = False,
        changed_files_result: list[str] | None = None,
    ) -> None:
        self.head = head
        self.has_uncommitted = has_uncommitted
        self.commit_messages: list[str] = []
        self._changed_files_result = changed_files_result or []

    def head_commit(self, repo_root: Path) -> str:
        return self.head

    def commit_all(self, repo_root: Path, message: str) -> bool:
        if self.has_uncommitted:
            self.commit_messages.append(message)
            return True
        return False

    def changed_files(self, repo_root: Path, start_commit: str) -> list[str]:
        return self._changed_files_result
