from pathlib import Path

import pytest

from factory.config import FactoryConfig, GateConfigError, GateStep, load_config

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
