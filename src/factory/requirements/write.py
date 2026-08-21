"""Deprecated compatibility shim for :mod:`coherence.register.write`."""

import warnings
import sys

from coherence.register import write as _canonical
from coherence.register.write import *  # noqa: F401,F403

warnings.warn(
    "factory.requirements.write is deprecated; import coherence.register.write",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = _canonical.__all__


def __getattr__(name: str):
    return getattr(_canonical, name)


sys.modules[__name__] = _canonical
