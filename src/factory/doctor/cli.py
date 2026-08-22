"""Deprecated compatibility shim for :mod:`coherence.doctor.cli`."""

import sys
import warnings

from coherence.doctor import cli as _canonical
from coherence.doctor.cli import *  # noqa: F401,F403

warnings.warn(
    "factory.doctor.cli is deprecated; import coherence.doctor.cli",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = _canonical.__all__


def __getattr__(name: str):
    return getattr(_canonical, name)


sys.modules[__name__] = _canonical

