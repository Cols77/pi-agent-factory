from __future__ import annotations

import atexit
from collections.abc import Callable
import os
from pathlib import Path
import shutil
import stat
import tempfile
from threading import Lock
from types import TracebackType
import warnings

SKILL_NAMES = [
    "verification-before-completion",
    "context-completeness-audit",
    "test-driven-development",
    "systematic-debugging",
    "receiving-code-review",
    "kb-lookup",
    "code-documentation",
    "requesting-code-review",
    "coding-principles",
    "session-report",
]

_SKILL_SEED: Path | None = None
_SKILL_SEED_LOCK = Lock()


def _ensure_directory(path: Path) -> None:
    if path.is_symlink():
        raise ValueError(f"destination must not be a symlink: {path}")
    if path.exists():
        if not path.is_dir():
            raise NotADirectoryError(f"destination must be a directory: {path}")
        return
    path.mkdir(parents=True)


def _ensure_empty_directory(path: Path) -> None:
    _ensure_directory(path)
    if next(path.iterdir(), None) is not None:
        raise FileExistsError(f"destination must be empty: {path}")


def _copy_seed_children(source: Path, destination: Path) -> None:
    """Copy a seed's immediate children without merging into a destination."""
    _ensure_empty_directory(destination)
    for child in source.iterdir():
        target = destination / child.name
        if target.is_symlink() or target.exists():
            raise FileExistsError(f"destination entry already exists: {target}")
        if child.is_symlink():
            raise ValueError(f"seed entry must not be a symlink: {child}")
        if child.is_dir():
            shutil.copytree(child, target, copy_function=shutil.copyfile)
        elif child.is_file():
            shutil.copyfile(child, target)
        else:
            raise ValueError(f"unsupported seed entry: {child}")


def _remove_readonly(
    func: Callable[[str], object],
    path: str,
    exc_info: tuple[type[BaseException], BaseException, TracebackType | None],
) -> None:
    """Restore write permission before retrying a failed rmtree operation."""
    try:
        mode = os.stat(path, follow_symlinks=False).st_mode
        os.chmod(path, mode | stat.S_IWRITE)
    except OSError as chmod_error:
        raise chmod_error from exc_info[1]
    func(path)


def _remove_tree(path: Path) -> None:
    """Remove a directory, retrying read-only entries without suppressing errors."""
    if not path.exists():
        if path.is_symlink():
            raise ValueError(f"cleanup path must not be a symlink: {path}")
        return
    if path.is_symlink():
        raise ValueError(f"cleanup path must not be a symlink: {path}")
    shutil.rmtree(path, onerror=_remove_readonly)


def _cleanup_skill_seed() -> None:
    global _SKILL_SEED
    with _SKILL_SEED_LOCK:
        seed = _SKILL_SEED
        if seed is None:
            return
        try:
            _remove_tree(seed)
        except Exception as exc:
            warnings.warn(
                f"failed to clean up skill seed {seed}: {exc}",
                RuntimeWarning,
                stacklevel=2,
            )
        else:
            _SKILL_SEED = None


atexit.register(_cleanup_skill_seed)


def _skill_seed() -> Path:
    global _SKILL_SEED
    with _SKILL_SEED_LOCK:
        if _SKILL_SEED is not None:
            return _SKILL_SEED

        seed: Path | None = None
        try:
            seed = Path(tempfile.mkdtemp(prefix="orchestrator-skills-seed-"))
            for name in SKILL_NAMES:
                skill_dir = seed / name
                skill_dir.mkdir()
                (skill_dir / "SKILL.md").write_text(
                    f"---\nname: {name}\ndescription: stub for tests\n---\n\n"
                    f"Stub content for {name}.\n",
                    encoding="utf-8",
                )
        except BaseException as build_error:
            if seed is not None:
                try:
                    _remove_tree(seed)
                except BaseException as cleanup_error:
                    build_error.add_note(
                        f"failed to clean up partial skill seed {seed}: {cleanup_error}"
                    )
            raise

        assert seed is not None
        _SKILL_SEED = seed
        return seed


def write_skill_stubs(root: Path) -> None:
    """Copy static skill stubs into root's isolated ``.pi/skills`` tree.

    The source files are created once per pytest process. Each test still gets
    independent writable copies, so a test cannot mutate another test's skills.
    The destination must be absent or an empty directory; existing contents are
    never merged with the seed.
    """
    _ensure_directory(root)
    _ensure_directory(root / ".pi")
    destination = root / ".pi" / "skills"
    _ensure_empty_directory(destination)
    _copy_seed_children(_skill_seed(), destination)
