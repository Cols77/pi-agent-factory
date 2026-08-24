"""Deprecated compatibility shim for :mod:`coherence.audit.scope`."""

import warnings
import sys

from coherence.audit import scope as _canonical
from coherence.audit.scope import *  # noqa: F401,F403

warnings.warn(
    "factory.coverage.scope is deprecated; import coherence.audit.scope",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = _canonical.__all__


def __getattr__(name: str):
    return getattr(_canonical, name)


sys.modules[__name__] = _canonical
