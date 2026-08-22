"""Deprecated compatibility package for :mod:`coherence.trace`."""

import warnings


warnings.warn(
    "factory.trace is deprecated; use coherence.trace",
    DeprecationWarning,
    stacklevel=2,
)
