import pytest
from factory.polish.config import UnknownTypeError, load_config
from factory.polish.reference import ScenarioReplayPlayground
from factory.validation.sim_harness import SimTestbenchHarness

pytestmark = pytest.mark.unit

_YAML = """
playgrounds:
  ref:
    type: scenario-replay
    usecases_dir: validation/traces
harnesses:
  nav:
    type: sim-testbench
    traces_dir: validation/traces
"""


def _project(tmp_path, yaml_text=_YAML):
    fac = tmp_path / ".factory"
    fac.mkdir()
    (fac / "factory.yaml").write_text(yaml_text, encoding="utf-8")
    traces = tmp_path / "validation" / "traces"
    traces.mkdir(parents=True)
    (traces / "demo.json").write_text("{}", encoding="utf-8")
    return tmp_path


def test_missing_config_is_empty(tmp_path):
    cfg = load_config(tmp_path)
    assert cfg.playgrounds == {} and cfg.harnesses == {}


def test_builds_playgrounds_and_harnesses(tmp_path):
    cfg = load_config(_project(tmp_path))
    assert set(cfg.playgrounds) == {"ref"}
    assert isinstance(cfg.playgrounds["ref"], ScenarioReplayPlayground)
    assert cfg.playgrounds["ref"].list_usecases() == ["demo"]
    assert set(cfg.harnesses) == {"nav"}
    assert isinstance(cfg.harnesses["nav"], SimTestbenchHarness)


def test_unknown_type_raises(tmp_path):
    bad = "playgrounds:\n  x:\n    type: nope\n"
    with pytest.raises(UnknownTypeError):
        load_config(_project(tmp_path, bad))
