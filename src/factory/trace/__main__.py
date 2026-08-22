from __future__ import annotations

import sys
import warnings

from coherence.trace.cli import main


warnings.warn(
    "python -m factory.trace is deprecated; use python -m coherence.trace",
    DeprecationWarning,
    stacklevel=2,
)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:], prog="factory-trace"))
