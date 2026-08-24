"""Deprecated compatibility shim for :mod:`coherence.measurement.report`."""

import sys
import warnings

from coherence.measurement import report as _canonical
from coherence.measurement.report import *  # noqa: F401,F403

warnings.warn(
    "factory.validation.report is deprecated; import coherence.measurement.report",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = _canonical.__all__


def __getattr__(name: str):
    return getattr(_canonical, name)


sys.modules[__name__] = _canonical
