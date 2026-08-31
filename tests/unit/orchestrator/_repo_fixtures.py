from __future__ import annotations

import atexit
from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
import tempfile
from threading import Lock

from ._skill_fixtures import write_skill_stubs


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
    for seed in _SEED_DIRS.values():
        shutil.rmtree(seed, ignore_errors=True)


atexit.register(_cleanup_seed_dirs)


def _build_seed(name: str, spec: _RepoSpec) -> Path:
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
    run-state files without affecting another test or the seed.
    """
    root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        _seed_for(name),
        root,
        copy_function=shutil.copyfile,
        dirs_exist_ok=True,
    )
    return root
