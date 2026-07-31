import subprocess
import sys
import pytest

pytestmark = pytest.mark.unit


def test_ext_gate_passes():
    rc = subprocess.run([sys.executable, "scripts/gates/ext.py"]).returncode
    assert rc == 0
