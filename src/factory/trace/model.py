"""Deprecated compatibility re-export for :mod:`coherence.trace.model`."""

import warnings

from coherence.trace.model import *  # noqa: F403
from coherence.trace.model import _load_post  # noqa: F401


warnings.warn(
    "factory.trace.model is deprecated; use coherence.trace.model",
    DeprecationWarning,
    stacklevel=2,
)
