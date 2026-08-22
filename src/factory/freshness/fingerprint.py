from __future__ import annotations

import warnings

from substrate.freshness.fingerprint import (
    fingerprint_file,
    fingerprint_git_tree,
    fingerprint_tool,
    fingerprint_value,
    sha256_bytes,
)

warnings.warn(
    "factory.freshness.fingerprint is deprecated; import substrate.freshness.fingerprint",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "sha256_bytes",
    "fingerprint_file",
    "fingerprint_value",
    "fingerprint_tool",
    "fingerprint_git_tree",
]
