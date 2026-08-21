from __future__ import annotations

import warnings

from substrate.freshness.evaluate import compare_dependencies

warnings.warn(
    "factory.freshness.evaluate is deprecated; import substrate.freshness.evaluate",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["compare_dependencies"]
