"""Deprecated compatibility shim for :mod:`coherence.audit.audit`."""

import warnings
import sys

from coherence.audit import audit as _canonical
from coherence.audit.audit import *  # noqa: F401,F403

warnings.warn(
    "factory.coverage.audit is deprecated; import coherence.audit.audit",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = _canonical.__all__


def __getattr__(name: str):
    return getattr(_canonical, name)


sys.modules[__name__] = _canonical
