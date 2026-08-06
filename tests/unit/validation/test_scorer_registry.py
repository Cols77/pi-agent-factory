import pytest
from factory.validation.scorer_registry import ScorerModuleError, load_scorers

pytestmark = pytest.mark.unit


def _write_module(tmp_path, pkg: str, body: str) -> None:
    # A distinct package name per test: importlib caches in sys.modules, so reusing
    # one name would make a later test read an earlier test's module.
    d = tmp_path / "src" / pkg
    d.mkdir(parents=True)
    (d / "__init__.py").write_text("", encoding="utf-8")
    (d / "scorers.py").write_text(body, encoding="utf-8")


def test_absent_module_name_is_an_empty_map(tmp_path):
    assert load_scorers(None, tmp_path) == {}
    assert load_scorers("", tmp_path) == {}


def test_scorers_are_read_from_the_targets_src_tree(tmp_path):
    _write_module(tmp_path, "demo_ok", "SCORERS = {'always_true': lambda frames, window: True}\n")
    scorers = load_scorers("demo_ok.scorers", tmp_path)
    assert sorted(scorers) == ["always_true"]
    assert scorers["always_true"]([], None) is True


def test_a_module_without_SCORERS_is_reported_not_guessed(tmp_path):
    _write_module(tmp_path, "demo_bare", "def trial_thing(frames, window):\n    return True\n")
    with pytest.raises(ScorerModuleError, match="SCORERS"):
        load_scorers("demo_bare.scorers", tmp_path)


def test_an_unimportable_module_names_itself(tmp_path):
    with pytest.raises(ScorerModuleError, match="demo_missing"):
        load_scorers("demo_missing.scorers", tmp_path)


def test_the_targets_src_is_not_left_on_sys_path(tmp_path):
    import sys

    before = list(sys.path)
    _write_module(tmp_path, "demo_clean", "SCORERS = {}\n")
    load_scorers("demo_clean.scorers", tmp_path)
    assert sys.path == before
