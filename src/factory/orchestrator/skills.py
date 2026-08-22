from __future__ import annotations

import warnings

from substrate.agents.skills import load_skill_block
from substrate.paths import factory_skills_dir

warnings.warn(
    "factory.orchestrator.skills is deprecated; import substrate.agents.skills "
    "and substrate.paths",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["factory_skills_dir", "load_skill_block"]
