from __future__ import annotations

import base64
import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Protocol

# The factory's own per-run output. These live inside the target repo and are
# untracked there (a target repo does not inherit the factory's .gitignore), so
# enumerating untracked files picked them up and `write_patch` inlined their
# full contents, base64-encoded, into the checkpoint sidecar it was writing --
# into sessions/.factory-runs/ itself. Each checkpoint therefore embedded every
# earlier sidecar: 768MB -> 1.8GB -> 4.3GB -> 10GB across four checkpoints in
# cool_physical_ai_project, then MemoryError in json.dumps. The run died at its
# first execution.record, before finalize_run_evidence, which is why no
# evidence manifest was ever written in any repo.
#
# These are excluded by path rather than by .gitignore because the fix must
# hold even in a target repo that has not been told to ignore them.
_FACTORY_SCRATCH_PREFIXES = (
    "sessions/.factory-runs/",
    "sessions/.factory-transcripts/",
    ".factory/artifacts/",
)


def _is_factory_scratch(relative: str) -> bool:
    """True for the factory's own run output, which is never a work product."""
    normalized = relative.replace("\\", "/")
    return normalized.startswith(_FACTORY_SCRATCH_PREFIXES)


_IGNORE_BLOCK_HEADER = "# factory scratch (written by the orchestrator; never a work product)"


def ensure_factory_ignores(repo_root: Path) -> bool:
    """Ensure the target repo ignores the factory's own run output.

    A target repo does not inherit the factory's .gitignore, so its scratch
    directories show up as untracked work there. That is more than cosmetic:
    `commit_all` runs `git add -A`, so unignored run output can be committed
    into the user's repository.

    Idempotent and additive -- it appends a marked block only when an entry is
    missing, and never rewrites or reorders what is already there. Returns True
    when the file was modified.
    """
    gitignore = repo_root / ".gitignore"
    try:
        existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    except OSError:
        return False
    present = {line.strip() for line in existing.splitlines()}
    missing = [p for p in _FACTORY_SCRATCH_PREFIXES if p not in present]
    if not missing:
        return False
    block = "\n".join([_IGNORE_BLOCK_HEADER, *missing])
    prefix = "" if existing == "" or existing.endswith("\n") else "\n"
    try:
        gitignore.write_text(f"{existing}{prefix}{block}\n", encoding="utf-8")
    except OSError:
        return False
    return True


class GitOps(Protocol):
    def head_commit(self, repo_root: Path) -> str: ...
    def commit_exists(self, repo_root: Path, commit: str) -> bool: ...
    def commit_all(self, repo_root: Path, message: str) -> bool: ...
    def commit_paths(self, repo_root: Path, paths: list[Path], message: str) -> bool: ...
    def changed_files(self, repo_root: Path, start_commit: str) -> list[str]: ...
    def changed_files_between(
        self, repo_root: Path, start_commit: str, end_commit: str
    ) -> list[str]: ...
    def binary_diff(
        self, repo_root: Path, start_commit: str, end_commit: str | None = None
    ) -> bytes: ...
    def worktree_fingerprint(self, repo_root: Path, start_commit: str) -> str: ...
    def write_patch(self, repo_root: Path, start_commit: str, path: Path) -> Path: ...
    def check_patch(self, repo_root: Path, path: Path) -> bool: ...
    def restore_patch(self, repo_root: Path, path: Path) -> None: ...


