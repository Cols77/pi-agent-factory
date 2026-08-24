"""Deprecated compatibility shim for :mod:`coherence.measurement.pipeline`."""

import sys
import warnings

from coherence.measurement import pipeline as _canonical
from coherence.measurement.pipeline import *  # noqa: F401,F403

warnings.warn(
    "factory.validation.pipeline is deprecated; import coherence.measurement.pipeline",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = _canonical.__all__


def __getattr__(name: str):
    return getattr(_canonical, name)


sys.modules[__name__] = _canonical
