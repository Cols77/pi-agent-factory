import subprocess
import sys
import pytest

pytestmark = pytest.mark.unit


def test_all_gate_passes_on_clean_repo():
    rc = subprocess.run([sys.executable, "scripts/gates/all.py"]).returncode
    assert rc == 0
