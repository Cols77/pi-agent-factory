import sys
from _proc import run_and_propagate

if __name__ == "__main__":
    sys.exit(run_and_propagate(["pytest", "-m", "unit", "-q"]))