class SubprocessGitOps:
    def head_commit(self, repo_root: Path) -> str:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo_root, capture_output=True, text=True, check=True,
        )
        return result.stdout.strip()

    def commit_exists(self, repo_root: Path, commit: str) -> bool:
        result = subprocess.run(
            ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
            cwd=repo_root,
            capture_output=True,
        )
        return result.returncode == 0

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

    def _untracked_files(self, repo_root: Path) -> list[str]:
        result = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "-z"],
            cwd=repo_root,
            capture_output=True,
            check=True,
        )
        files = []
        for raw in result.stdout.split(b"\0"):
            if not raw:
                continue
            relative = os.fsdecode(raw)
            # git lists an embedded repository / nested git worktree as a single
            # untracked *directory* entry. It cannot be snapshotted as a file and
            # read_bytes() would raise PermissionError (e.g. on Windows). Skip any
            # non-file entry so patch/fingerprint recording never crashes on it.
            if (repo_root / relative).is_dir():
                continue
            if _is_factory_scratch(relative):
                continue
            files.append(relative)
        return sorted(files)

    def worktree_fingerprint(self, repo_root: Path, start_commit: str) -> str:
        digest = hashlib.sha256()
        patch = self.binary_diff(repo_root, start_commit)
        digest.update(len(patch).to_bytes(8, "big"))
        digest.update(patch)
        for relative in self._untracked_files(repo_root):
            name = relative.encode("utf-8", errors="surrogateescape")
            data = (repo_root / relative).read_bytes()
            digest.update(len(name).to_bytes(8, "big"))
            digest.update(name)
            digest.update(len(data).to_bytes(8, "big"))
            digest.update(data)
        return digest.hexdigest()

    def write_patch(self, repo_root: Path, start_commit: str, path: Path) -> Path:
        try:
            path.resolve().relative_to(repo_root.resolve())
        except ValueError as exc:
            raise ValueError("checkpoint patch must be inside the repository") from exc
        # Enumerate before creating the checkpoint itself, which may live inside
        # a repository whose test fixture has not configured ignore rules.
        untracked_files = self._untracked_files(repo_root)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_bytes(self.binary_diff(repo_root, start_commit))
        tmp.replace(path)
        untracked = [
            {
                "path": relative,
                "data": base64.b64encode((repo_root / relative).read_bytes()).decode("ascii"),
                "mode": stat.S_IMODE((repo_root / relative).stat().st_mode),
            }
            for relative in untracked_files
        ]
        sidecar = path.with_suffix(path.suffix + ".untracked.json")
        sidecar_tmp = sidecar.with_name(sidecar.name + ".tmp")
        sidecar_tmp.write_text(json.dumps({"files": untracked}, indent=2), encoding="utf-8")
        sidecar_tmp.replace(sidecar)
        return path

    def check_patch(self, repo_root: Path, path: Path) -> bool:
        if not path.exists():
            return False
        result = subprocess.run(
            ["git", "apply", "--check", "--binary", str(path.resolve())],
            cwd=repo_root,
            capture_output=True,
        )
        return result.returncode == 0

    def restore_patch(self, repo_root: Path, path: Path) -> None:
        subprocess.run(
            ["git", "apply", "--binary", str(path.resolve())],
            cwd=repo_root,
            capture_output=True,
            check=True,
        )
        sidecar = path.with_suffix(path.suffix + ".untracked.json")
        if not sidecar.exists():
            return
        value = json.loads(sidecar.read_text(encoding="utf-8"))
        for item in value.get("files", []):
            relative = item["path"]
            target = (repo_root / relative).resolve()
            try:
                target.relative_to(repo_root.resolve())
            except ValueError as exc:
                raise ValueError(f"untracked checkpoint path escapes repository: {relative}") from exc
            data = base64.b64decode(item["data"], validate=True)
            if target.exists() and target.read_bytes() != data:
                raise ValueError(f"untracked checkpoint conflicts with existing file: {relative}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            if isinstance(item.get("mode"), int):
                target.chmod(item["mode"])


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
        self.fingerprint = "f" * 64

    def head_commit(self, repo_root: Path) -> str:
        return self.head

    def commit_exists(self, repo_root: Path, commit: str) -> bool:
        return commit == self.head

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

    def worktree_fingerprint(self, repo_root: Path, start_commit: str) -> str:
        return self.fingerprint

    def write_patch(self, repo_root: Path, start_commit: str, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")
        return path

    def check_patch(self, repo_root: Path, path: Path) -> bool:
        return path.exists()

    def restore_patch(self, repo_root: Path, path: Path) -> None:
        if not path.exists():
            raise FileNotFoundError(path)
