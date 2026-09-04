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

from substrate import vcs

# The factory's own per-run output. These live inside the target repo and are
# untracked there (a target repo does not inherit the factory's .gitignore), so
# enumerating untracked files picked them up and `write_patch` inlined their
# full contents, base64-encoded, into the checkpoint sidecar it was writing --
# into sessions/.factory-runs/ itself. Each checkpoint therefore embedded every
# earlier sidecar: 768MB -> 1.8GB -> 4.3GB -> 10GB across four checkpoints in
# cool_physical_ai_project, then MemoryError in json.dumps. The run died at its
# first execution.record, before finalize_run_evidence, which is why no
# evidence manifest was ever written in any repo. The same writes also flipped
# the worktree fingerprint (sessions/latest.md and sessions/.factory-*.json are
# tracked in a target repo and re-written by the factory mid-run), which is why
# the fingerprint and checkpoint patch must exclude them from the tracked diff
# too, not only from the untracked enumeration.
#
# These are excluded by path rather than by .gitignore because the fix must
# hold even in a target repo that has not been told to ignore them.
_FACTORY_SCRATCH_PREFIXES = (
    "sessions/.factory-runs/",
    "sessions/.factory-transcripts/",
    ".factory/",
    "sessions/latest.md",
    "sessions/.factory-",
)

# Positive pathspecs for `git reset -- <paths>` after `git add -A`: staging the
# whole tree must never sweep the factory's own writes into the run's commit.
_FACTORY_SCRATCH_RESET_PATHSPECS = (
    "sessions/.factory-runs/",
    "sessions/.factory-transcripts/",
    ".factory/",
    "sessions/latest.md",
    "sessions/.factory-*",
)

# Pathspecs (with :(exclude) magic) for the tracked diff the checkpoint patch
# and worktree fingerprint are built from. Factory-owned writes -- whether
# untracked or tracked -- must never flip the fingerprint or bloat the patch.
_FACTORY_SCRATCH_TRACKED_PATHSPECS = (
    ".",
    ":(exclude)sessions/.factory-runs/**",
    ":(exclude)sessions/.factory-transcripts/**",
    ":(exclude).factory/**",
    ":(exclude)sessions/latest.md",
    ":(exclude)sessions/.factory-*",
)

# Windows reserved device names: git's `add -A` refuses to stage a path whose
# basename (sans extension) matches one of these, even when the file is
# gitignored, because the OS intercepts the name as a device handle. A literal
# `nul` file at the repo root broke commit_all in cool_physical_ai_project.
_WINDOWS_RESERVED_NAMES = frozenset(
    {
        "con", "prn", "aux", "nul",
        *(f"com{i}" for i in range(1, 10)),
        *(f"lpt{i}" for i in range(1, 10)),
    }
)

# Untracked files above this size are recorded in the checkpoint sidecar by
# path only (content skipped), so patch recording stays bounded even when a
# run's working tree contains an accidental giant artifact.
MAX_SIDECAR_FILE_BYTES = 64 * 1024 * 1024


class CommitAllError(RuntimeError):
    """git refused to stage the working tree for a reason the run must stop for.

    Distinguished from the ordinary "nothing to commit"/transient failure path
    (which returns False from commit_all) so the runner can surface the refusal
    as a run-blocking error with remediation instead of silently continuing
    without a commit.
    """


def _is_factory_scratch(relative: str) -> bool:
    """True for the factory's own run output, which is never a work product."""
    normalized = relative.replace("\\", "/")
    return normalized.startswith(_FACTORY_SCRATCH_PREFIXES)


def _reserved_name_path(relative: str) -> bool:
    """True when a path's final component is a Windows reserved device name."""
    normalized = relative.replace("\\", "/").rstrip("/")
    stem = normalized.rsplit("/", 1)[-1].split(".", 1)[0].lower()
    return stem in _WINDOWS_RESERVED_NAMES


def _exc_stderr(exc: subprocess.CalledProcessError) -> str:
    if isinstance(exc.stderr, bytes):
        return exc.stderr.decode("utf-8", errors="replace")
    return exc.stderr or ""


