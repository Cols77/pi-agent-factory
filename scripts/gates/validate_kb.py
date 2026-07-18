import sys
from pathlib import Path

from factory.validation.kb_validator import validate_entry_file

if __name__ == "__main__":
    errors = validate_entry_file(Path(sys.argv[1]))
    for e in errors:
        print(e, file=sys.stderr)
    sys.exit(1 if errors else 0)
