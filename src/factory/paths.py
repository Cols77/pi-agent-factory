from __future__ import annotations

import warnings

from substrate.paths import factory_root, factory_skills_dir, scope_guard_extension

warnings.warn(
    "factory.paths is deprecated; import substrate.paths",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["factory_root", "factory_skills_dir", "scope_guard_extension"]
