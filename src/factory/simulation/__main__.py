from __future__ import annotations

import warnings

warnings.warn(
    "factory.simulation is deprecated; use coherence.simulation",
    DeprecationWarning,
    stacklevel=2,
)

from coherence.simulation.cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
