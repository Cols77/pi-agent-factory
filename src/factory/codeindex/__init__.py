from __future__ import annotations

import warnings

from substrate.codemap import (
    CodeIndex,
    IndexFile,
    IndexSignature,
    build_index,
    detect_language,
    discover_source_files,
    ensure_fresh,
    extract_signatures,
    file_signatures,
    fingerprint_for,
    is_fresh,
    load_latest,
    preferred_engine,
    render_index_slice,
    save_index,
)

warnings.warn(
    "factory.codeindex is deprecated; import substrate.codemap",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "build_index",
    "discover_source_files",
    "ensure_fresh",
    "file_signatures",
    "fingerprint_for",
    "is_fresh",
    "render_index_slice",
    "load_latest",
    "save_index",
    "CodeIndex",
    "IndexFile",
    "IndexSignature",
    "detect_language",
    "extract_signatures",
    "preferred_engine",
]
