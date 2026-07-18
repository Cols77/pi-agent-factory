from __future__ import annotations

import subprocess

# Single source of truth for each gate's command line, shared by the
# individual gate scripts (lint.py, typecheck.py, unit.py, sim_smoke.py) and
# all.py, so they can never drift out of sync with each other.
LINT_CMD = ["ruff", "check", "."]
TYPECHECK_CMD = ["pyright"]
# tests/gates/test_all_gate.py spawns `python scripts/gates/all.py` as a
# subprocess, and all.py runs this exact command as its unit-gate step. If
# that test were included here, every run of the unit suite would recurse
# into itself without bound, so it's excluded everywhere this command is used.
UNIT_CMD = ["pytest", "-m", "unit", "-q", "--ignore=tests/gates/test_all_gate.py"]
SIM_CMD = ["pytest", "-m", "sim", "-q"]


def run_and_propagate(cmd: list[str]) -> int:
    """Run cmd, stream its output, return its exit code. No parsing of stdout."""
    return subprocess.run(cmd, check=False).returncode
