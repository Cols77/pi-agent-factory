"""Deprecated compatibility shim for :mod:`coherence.measurement.scorer_registry`."""

import sys
import warnings

from coherence.measurement import scorer_registry as _canonical
from coherence.measurement.scorer_registry import *  # noqa: F401,F403

warnings.warn(
    "factory.validation.scorer_registry is deprecated; import coherence.measurement.scorer_registry",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = _canonical.__all__


def __getattr__(name: str):
    return getattr(_canonical, name)


sys.modules[__name__] = _canonical
