# src/factory/kb/index.py
from __future__ import annotations

import warnings

from substrate.kb.index import build_index, build_index_payload

warnings.warn(
    "factory.kb.index is deprecated; import substrate.kb.index",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["build_index", "build_index_payload"]
