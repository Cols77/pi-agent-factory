"""Deprecated compatibility re-export for :mod:`coherence.trace.validation_status`."""

import warnings

from coherence.trace.validation_status import *  # noqa: F403


warnings.warn(
    "factory.trace.validation_status is deprecated; use coherence.trace.validation_status",
    DeprecationWarning,
    stacklevel=2,
)
