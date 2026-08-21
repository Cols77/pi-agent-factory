"""Deprecated compatibility re-export for :mod:`coherence.trace.write`."""

import warnings

from coherence.trace.write import *  # noqa: F403


warnings.warn(
    "factory.trace.write is deprecated; use coherence.trace.write",
    DeprecationWarning,
    stacklevel=2,
)
