import pytest
from factory.polish.playground import Playground
from factory.polish.reference import ScenarioReplayPlayground

pytestmark = pytest.mark.unit


def _mk(dir_, name):
    (dir_ / f"{name}.json").write_text("{}", encoding="utf-8")


def test_is_a_playground(tmp_path):
    assert isinstance(ScenarioReplayPlayground(tmp_path), Playground)


def test_list_usecases_sorted(tmp_path):
    _mk(tmp_path, "shark_warning")
    _mk(tmp_path, "all_clear")
    assert ScenarioReplayPlayground(tmp_path).list_usecases() == ["all_clear", "shark_warning"]


def test_setup_returns_session(tmp_path):
    _mk(tmp_path, "shark_warning")
    s = ScenarioReplayPlayground(tmp_path).setup("shark_warning")
    assert s.entrypoints == [str(tmp_path / "shark_warning.json")]
    assert "shark_warning" in s.describe
    s.teardown()  # no-op, does not raise


def test_setup_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        ScenarioReplayPlayground(tmp_path).setup("nope")
