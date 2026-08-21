from __future__ import annotations

import warnings

from substrate.codemap.cli import main

warnings.warn(
    "factory.codeindex.cli is deprecated; import substrate.codemap.cli",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["main"]
