import pytest
from factory.orchestrator.deliverables import parse_deliverables

pytestmark = pytest.mark.unit

BODY = """- Create: `src/drone/interfaces.py`
- Create: `src/drone/fake_flight_controller.py`
- Test: `tests/unit/drone/test_interfaces.py`

Full steps: docs/plan.md, Task 1."""


def test_parses_create_and_test_paths():
    assert parse_deliverables(BODY) == [
        "src/drone/interfaces.py",
        "src/drone/fake_flight_controller.py",
        "tests/unit/drone/test_interfaces.py",
    ]


def test_parses_modify_lines_and_dedupes():
    body = "- Modify: `a.py`\n- Test: `a.py`\n- prose line, ignored"
    assert parse_deliverables(body) == ["a.py"]


def test_ignores_bodies_without_deliverables():
    assert parse_deliverables("just some prose\nno paths here") == []


def test_created_deliverables_only_create_and_test(tmp_path):
    from factory.orchestrator.deliverables import created_deliverables
    body = "- Create: `src/a.py`\n- Modify: `src/b.py`\n- Test: `tests/test_a.py`"
    # Modify: is excluded -- its file exists regardless, so it's no done-signal.
    assert created_deliverables(body) == ["src/a.py", "tests/test_a.py"]


def test_deliverables_exist_true_when_all_created_files_present(tmp_path):
    from factory.orchestrator.deliverables import deliverables_exist
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text("x", encoding="utf-8")
    body = "- Create: `src/a.py`\n- Test: `tests/test_a.py`"
    assert deliverables_exist(body, tmp_path) is True


def test_deliverables_exist_false_when_any_missing(tmp_path):
    from factory.orchestrator.deliverables import deliverables_exist
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x", encoding="utf-8")
    body = "- Create: `src/a.py`\n- Test: `tests/test_a.py`"  # test file missing
    assert deliverables_exist(body, tmp_path) is False


def test_deliverables_exist_false_when_no_created_deliverables(tmp_path):
    from factory.orchestrator.deliverables import deliverables_exist
    # Modify-only task: nothing to signal doneness by existence.
    assert deliverables_exist("- Modify: `src/x.py`", tmp_path) is False
    assert deliverables_exist("just prose", tmp_path) is False
