from __future__ import annotations

import subprocess
import sys

# Single source of truth for each gate's command line, shared by the
# individual gate scripts (lint.py, typecheck.py, unit.py, sim_smoke.py) and
# all.py, so they can never drift out of sync with each other.


# Use sys.executable -m for all tools so they resolve from the venv even
# when the subprocess PATH doesn't include the venv Scripts directory.
PYTHON = sys.executable
LINT_CMD = [PYTHON, "-m", "ruff", "check", "."]
TYPECHECK_CMD = [PYTHON, "-m", "pyright"]
UNIT_CMD = [PYTHON, "-m", "pytest", "-m", "unit", "-q", "--ignore=tests/gates/test_all_gate.py"]
AGENT_CMD = [PYTHON, "-m", "pytest", "-m", "agent", "-q"]
SIM_CMD = [PYTHON, "-m", "pytest", "-m", "sim", "-q"]


def run_and_propagate(cmd: list[str]) -> int:
    """Run cmd, stream its output, return its exit code. No parsing of stdout."""
    return subprocess.run(cmd, check=False).returncode
