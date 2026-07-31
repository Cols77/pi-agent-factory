import sys
from _proc import LINT_CMD, TYPECHECK_CMD, UNIT_CMD, AGENT_CMD, run_and_propagate

GATES = [LINT_CMD, TYPECHECK_CMD, UNIT_CMD, AGENT_CMD]

if __name__ == "__main__":
    for cmd in GATES:
        code = run_and_propagate(cmd)
        if code != 0:
            sys.exit(code)
    sys.exit(0)
