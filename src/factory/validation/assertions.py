"""Deprecated compatibility shim for :mod:`coherence.measurement.assertions`."""

import sys
import warnings

from coherence.measurement import assertions as _canonical
from coherence.measurement.assertions import *  # noqa: F401,F403

warnings.warn(
    "factory.validation.assertions is deprecated; import coherence.measurement.assertions",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = _canonical.__all__


def __getattr__(name: str):
    return getattr(_canonical, name)


sys.modules[__name__] = _canonical
