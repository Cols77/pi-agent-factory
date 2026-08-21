import subprocess
import sys
from pathlib import Path

import pytest

from factory.config import FactoryConfig, GateConfigError, GateStep, load_config
from substrate.config import GateConfigError as SubstrateGateConfigError
from substrate.config import GateStep as SubstrateGateStep
from substrate.config import load_gate_declarations, require_gates as substrate_require_gates

pytestmark = pytest.mark.unit


def _write(tmp_path: Path, body: str) -> Path:
    (tmp_path / ".factory").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".factory" / "factory.yaml").write_text(body, encoding="utf-8")
    return tmp_path


def test_parses_gate_steps_in_order_with_cwd(tmp_path):
    root = _write(tmp_path, """
gates:
  unit:
    - { cmd: "pytest -q", cwd: backend }
    - { cmd: "npm test", cwd: frontend }
""")
    cfg = load_config(root)
    assert cfg.gates["unit"] == [
        GateStep(cmd="pytest -q", cwd="backend"),
        GateStep(cmd="npm test", cwd="frontend"),
    ]


def test_cwd_is_optional(tmp_path):
    root = _write(tmp_path, 'gates:\n  full:\n    - { cmd: "ruff check ." }\n')
    assert load_config(root).gates["full"] == [GateStep(cmd="ruff check .", cwd=None)]


def test_absent_gates_section_parses_to_empty_not_an_error(tmp_path):
    # validation/pipeline.py and polish/cli.py call load_config on repos that
    # declare only playgrounds; requiring gates here would break them.
    root = _write(tmp_path, "playgrounds: {}\n")
    assert load_config(root).gates == {}


def test_missing_config_file_is_empty_config(tmp_path):
    cfg = load_config(tmp_path)
    assert cfg == FactoryConfig({}, {}, {})


def test_step_without_cmd_names_the_gate(tmp_path):
    root = _write(tmp_path, 'gates:\n  unit:\n    - { cwd: backend }\n')
    with pytest.raises(GateConfigError, match="unit"):
        load_config(root)


def test_gate_that_is_not_a_list_is_rejected(tmp_path):
    root = _write(tmp_path, 'gates:\n  unit: "pytest -q"\n')
    with pytest.raises(GateConfigError, match="unit"):
        load_config(root)


def test_polish_config_still_re_exports(tmp_path):
    # factory.validation.pipeline and factory.polish.cli import from here.
    from factory.polish.config import UnknownTypeError, load_config as polish_load

    assert polish_load(tmp_path) == FactoryConfig({}, {}, {})
    assert UnknownTypeError is not None


# --- substrate.config: GateStep/GateConfigError are the same objects
# factory.config re-exports (internal composition split, not a public move). ---


def test_factory_config_reexports_the_same_gate_types_substrate_config_defines():
    assert GateStep is SubstrateGateStep
    assert GateConfigError is SubstrateGateConfigError


def test_load_gate_declarations_parses_gate_names_and_steps():
    data = {
        "gates": {
            "unit": [{"cmd": "pytest -q", "cwd": "backend"}, {"cmd": "npm test", "cwd": "frontend"}],
            "full": [{"cmd": "ruff check ."}],
        }
    }
    declarations = load_gate_declarations(data)
    assert declarations == {
        "unit": [
            SubstrateGateStep(cmd="pytest -q", cwd="backend"),
            SubstrateGateStep(cmd="npm test", cwd="frontend"),
        ],
        "full": [SubstrateGateStep(cmd="ruff check .", cwd=None)],
    }


def test_load_gate_declarations_absent_gates_is_empty_not_an_error():
    assert load_gate_declarations({"playgrounds": {}}) == {}


def test_load_gate_declarations_rejects_non_list_steps():
    with pytest.raises(SubstrateGateConfigError, match="unit"):
        load_gate_declarations({"gates": {"unit": "pytest -q"}})


def test_load_gate_declarations_rejects_step_without_cmd():
    with pytest.raises(SubstrateGateConfigError, match="unit"):
        load_gate_declarations({"gates": {"unit": [{"cwd": "backend"}]}})


def test_substrate_require_gates_raises_when_empty_and_returns_the_same_object_otherwise():
    with pytest.raises(SubstrateGateConfigError, match="no gates"):
        substrate_require_gates({}, "some-context")

    gates = {"unit": [SubstrateGateStep(cmd="pytest -q")]}
    assert substrate_require_gates(gates, "some-context") is gates


def test_load_config_matches_load_gate_declarations_parsing(tmp_path):
    root = _write(tmp_path, """
gates:
  unit:
    - { cmd: "pytest -q", cwd: backend }
""")
    data = {"gates": {"unit": [{"cmd": "pytest -q", "cwd": "backend"}]}}
    assert load_config(root).gates == load_gate_declarations(data)


def test_substrate_config_never_imports_factory_polish_config():
    # substrate.config must stay neutral: importing it must not pull in
    # factory.polish.config, the dynamic playground/harness type registry
    # that only factory.config's own load_config composes in. Run in a
    # fresh interpreter -- checking sys.modules in-process is unreliable
    # once some earlier test in this same session has already imported
    # factory.polish.config for an unrelated reason.
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, substrate.config; "
            "assert 'factory.polish.config' not in sys.modules, sorted(sys.modules)",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
