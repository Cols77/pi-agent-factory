import json
import sys
from pathlib import Path

from factory.validation.session_validator import validate_session

if __name__ == "__main__":
    record = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    errors = validate_session(record)
    for e in errors:
        print(e, file=sys.stderr)
    sys.exit(1 if errors else 0)
