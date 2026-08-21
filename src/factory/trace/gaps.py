"""Deprecated compatibility re-export for :mod:`coherence.trace.gaps`."""

import warnings

from coherence.trace.gaps import *  # noqa: F403


warnings.warn(
    "factory.trace.gaps is deprecated; use coherence.trace.gaps",
    DeprecationWarning,
    stacklevel=2,
)
