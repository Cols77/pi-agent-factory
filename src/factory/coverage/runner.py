"""Deprecated compatibility shim for :mod:`coherence.audit.runner`."""

import warnings
import sys

from coherence.audit import runner as _canonical
from coherence.audit.runner import *  # noqa: F401,F403

warnings.warn(
    "factory.coverage.runner is deprecated; import coherence.audit.runner",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = _canonical.__all__


def __getattr__(name: str):
    return getattr(_canonical, name)


sys.modules[__name__] = _canonical
