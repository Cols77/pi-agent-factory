import sys
from _proc import run_and_propagate

GATES = [
    ["ruff", "check", "."],
    ["pyright"],
    # Excludes test_all_gate.py: that test spawns this very script, so
    # including it here would make all.py recurse into itself without bound.
    ["pytest", "-m", "unit", "-q", "--ignore=tests/gates/test_all_gate.py"],
]

if __name__ == "__main__":
    for cmd in GATES:
        code = run_and_propagate(cmd)
        if code != 0:
            sys.exit(code)
    sys.exit(0)
