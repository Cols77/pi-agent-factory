from __future__ import annotations

import warnings

from substrate.validators.kb import parse_entry, validate_entry, validate_entry_file

warnings.warn(
    "factory.validation.kb_validator is deprecated; import substrate.validators.kb",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["parse_entry", "validate_entry", "validate_entry_file"]
