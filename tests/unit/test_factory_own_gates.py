import pytest

from factory.config import GateConfigError, load_config, require_gates
from factory.paths import factory_root

pytestmark = pytest.mark.unit


def test_the_factory_declares_its_own_gates():
    # The hard-coded scripts/gates map is gone, so the factory eats its own
    # cooking. If this file disappears, the factory silently validates nothing.
    cfg = load_config(factory_root())
    assert "unit" in cfg.gates
    assert "full" in cfg.gates
    assert "sim" not in cfg.gates
    assert "agent" not in cfg.gates
    assert cfg.gates["unit"], "unit gate must have at least one step"


def test_the_unit_gate_does_not_reference_the_removed_all_gate_test():
    cmds = " ".join(s.cmd for s in load_config(factory_root()).gates["unit"])
    assert "tests/gates/test_all_gate.py" not in cmds
    assert "test_all_gate" not in cmds


def test_the_full_gate_runs_extension_checks_directly():
    cmds = [s.cmd for s in load_config(factory_root()).gates["full"]]
    assert "{python} scripts/gates/ext.py" in cmds
    assert "{python} scripts/gates/watch_ext.py" in cmds


def test_require_gates_rejects_a_project_that_declares_none(tmp_path):
    cfg = load_config(tmp_path)  # no .factory at all
    with pytest.raises(GateConfigError, match="no gates"):
        require_gates(cfg, tmp_path)


def test_require_gates_accepts_a_project_with_gates():
    cfg = load_config(factory_root())
    assert require_gates(cfg, factory_root()) is cfg.gates
