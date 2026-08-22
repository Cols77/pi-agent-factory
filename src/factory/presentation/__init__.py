from __future__ import annotations

import warnings

warnings.warn(
    "factory.presentation is deprecated; use coherence.presentation",
    DeprecationWarning,
    stacklevel=2,
)

from coherence.presentation import *  # noqa: F401,F403,E402
