from __future__ import annotations

import warnings

from substrate.validators.session import validate_session

warnings.warn(
    "factory.validation.session_validator is deprecated; import substrate.validators.session",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["validate_session"]
