"""Deprecated compatibility shim for :mod:`coherence.doctor.write`."""

import sys
import warnings

from coherence.doctor import write as _canonical
from coherence.doctor.write import *  # noqa: F401,F403

warnings.warn(
    "factory.doctor.write is deprecated; import coherence.doctor.write",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = _canonical.__all__


def __getattr__(name: str):
    return getattr(_canonical, name)


sys.modules[__name__] = _canonical

