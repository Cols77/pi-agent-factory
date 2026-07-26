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
