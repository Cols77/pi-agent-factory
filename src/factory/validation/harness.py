"""Deprecated compatibility shim for :mod:`coherence.measurement.harness`."""

import sys
import warnings

from coherence.measurement import harness as _canonical
from coherence.measurement.harness import *  # noqa: F401,F403

warnings.warn(
    "factory.validation.harness is deprecated; import coherence.measurement.harness",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = _canonical.__all__


def __getattr__(name: str):
    return getattr(_canonical, name)


sys.modules[__name__] = _canonical
