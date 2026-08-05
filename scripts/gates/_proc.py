from __future__ import annotations

import subprocess

# Shared by the standalone gate scripts (ext.py, watch_ext.py). The per-gate
# command lines that used to live here are now declared in .factory/factory.yaml.


def run_and_propagate(cmd: list[str]) -> int:
    """Run cmd, stream its output, return its exit code. No parsing of stdout."""
    return subprocess.run(cmd, check=False).returncode
