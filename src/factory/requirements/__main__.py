from __future__ import annotations

import sys
import warnings

from coherence.register.cli import main

warnings.warn(
    "factory.requirements.__main__ is deprecated; import coherence.register.__main__",
    DeprecationWarning,
    stacklevel=2,
)

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
