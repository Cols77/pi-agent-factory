from __future__ import annotations

import warnings

from substrate.codemap.store import ensure_fresh, load_latest, save_index

warnings.warn(
    "factory.codeindex.store is deprecated; import substrate.codemap.store",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["ensure_fresh", "load_latest", "save_index"]
