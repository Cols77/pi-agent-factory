from __future__ import annotations

import warnings

from substrate.validators.schema import SCHEMA_DIR, validate, validate_against

warnings.warn(
    "factory.validation.schema_validator is deprecated; import substrate.validators.schema",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["SCHEMA_DIR", "validate_against", "validate"]
