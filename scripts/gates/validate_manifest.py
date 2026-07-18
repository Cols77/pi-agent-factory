import json
import sys
from pathlib import Path

from factory.validation.manifest_validator import validate_manifest

if __name__ == "__main__":
    manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    errors = validate_manifest(manifest, Path.cwd())
    for e in errors:
        print(e, file=sys.stderr)
    sys.exit(1 if errors else 0)
