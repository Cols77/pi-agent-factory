"""Deprecated compatibility shim for :mod:`coherence.audit.report`."""

import warnings
import sys

from coherence.audit import report as _canonical
from coherence.audit.report import *  # noqa: F401,F403

warnings.warn(
    "factory.coverage.report is deprecated; import coherence.audit.report",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = _canonical.__all__


def __getattr__(name: str):
    return getattr(_canonical, name)


sys.modules[__name__] = _canonical
