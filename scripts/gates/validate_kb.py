import sys
import os

# Fix sys.path to avoid shadowing stdlib modules BEFORE any other imports
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path = [p for p in sys.path if os.path.abspath(p) != script_dir]

from pathlib import Path  # noqa: E402

from factory.validation.kb_validator import validate_entry_file  # noqa: E402

if __name__ == "__main__":
    errors = validate_entry_file(Path(sys.argv[1]))
    for e in errors:
        print(e, file=sys.stderr)
    sys.exit(1 if errors else 0)
