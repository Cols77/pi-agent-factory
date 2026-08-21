"""Deprecated compatibility re-export for :mod:`coherence.trace.model`."""

import warnings

from coherence.trace.model import *  # noqa: F403


warnings.warn(
    "factory.trace.model is deprecated; use coherence.trace.model",
    DeprecationWarning,
    stacklevel=2,
)
