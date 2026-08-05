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


# pytest exits 5 when nothing is collected. For a gate that means this project has
# no such suite -- not that the suite failed. all.py runs AGENT_CMD, and a repo
# with no agent-marked tests must not fail the pipeline because of it.
#
# Deliberately narrowed to pytest: ruff and pyright have their own meanings for
# exit 5, and silently treating those as success would hide real failures.
PYTEST_NO_TESTS_COLLECTED = 5


def _is_pytest(cmd: list[str]) -> bool:
    return "pytest" in cmd


def run_and_propagate(cmd: list[str]) -> int:
    """Run cmd, stream its output, return its exit code. No parsing of stdout."""
    code = subprocess.run(cmd, check=False).returncode
    if code == PYTEST_NO_TESTS_COLLECTED and _is_pytest(cmd):
        return 0
    return code
