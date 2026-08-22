from __future__ import annotations

import warnings

from substrate.codemap.build import (
    INDEX_DIR,
    LATEST_STEM,
    build_index,
    discover_source_files,
    file_signatures,
    fingerprint_for,
    index_dir,
    is_fresh,
    profile_source_dirs,
    render_index_slice,
)

warnings.warn(
    "factory.codeindex.build is deprecated; import substrate.codemap.build",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "INDEX_DIR",
    "LATEST_STEM",
    "build_index",
    "discover_source_files",
    "file_signatures",
    "fingerprint_for",
    "index_dir",
    "is_fresh",
    "profile_source_dirs",
    "render_index_slice",
]
