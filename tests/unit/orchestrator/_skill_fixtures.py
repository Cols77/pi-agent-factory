from __future__ import annotations

import atexit
from pathlib import Path
import shutil
import tempfile
from threading import Lock

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


def _cleanup_skill_seed() -> None:
    if _SKILL_SEED is not None:
        shutil.rmtree(_SKILL_SEED, ignore_errors=True)


atexit.register(_cleanup_skill_seed)


def _skill_seed() -> Path:
    global _SKILL_SEED
    with _SKILL_SEED_LOCK:
        if _SKILL_SEED is None:
            seed = Path(tempfile.mkdtemp(prefix="orchestrator-skills-seed-"))
            for name in SKILL_NAMES:
                skill_dir = seed / name
                skill_dir.mkdir()
                (skill_dir / "SKILL.md").write_text(
                    f"---\nname: {name}\ndescription: stub for tests\n---\n\n"
                    f"Stub content for {name}.\n",
                    encoding="utf-8",
                )
            _SKILL_SEED = seed
        return _SKILL_SEED


def write_skill_stubs(root: Path) -> None:
    """Copy the static skill stubs into root's isolated ``.pi/skills`` tree.

    The source files are created once per pytest process. Each test still gets
    independent writable copies, so a test cannot mutate another test's skills.
    """
    shutil.copytree(
        _skill_seed(),
        root / ".pi" / "skills",
        copy_function=shutil.copyfile,
        dirs_exist_ok=True,
    )
