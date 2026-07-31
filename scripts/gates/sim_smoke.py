import sys
from _proc import PYTHON, run_and_propagate

SIM_CMD = [PYTHON, "-m", "pytest", "-m", "sim", "-q"]

if __name__ == "__main__":
    sys.exit(run_and_propagate(SIM_CMD))
