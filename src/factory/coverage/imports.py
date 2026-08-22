# src/factory/coverage/imports.py
from __future__ import annotations

import warnings

from substrate.codemap.imports import (
    ImportClosure,
    ImportEdge,
    OverlapResult,
    build_import_closure,
    compute_overlap,
    transitive_imports,
)

warnings.warn(
    "factory.coverage.imports is deprecated; import substrate.codemap.imports",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "ImportClosure",
    "ImportEdge",
    "OverlapResult",
    "build_import_closure",
    "compute_overlap",
    "transitive_imports",
]
