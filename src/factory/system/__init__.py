from __future__ import annotations

import warnings

warnings.warn(
    "factory.system is deprecated; use coherence.navigate",
    DeprecationWarning,
    stacklevel=2,
)

from coherence.navigate import *  # noqa: F401,F403,E402
