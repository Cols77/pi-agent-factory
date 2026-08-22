from __future__ import annotations

import warnings

warnings.warn(
    "factory.system is deprecated; use coherence.navigate",
    DeprecationWarning,
    stacklevel=2,
)

from coherence.navigate.cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
