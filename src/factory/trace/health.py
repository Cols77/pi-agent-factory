"""Deprecated compatibility re-export for :mod:`coherence.trace.health`."""

import warnings

from coherence.trace.health import *  # noqa: F403


warnings.warn(
    "factory.trace.health is deprecated; use coherence.trace.health",
    DeprecationWarning,
    stacklevel=2,
)
