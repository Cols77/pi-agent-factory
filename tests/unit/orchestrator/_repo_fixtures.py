from __future__ import annotations

import atexit
from dataclasses import dataclass
from pathlib import Path
import subprocess
import tempfile
from threading import Lock
import warnings

from ._skill_fixtures import (
    _copy_seed_children,
    _ensure_empty_directory,
    _remove_tree,
    write_skill_stubs,
)


_RUN_NEXT_TASK = "---\nid: T-001\ntitle: t\nstatus: todo\ndod:\n  - c\n---\nbody\n"


@dataclass(frozen=True)
class _RepoSpec:
    files: tuple[tuple[str, str], ...]
    commit_message: str
    user_email: str
    user_name: str
    include_skill_stubs: bool = False


_REPO_SPECS = {
    "runner": _RepoSpec(
        files=(
            ("tasks/T-001.md", "dod"),
            ("src/x.py", "x = 1\n"),
        ),
        commit_message="init",
        user_email="t@example.com",
        user_name="t",
        include_skill_stubs=True,
    ),
    "run_next": _RepoSpec(
        files=(
            ("tasks/T-001.md", _RUN_NEXT_TASK),
            ("src/x.py", "x = 1\n"),
        ),
        commit_message="init",
        user_email="t@example.com",
        user_name="t",
        include_skill_stubs=True,
    ),
    "evidence": _RepoSpec(
        files=(
            (
                "tasks/T-001-example.md",
                "---\nid: T-001\ntitle: Example\nstatus: todo\ndod:\n  - works\n---\nbody\n",
            ),
        ),
        commit_message="base",
        user_email="test@example.com",
        user_name="Test",
    ),
    "git_ops": _RepoSpec(
        files=(("a.txt", "one\n"),),
        commit_message="init",
        user_email="t@example.com",
        user_name="t",
    ),
}

_SEED_DIRS: dict[str, Path] = {}
_SEED_LOCK = Lock()


def _cleanup_seed_dirs() -> None:
    failures: list[tuple[str, Path, Exception]] = []
    with _SEED_LOCK:
        for name, seed in tuple(_SEED_DIRS.items()):
            try:
                _remove_tree(seed)
            except Exception as exc:
                failures.append((name, seed, exc))
            else:
                del _SEED_DIRS[name]

    if failures:
        details = "; ".join(f"{name} ({seed}): {exc}" for name, seed, exc in failures)
        warnings.warn(
            f"failed to clean up repository seed(s): {details}",
            RuntimeWarning,
            stacklevel=2,
        )


atexit.register(_cleanup_seed_dirs)


def _build_seed(name: str, spec: _RepoSpec) -> Path:
    seed: Path | None = None
    try:
        seed = Path(tempfile.mkdtemp(prefix=f"orchestrator-{name}-seed-"))
        for relative_path, content in spec.files:
            path = seed / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        if spec.include_skill_stubs:
            write_skill_stubs(seed)

        subprocess.run(["git", "init", "-q"], cwd=seed, check=True)
        subprocess.run(["git", "config", "user.email", spec.user_email], cwd=seed, check=True)
        subprocess.run(["git", "config", "user.name", spec.user_name], cwd=seed, check=True)
        subprocess.run(["git", "add", "-A"], cwd=seed, check=True)
        subprocess.run(["git", "commit", "-q", "-m", spec.commit_message], cwd=seed, check=True)
        return seed
    except BaseException as build_error:
        if seed is not None:
            try:
                _remove_tree(seed)
            except BaseException as cleanup_error:
                build_error.add_note(
                    f"failed to clean up partial repository seed {seed}: {cleanup_error}"
                )
        raise


def _seed_for(name: str) -> Path:
    try:
        spec = _REPO_SPECS[name]
    except KeyError as exc:
        raise ValueError(f"unknown orchestrator repository fixture: {name}") from exc

    with _SEED_LOCK:
        seed = _SEED_DIRS.get(name)
        if seed is None:
            seed = _build_seed(name, spec)
            _SEED_DIRS[name] = seed
        return seed


def copy_repo_seed(root: Path, name: str) -> Path:
    """Copy an immutable baseline repository into an isolated test root.

    The seed is prepared once per pytest process, but every caller receives a
    complete copy, including an independent ``.git`` directory. Tests remain
    free to mutate their checkout, run real Git commands, and create their own
    run-state files without affecting another test or the seed. The destination
    must be absent or an empty directory; existing contents are never merged.
    """
    _ensure_empty_directory(root)
    _copy_seed_children(_seed_for(name), root)
    return root
