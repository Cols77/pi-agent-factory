"""Deprecated compatibility re-export for :mod:`coherence.trace.propose`."""

import warnings

from coherence.trace.propose import *  # noqa: F403


warnings.warn(
    "factory.trace.propose is deprecated; use coherence.trace.propose",
    DeprecationWarning,
    stacklevel=2,
)
