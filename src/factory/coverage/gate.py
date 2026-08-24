"""Deprecated compatibility shim for :mod:`coherence.audit.gate`."""

import warnings
import sys

from coherence.audit import gate as _canonical
from coherence.audit.gate import *  # noqa: F401,F403

warnings.warn(
    "factory.coverage.gate is deprecated; import coherence.audit.gate",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = _canonical.__all__


def __getattr__(name: str):
    return getattr(_canonical, name)


sys.modules[__name__] = _canonical
