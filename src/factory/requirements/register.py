"""Deprecated compatibility shim for :mod:`coherence.register.register`."""

import warnings
import sys

from coherence.register import register as _canonical
from coherence.register.register import *  # noqa: F401,F403

warnings.warn(
    "factory.requirements.register is deprecated; import coherence.register.register",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = _canonical.__all__


def __getattr__(name: str):
    return getattr(_canonical, name)


sys.modules[__name__] = _canonical
