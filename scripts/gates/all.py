import sys
from _proc import run_and_propagate

GATES = [
    ["ruff", "check", "."],
    ["pyright"],
    ["pytest", "-m", "unit", "-q"],
]

if __name__ == "__main__":
    for cmd in GATES:
        code = run_and_propagate(cmd)
        if code != 0:
            sys.exit(code)
    sys.exit(0)
