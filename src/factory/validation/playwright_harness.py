"""Deprecated compatibility shim for :mod:`coherence.measurement.playwright_harness`."""

import sys
import warnings

from coherence.measurement import playwright_harness as _canonical
from coherence.measurement.playwright_harness import *  # noqa: F401,F403

warnings.warn(
    "factory.validation.playwright_harness is deprecated; "
    "import coherence.measurement.playwright_harness",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = _canonical.__all__


def __getattr__(name: str):
    return getattr(_canonical, name)


sys.modules[__name__] = _canonical