def _is_commit_refusal(repo_root: Path, stderr: str) -> bool:
    """True when git's staging failure means the run must stop, not skip.

    A Windows reserved device name (nul, con, ...) or an embedded git
    repository makes `git add -A` fail in a way that no retry will fix and
    that silently committing nothing would mask -- surface it as a
    CommitAllError with remediation instead. Other failures keep the old
    warn-and-continue behavior."""
    if any(
        marker in stderr
        for marker in ("invalid path", "adding files failed", "does not have a commit checked out")
    ):
        return True
    return bool(_find_reserved_name_files(repo_root))


def _find_reserved_name_files(repo_root: Path) -> list[str]:
    """Repo-relative paths whose basename is a Windows reserved device name.

    Tracked, untracked (non-ignored) and ignored paths are all checked: the
    incident file was gitignored yet still made `git add -A` fail on Windows,
    because git's readdir resolves `nul` to a device handle before the ignore
    filter runs."""
    found: list[str] = []
    commands = [
        ["git", "ls-files", "-z"],
        ["git", "ls-files", "--others", "--exclude-standard", "-z"],
        ["git", "status", "--ignored", "--porcelain", "-z"],
    ]
    for command in commands:
        try:
            result = subprocess.run(command, cwd=repo_root, capture_output=True, check=True)
        except subprocess.CalledProcessError:
            continue
        for entry in (result.stdout or b"").split(b"\0"):
            if not entry:
                continue
            text = os.fsdecode(entry)
            if len(text) >= 3 and text[2] == " " and text[0] in " MARC?!":
                text = text[3:]  # porcelain `XY <path>` (or `!! ` for ignored)
            if _reserved_name_path(text):
                found.append(text)
    return sorted(set(found))


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
    # .gitignore lines are glob patterns, not path prefixes: `sessions/.factory-`
    # (no wildcard) would only match a literal name, not `.factory-status.json`.
    ignore_lines = (
        "sessions/.factory-runs/",
        "sessions/.factory-transcripts/",
        ".factory/",
        "sessions/latest.md",
        "sessions/.factory-*",
    )
    missing = [p for p in ignore_lines if p not in present]
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
    def commit_all(
        self, repo_root: Path, message: str, preserve: dict[str, str] | None = None
    ) -> bool: ...
    def dirty_snapshot(self, repo_root: Path) -> dict[str, str]: ...
    def commit_paths(self, repo_root: Path, paths: list[Path], message: str) -> bool: ...
    def changed_files(self, repo_root: Path, start_commit: str) -> list[str]: ...
    def changed_files_between(
        self, repo_root: Path, start_commit: str, end_commit: str
    ) -> list[str]: ...
    def commits_between(
        self, repo_root: Path, start_commit: str, end_commit: str
    ) -> list[tuple[str, str, str]]: ...
    def changed_files_in_commit(self, repo_root: Path, commit: str) -> list[str]: ...
    def is_ancestor(self, repo_root: Path, commit: str, descendant: str) -> bool: ...
    def root_commit(self, repo_root: Path) -> str | None: ...
    def binary_diff(
        self, repo_root: Path, start_commit: str, end_commit: str | None = None
    ) -> bytes: ...
    def worktree_diff(self, repo_root: Path, start_commit: str) -> bytes: ...
    def worktree_fingerprint(
        self, repo_root: Path, start_commit: str, *, include_untracked: bool = True
    ) -> str: ...
    def tracked_fingerprint(self, repo_root: Path, start_commit: str) -> str: ...
    def untracked_snapshot(self, repo_root: Path) -> dict[str, str]: ...
    def read_untracked_sidecar(self, patch_path: Path) -> dict[str, str]: ...
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

    def dirty_snapshot(self, repo_root: Path) -> dict[str, str]:
        """Content hashes of every path already dirty, keyed by repo-relative path.

        Taken at run start so `commit_all` can tell the human's
        work-in-progress from the run's own output. A path is only ever skipped
        when its bytes are unchanged since this snapshot -- see commit_all.
        """
        snapshot: dict[str, str] = {}
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain", "-z", "--untracked-files=all"],
                cwd=repo_root, capture_output=True, check=True,
            )
        except subprocess.CalledProcessError:
            return {}
        for entry in result.stdout.split(b"\0"):
            if len(entry) < 4:
                continue
            relative = os.fsdecode(entry[3:])
            if _is_factory_scratch(relative):
                continue
            path = repo_root / relative
            try:
                snapshot[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError:
                continue
        return snapshot

    def commit_all(
        self, repo_root: Path, message: str, preserve: dict[str, str] | None = None
    ) -> bool:
        # Best-effort: stage and commit the run's working-tree changes. A git
        # failure (e.g. a path git refuses, such as the Windows reserved name
        # `nul` that its readdir can pick up) must NOT crash the orchestrator
        # and strand a human's approve mid-pipeline -- warn and continue
        # without a commit. A refusal that indicates a broken tree (reserved
        # name / embedded repository) raises CommitAllError instead, so the
        # run stops loudly with remediation rather than silently committing
        # nothing.
        #
        # `preserve` maps paths that were ALREADY dirty when the run started to
        # their content hash then. Such a path is left alone only while it
        # still matches that hash: `git add -A` used to sweep the human's
        # work-in-progress into the run's commit (cool_physical_ai_project
        # 3d1ab1b, titled for T-059, carried four unrelated task files someone
        # was mid-edit on). If the agent touched the file as well, it is the
        # run's work no matter who dirtied it first, and skipping it would lose
        # real output -- the hash check is what keeps that distinction honest.
        try:
            unchanged = self._unchanged_since(repo_root, preserve or {})
            subprocess.run(["git", "add", "-A"], cwd=repo_root, check=True)
            for relative in unchanged:
                subprocess.run(
                    ["git", "reset", "-q", "HEAD", "--", relative],
                    cwd=repo_root, capture_output=True, check=False,
                )
            self._unstage_scratch(repo_root)
            staged = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=repo_root)
            if staged.returncode == 0:
                return False
            subprocess.run(["git", "commit", "-q", "-m", message], cwd=repo_root, check=True)
            return True
        except subprocess.CalledProcessError as exc:
            stderr = _exc_stderr(exc)
            if _is_commit_refusal(repo_root, stderr):
                raise CommitAllError(
                    "git refused to stage the working tree; fix before continuing: "
                    + (stderr.strip() or str(exc))
                ) from exc
            print(
                f"factory: warning: commit_all failed, completing without a commit: {exc}",
                file=sys.stderr,
            )
            return False

    def _unstage_scratch(self, repo_root: Path) -> None:
        """Unstage the factory's own run output so it never enters the run's commit.

        Runs after `git add -A` even though ensure_factory_ignores keeps
        untracked scratch out of the index: a target repo may track some of it
        (sessions/latest.md, sessions/.factory-*.json), and `git add -A` would
        otherwise sweep the factory's mid-run rewrites of those files into the
        commit.
        """
        subprocess.run(
            ["git", "reset", "-q", "HEAD", "--", *_FACTORY_SCRATCH_RESET_PATHSPECS],
            cwd=repo_root,
            capture_output=True,
            check=False,
        )

    def _unchanged_since(self, repo_root: Path, preserve: dict[str, str]) -> list[str]:
        """Paths from the snapshot whose bytes the run never touched."""
        unchanged: list[str] = []
        for relative, digest in preserve.items():
            try:
                current = hashlib.sha256((repo_root / relative).read_bytes()).hexdigest()
            except OSError:
                continue
            if current == digest:
                unchanged.append(relative)
        return unchanged

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

    # Commit-range reads (SR-054 commit-claim ingestion). Implemented once in
    # substrate.vcs and exposed here through the GitOps protocol, because
    # coherence.register.ingest also needs them and may not import factory.*
    # (tests/unit/requirements/test_coherence_parity.py). Delegation, not a
    # second convention.
    def commits_between(
        self, repo_root: Path, start_commit: str, end_commit: str
    ) -> list[tuple[str, str, str]]:
        """(sha, subject, body) oldest-first for start..end, exclusive of start."""
        return vcs.commits_between(repo_root, start_commit, end_commit)

    def changed_files_in_commit(self, repo_root: Path, commit: str) -> list[str]:
        return vcs.changed_files_in_commit(repo_root, commit)

    def is_ancestor(self, repo_root: Path, commit: str, descendant: str) -> bool:
        """True when `commit` is reachable from `descendant`."""
        return vcs.is_ancestor(repo_root, commit, descendant)

    def root_commit(self, repo_root: Path) -> str | None:
        """The oldest commit reachable from HEAD, or None in an empty repo."""
        return vcs.root_commit(repo_root)

    def binary_diff(
        self, repo_root: Path, start_commit: str, end_commit: str | None = None
    ) -> bytes:
        args = ["git", "diff", "--binary", start_commit]
        if end_commit is not None:
            args.append(end_commit)
        result = subprocess.run(args, cwd=repo_root, capture_output=True, check=True)
        return result.stdout

    def worktree_diff(self, repo_root: Path, start_commit: str) -> bytes:
        """Tracked diff from start_commit to the working tree, minus factory scratch.

        The checkpoint patch and worktree fingerprint are built from this, so
        the factory's own mid-run rewrites of tracked scratch files
        (sessions/latest.md, sessions/.factory-*.json) can never flip the
        fingerprint or bloat the patch. Evidence's binary_diff is untouched.
        """
        result = subprocess.run(
            [
                "git", "diff", "--binary", start_commit, "--",
                *_FACTORY_SCRATCH_TRACKED_PATHSPECS,
            ],
            cwd=repo_root,
            capture_output=True,
            check=True,
        )
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

    def worktree_fingerprint(
        self, repo_root: Path, start_commit: str, *, include_untracked: bool = True
    ) -> str:
        digest = hashlib.sha256()
        patch = self.worktree_diff(repo_root, start_commit)
        digest.update(len(patch).to_bytes(8, "big"))
        digest.update(patch)
        if include_untracked:
            for relative in self._untracked_files(repo_root):
                name = relative.encode("utf-8", errors="surrogateescape")
                data = (repo_root / relative).read_bytes()
                digest.update(len(name).to_bytes(8, "big"))
                digest.update(name)
                digest.update(len(data).to_bytes(8, "big"))
                digest.update(data)
        return digest.hexdigest()

    def tracked_fingerprint(self, repo_root: Path, start_commit: str) -> str:
        """Fingerprint of the tracked diff only (factory scratch excluded).

        The full worktree fingerprint also folds in every untracked file, so it
        flips on untracked churn that never affects a run's continuation. Resume
        compares this separately: when HEAD matches and the tracked diff still
        matches the checkpoint, the run is resumable even if untracked files
        drifted (they are simply left in place).
        """
        return self.worktree_fingerprint(repo_root, start_commit, include_untracked=False)

    def untracked_snapshot(self, repo_root: Path) -> dict[str, str]:
        """Current untracked non-scratch files as path -> sha256."""
        snapshot: dict[str, str] = {}
        for relative in self._untracked_files(repo_root):
            try:
                snapshot[relative] = hashlib.sha256(
                    (repo_root / relative).read_bytes()
                ).hexdigest()
            except OSError:
                continue
        return snapshot

    def read_untracked_sidecar(self, patch_path: Path) -> dict[str, str]:
        """The checkpoint's recorded untracked files as path -> sha256.

        Tolerant of old sidecars that only stored base64 content: their digest
        is derived from the content. A missing or unreadable sidecar returns an
        empty mapping (no recorded untracked state to compare against)."""
        sidecar = patch_path.with_suffix(patch_path.suffix + ".untracked.json")
        try:
            value = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return {}
        out: dict[str, str] = {}
        for item in value.get("files", []):
            if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                continue
            digest = item.get("sha256")
            if not isinstance(digest, str):
                try:
                    raw = base64.b64decode(item.get("data", ""), validate=True)
                except (TypeError, ValueError):
                    continue
                digest = hashlib.sha256(raw).hexdigest()
            out[item["path"]] = digest
        return out

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
        tmp.write_bytes(self.worktree_diff(repo_root, start_commit))
        tmp.replace(path)

        def items():
            for relative in untracked_files:
                full = repo_root / relative
                size = full.stat().st_size
                if size > MAX_SIDECAR_FILE_BYTES:
                    yield {
                        "path": relative,
                        "size": size,
                        "skipped": True,
                        "reason": "too_large",
                    }
                    continue
                data = full.read_bytes()
                yield {
                    "path": relative,
                    "data": base64.b64encode(data).decode("ascii"),
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "mode": stat.S_IMODE(full.stat().st_mode),
                }

        sidecar = path.with_suffix(path.suffix + ".untracked.json")
        sidecar_tmp = sidecar.with_name(sidecar.name + ".tmp")
        # Stream item-by-item instead of building one giant in-memory string: the
        # old json.dumps of the full list was what hit MemoryError once sidecars
        # began embedding each other (768MB -> 10GB).
        with sidecar_tmp.open("w", encoding="utf-8") as stream:
            stream.write('{"files":[')
            for index, item in enumerate(items()):
                if index:
                    stream.write(",")
                json.dump(item, stream, separators=(",", ":"))
            stream.write("]}")
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
            if item.get("skipped"):
                # Content was too large to record; the file was never removed
                # from the tree, so there is nothing to restore.
                continue
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
        self.tracked_fp = "t" * 64
        self.untracked: dict[str, str] = {}
        self.sidecar: dict[str, str] = {}
        self.worktree_diff_result: bytes = b""
        # Commit-range reads (SR-054 commit-claim ingestion). Empty by default so every
        # existing caller is unaffected; a test that needs a range sets them.
        self.commits: list[tuple[str, str, str]] = []
        self.commit_changed_files: dict[str, list[str]] = {}
        self.ancestor = True

    def head_commit(self, repo_root: Path) -> str:
        return self.head

    def commit_exists(self, repo_root: Path, commit: str) -> bool:
        return commit == self.head

    def dirty_snapshot(self, repo_root: Path) -> dict[str, str]:
        return {}

    def commit_all(
        self, repo_root: Path, message: str, preserve: dict[str, str] | None = None
    ) -> bool:
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

    def commits_between(
        self, repo_root: Path, start_commit: str, end_commit: str
    ) -> list[tuple[str, str, str]]:
        return list(self.commits)

    def changed_files_in_commit(self, repo_root: Path, commit: str) -> list[str]:
        return list(self.commit_changed_files.get(commit, self._changed_files_result))

    def is_ancestor(self, repo_root: Path, commit: str, descendant: str) -> bool:
        return self.ancestor

    def root_commit(self, repo_root: Path) -> str | None:
        return self.head

    def binary_diff(
        self, repo_root: Path, start_commit: str, end_commit: str | None = None
    ) -> bytes:
        return b""

    def worktree_diff(self, repo_root: Path, start_commit: str) -> bytes:
        return self.worktree_diff_result

    def worktree_fingerprint(
        self, repo_root: Path, start_commit: str, *, include_untracked: bool = True
    ) -> str:
        return self.fingerprint

    def tracked_fingerprint(self, repo_root: Path, start_commit: str) -> str:
        return self.tracked_fp

    def untracked_snapshot(self, repo_root: Path) -> dict[str, str]:
        return dict(self.untracked)

    def read_untracked_sidecar(self, patch_path: Path) -> dict[str, str]:
        return dict(self.sidecar)

    def write_patch(self, repo_root: Path, start_commit: str, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")
        return path

    def check_patch(self, repo_root: Path, path: Path) -> bool:
        return path.exists()

    def restore_patch(self, repo_root: Path, path: Path) -> None:
        if not path.exists():
            raise FileNotFoundError(path)
