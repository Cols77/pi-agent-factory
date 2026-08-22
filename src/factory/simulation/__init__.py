from __future__ import annotations

import warnings

warnings.warn(
    "factory.simulation is deprecated; use coherence.simulation",
    DeprecationWarning,
    stacklevel=2,
)

from coherence.simulation import *  # noqa: F401,F403,E402

