"""Where the factory's own assets live.

The factory runs against OTHER repos (polish sessions, cross-repo factory-run),
so anything that ships with the factory -- role skills, the scope-guard pi
extension -- must resolve from here and never from the repo being worked on.
Deriving these from the target repo has now caused three separate silent
failures, so they live in one place.
"""
from __future__ import annotations

from pathlib import Path


def factory_root() -> Path:
    """The factory checkout's root."""
    # <factory_root>/src/factory/paths.py -> <factory_root>
    return Path(__file__).resolve().parents[2]


def factory_skills_dir() -> Path:
    """The factory's vendored role skills (.pi/skills)."""
    return factory_root() / ".pi" / "skills"


def scope_guard_extension() -> Path:
    """The scope-guard pi extension the agent roles are launched with."""
    return factory_root() / "pi-ext" / "scope-guard" / "src" / "index.ts"
