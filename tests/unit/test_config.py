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


# --- SR-034 decision 3 (2026-09-11): the governed fixer budget is project-wide ---


def test_governed_execution_budget_is_typed_project_wide_and_fail_closed(tmp_path):
    from dataclasses import fields as dataclass_fields

    from factory.config import (
        GovernedExecutionConfig,
        GovernedExecutionConfigError,
        require_governed_execution,
    )

    root = _write(tmp_path, "governed_execution:\n  max_fixer_iterations: 2\n")
    cfg = load_config(root)
    assert cfg.governed_execution == GovernedExecutionConfig(max_fixer_iterations=2)
    assert require_governed_execution(cfg, root).max_fixer_iterations == 2

    # Project-wide, not task-local: one field, no task dimension, and a
    # task-scoped override elsewhere in the file cannot change it.
    assert [field.name for field in dataclass_fields(GovernedExecutionConfig)] == [
        "max_fixer_iterations"
    ]
    override = _write(
        tmp_path / "override",
        "governed_execution:\n  max_fixer_iterations: 2\n"
        "tasks:\n  T-001:\n    governed_execution:\n      max_fixer_iterations: 9\n",
    )
    assert require_governed_execution(load_config(override), override).max_fixer_iterations == 2

    # The decided value does not make an unset config acceptable: a governed
    # dispatch still fails closed with a configuration diagnostic.
    unset = _write(tmp_path / "unset", "playgrounds: {}\n")
    unset_cfg = load_config(unset)
    assert unset_cfg.governed_execution.max_fixer_iterations is None
    with pytest.raises(GovernedExecutionConfigError, match="max_fixer_iterations"):
        require_governed_execution(unset_cfg, unset)


@pytest.mark.parametrize("value", [0, -1, "2", 2.0, True, False, [2]])
def test_governed_execution_budget_rejects_zero_negative_boolean_and_non_integer(tmp_path, value):
    import json as _json

    from factory.config import GovernedExecutionConfigError

    root = _write(
        tmp_path, f"governed_execution:\n  max_fixer_iterations: {_json.dumps(value)}\n"
    )
    with pytest.raises(GovernedExecutionConfigError, match="max_fixer_iterations"):
        load_config(root)


def test_the_factory_records_the_decided_governed_fixer_budget():
    """The committed value (human decision 3, 2026-09-11) is 2, project-wide."""
    from factory.config import require_governed_execution

    repo_root = Path(__file__).resolve().parents[2]
    cfg = load_config(repo_root)
    assert cfg.governed_execution.max_fixer_iterations == 2
    assert require_governed_execution(cfg, repo_root).max_fixer_iterations == 2


def test_require_governed_execution_revalidates_a_patched_config(tmp_path):
    """F6b: require_governed_execution only checked `is None`, so a duck-typed or
    patched config handed a governed dispatch -5 / '9' / True. The value is
    re-validated here; the production load_config path is unchanged."""
    from dataclasses import replace as dc_replace
    from types import SimpleNamespace

    from factory.config import (
        GovernedExecutionConfigError,
        require_governed_execution,
    )

    root = _write(tmp_path, "governed_execution:\n  max_fixer_iterations: 2\n")
    cfg = load_config(root)
    assert require_governed_execution(cfg, root).max_fixer_iterations == 2

    # A duck-typed stand-in is refused outright, by type.
    duck = dc_replace(cfg, governed_execution=SimpleNamespace(max_fixer_iterations=2))
    assert not isinstance(duck.governed_execution, type(cfg.governed_execution))
    with pytest.raises(GovernedExecutionConfigError, match="GovernedExecutionConfig"):
        require_governed_execution(duck, root)

    # A patched real instance (object.__setattr__ bypasses the frozen __post_init__)
    # is refused for each out-of-range/ill-typed value.
    for value in (-5, 0, "9", True, False, 2.0, None):
        patched = load_config(root)
        object.__setattr__(patched.governed_execution, "max_fixer_iterations", value)
        with pytest.raises(GovernedExecutionConfigError, match="max_fixer_iterations"):
            require_governed_execution(patched, root)
