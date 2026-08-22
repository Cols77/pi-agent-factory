"""Deprecated compatibility shim for :mod:`coherence.register.cli`."""

import warnings
import sys

from coherence.register import cli as _canonical
from coherence.register.cli import *  # noqa: F401,F403

warnings.warn(
    "factory.requirements.cli is deprecated; import coherence.register.cli",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = _canonical.__all__


def __getattr__(name: str):
    return getattr(_canonical, name)


sys.modules[__name__] = _canonical
