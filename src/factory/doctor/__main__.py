from __future__ import annotations

import sys
import warnings

from coherence.doctor.cli import main

warnings.warn(
    "factory.doctor.__main__ is deprecated; import coherence.doctor.__main__",
    DeprecationWarning,
    stacklevel=2,
)

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

