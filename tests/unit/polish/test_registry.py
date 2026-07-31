import pytest
from factory.polish.registry import load_playgrounds

pytestmark = pytest.mark.unit

_REGISTRY = """
from pathlib import Path
from factory.polish.reference import ScenarioReplayPlayground

PLAYGROUNDS = {"ref": ScenarioReplayPlayground(Path(__file__).parent / "usecases")}
"""


def test_missing_registry_returns_empty(tmp_path):
    assert load_playgrounds(tmp_path) == {}


def test_loads_playgrounds(tmp_path):
    fac = tmp_path / ".factory"
    fac.mkdir()
    (fac / "registry.py").write_text(_REGISTRY, encoding="utf-8")
    (fac / "usecases").mkdir()
    (fac / "usecases" / "demo.json").write_text("{}", encoding="utf-8")
    pgs = load_playgrounds(tmp_path)
    assert set(pgs) == {"ref"}
    assert pgs["ref"].list_usecases() == ["demo"]
