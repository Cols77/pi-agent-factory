import sys
from _proc import TYPECHECK_CMD, run_and_propagate

if __name__ == "__main__":
    sys.exit(run_and_propagate(TYPECHECK_CMD))
