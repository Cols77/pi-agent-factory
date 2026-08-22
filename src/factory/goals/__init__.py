from __future__ import annotations

import warnings

warnings.warn(
    "factory.goals is deprecated; use coherence.goals",
    DeprecationWarning,
    stacklevel=2,
)

from coherence.goals import *  # noqa: F401,F403,E402

