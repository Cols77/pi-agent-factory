import subprocess
import sys
import pytest

pytestmark = pytest.mark.unit


def test_watch_ext_gate_passes():
    rc = subprocess.run([sys.executable, "scripts/gates/watch_ext.py"]).returncode
    assert rc == 0
