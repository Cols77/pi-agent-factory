"""Deprecated compatibility shim for :mod:`coherence.register.closure`."""

import warnings
import sys

from coherence.register import closure as _canonical
from coherence.register.closure import *  # noqa: F401,F403

warnings.warn(
    "factory.requirements.closure is deprecated; import coherence.register.closure",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = _canonical.__all__


def __getattr__(name: str):
    return getattr(_canonical, name)


sys.modules[__name__] = _canonical
