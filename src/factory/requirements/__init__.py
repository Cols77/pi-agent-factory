"""Deprecated compatibility package for :mod:`coherence.register`."""

import warnings

warnings.warn(
    "factory.requirements is deprecated; use coherence.register",
    DeprecationWarning,
    stacklevel=2,
)
