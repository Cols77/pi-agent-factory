"""Deprecated compatibility re-export for :mod:`coherence.trace.cli`."""

import warnings

from coherence.trace.cli import *  # noqa: F403


warnings.warn(
    "factory.trace.cli is deprecated; use coherence.trace.cli",
    DeprecationWarning,
    stacklevel=2,
)
