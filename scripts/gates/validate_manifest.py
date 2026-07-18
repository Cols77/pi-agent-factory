import sys
import os

# Fix sys.path to avoid shadowing stdlib modules BEFORE any other imports
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path = [p for p in sys.path if os.path.abspath(p) != script_dir]

import json  # noqa: E402
from pathlib import Path  # noqa: E402

from factory.validation.manifest_validator import validate_manifest  # noqa: E402

if __name__ == "__main__":
    manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    errors = validate_manifest(manifest, Path.cwd())
    for e in errors:
        print(e, file=sys.stderr)
    sys.exit(1 if errors else 0)
