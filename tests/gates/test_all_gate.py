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


def test_agent_gate_in_all_gates_list():
    """all.py must import AGENT_CMD and include it in GATES."""
    with open("scripts/gates/all.py") as f:
        content = f.read()
    assert "AGENT_CMD" in content, "all.py must import AGENT_CMD"
    # Verify GATES includes AGENT_CMD (not INTEGRATION_CMD or SIM_CMD)
    assert "AGENT_CMD," in content or "AGENT_CMD]" in content, "AGENT_CMD must be in GATES list"


def test_no_yagni_cmds_in_proc():
    """Only LINT_CMD, TYPECHECK_CMD, UNIT_CMD, AGENT_CMD should exist in _proc."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_proc", "scripts/gates/_proc.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # These YAGNI commands should NOT exist
    assert not hasattr(mod, 'INTEGRATION_CMD'), "INTEGRATION_CMD is YAGNI, remove it"
    assert not hasattr(mod, 'SIM_CMD'), "SIM_CMD is YAGNI, remove it"


def test_no_yagni_imports_in_all():
    """all.py must not import INTEGRATION_CMD or SIM_CMD."""
    with open("scripts/gates/all.py") as f:
        content = f.read()
    assert "INTEGRATION_CMD" not in content, "all.py must not import INTEGRATION_CMD (YAGNI)"
    assert "SIM_CMD" not in content, "all.py must not import SIM_CMD (YAGNI)"


def test_all_gate_passes_on_clean_repo():
    rc = subprocess.run([sys.executable, "scripts/gates/all.py"]).returncode
    assert rc == 0