"""Deprecated compatibility re-export for :mod:`coherence.trace.graph`."""

import warnings

from substrate.documents.adr import load_adrs  # noqa: F401
from coherence.trace.graph import *  # noqa: F403


warnings.warn(
    "factory.trace.graph is deprecated; use coherence.trace.graph",
    DeprecationWarning,
    stacklevel=2,
)
