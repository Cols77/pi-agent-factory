from __future__ import annotations

import warnings

from substrate.codemap.sigs import detect_language, extract_signatures, preferred_engine

warnings.warn(
    "factory.codeindex.sigs is deprecated; import substrate.codemap.sigs",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["detect_language", "extract_signatures", "preferred_engine"]
