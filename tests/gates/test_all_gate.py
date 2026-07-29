import subprocess
import sys
import pytest

pytestmark = pytest.mark.unit


def test_agent_gate_defined_in_proc():
    """AGENT_CMD must be defined in _proc."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_proc", "scripts/gates/_proc.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, 'AGENT_CMD')
    assert 'agent' in mod.AGENT_CMD



def test_all_gate_passes_on_clean_repo():
    rc = subprocess.run([sys.executable, "scripts/gates/all.py"]).returncode
    assert rc == 0
