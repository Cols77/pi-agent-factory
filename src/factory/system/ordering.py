from __future__ import annotations

import importlib as _importlib
import sys as _sys
import warnings as _warnings

_warnings.warn(
    "factory.system.ordering is deprecated; use coherence.navigate.ordering",
    DeprecationWarning,
    stacklevel=2,
)
_sys.modules[__name__] = _importlib.import_module("coherence.navigate.ordering")
