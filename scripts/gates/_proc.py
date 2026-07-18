from __future__ import annotations

import os
import sys

# Remove the current script directory from sys.path to prevent local modules
# (like types.py) from shadowing standard library modules
_script_dir = os.path.dirname(os.path.abspath(__file__))
while _script_dir in sys.path:
    sys.path.remove(_script_dir)
if "" in sys.path:
    sys.path.remove("")

import subprocess  # noqa: E402


def run_and_propagate(cmd: list[str]) -> int:
    """Run cmd, stream its output, return its exit code. No parsing of stdout."""
    return subprocess.run(cmd, check=False).returncode
