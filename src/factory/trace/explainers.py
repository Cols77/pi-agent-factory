"""Deprecated compatibility re-export for :mod:`coherence.trace.explainers`."""

import warnings

from coherence.trace.explainers import *  # noqa: F403


warnings.warn(
    "factory.trace.explainers is deprecated; use coherence.trace.explainers",
    DeprecationWarning,
    stacklevel=2,
)
