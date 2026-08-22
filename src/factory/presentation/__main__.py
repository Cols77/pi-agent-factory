from __future__ import annotations

import warnings

warnings.warn(
    "factory.presentation is deprecated; use coherence.presentation",
    DeprecationWarning,
    stacklevel=2,
)

from coherence.presentation.cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
