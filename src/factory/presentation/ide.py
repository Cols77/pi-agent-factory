from __future__ import annotations

import importlib as _importlib
import sys as _sys
import warnings as _warnings

_warnings.warn(
    "factory.presentation.ide is deprecated; use coherence.presentation.ide",
    DeprecationWarning,
    stacklevel=2,
)
_sys.modules[__name__] = _importlib.import_module("coherence.presentation.ide")
