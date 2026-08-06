from __future__ import annotations

import subprocess

# Shared by the standalone gate scripts (ext.py, watch_ext.py). The per-gate
# command lines that used to live here are now declared in .factory/factory.yaml.


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
