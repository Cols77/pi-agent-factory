from __future__ import annotations

import sys
import warnings

from coherence.measurement.cli import main

warnings.warn(
    "factory.validation.__main__ is deprecated; import coherence.measurement.__main__",
    DeprecationWarning,
    stacklevel=2,
)

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
