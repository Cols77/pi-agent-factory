from __future__ import annotations

import warnings

warnings.warn(
    "factory.goals is deprecated; use coherence.goals",
    DeprecationWarning,
    stacklevel=2,
)

from coherence.goals.cli import main


if __name__ == "__main__":
    raise SystemExit(main())

