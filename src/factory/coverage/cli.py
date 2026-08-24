"""Deprecated compatibility shim for :mod:`coherence.audit.cli`."""

import warnings
import sys

from coherence.audit import cli as _canonical
from coherence.audit.cli import *  # noqa: F401,F403

warnings.warn(
    "factory.coverage.cli is deprecated; import coherence.audit.cli",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = _canonical.__all__


def __getattr__(name: str):
    return getattr(_canonical, name)


sys.modules[__name__] = _canonical
