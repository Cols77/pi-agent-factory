"""Deprecated compatibility shim for :mod:`coherence.measurement.cli`."""

import sys
import warnings

from coherence.measurement import cli as _canonical
from coherence.measurement.cli import *  # noqa: F401,F403

warnings.warn(
    "factory.validation.cli is deprecated; import coherence.measurement.cli",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = _canonical.__all__


def __getattr__(name: str):
    return getattr(_canonical, name)


sys.modules[__name__] = _canonical
