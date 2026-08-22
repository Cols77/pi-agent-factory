from __future__ import annotations

import warnings

from substrate.codemap.model import CodeIndex, IndexFile, IndexSignature

warnings.warn(
    "factory.codeindex.model is deprecated; import substrate.codemap.model",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["CodeIndex", "IndexFile", "IndexSignature"]
