import pytest
from factory.orchestrator.plan_to_tasks import parse_plan_tasks

pytestmark = pytest.mark.unit

PLAN_TWO_TASKS = """\
# Some Feature Implementation Plan

**Goal:** do the thing.

---

### Task 1: First Component

**Files:**
- Create: `src/a.py`
- Test: `tests/test_a.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `do_a(x: int) -> int`.

- [ ] **Step 1: Write the failing test**

some code here

---

### Task 2: Second Component

**Files:**
- Create: `src/b.py`

**Interfaces:**
- Consumes: `do_a` (Task 1).
- Produces: `do_b() -> None`.

- [ ] **Step 1: Write the failing test**

some more code
"""

PLAN_NO_TASKS = "# Just a doc\n\nNo task sections here.\n"

PLAN_TASK_WITHOUT_PRODUCES = """\
### Task 1: Config Only

**Files:**
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: nothing.

- [ ] **Step 1: Edit the file**
"""


def test_parses_multiple_tasks():
    tasks = parse_plan_tasks(PLAN_TWO_TASKS)
    assert [t.number for t in tasks] == [1, 2]
    assert tasks[0].title == "First Component"
    assert tasks[1].title == "Second Component"


def test_extracts_files_block():
    tasks = parse_plan_tasks(PLAN_TWO_TASKS)
    assert "Create: `src/a.py`" in tasks[0].files_block
    assert "Test: `tests/test_a.py`" in tasks[0].files_block
    assert "Interfaces" not in tasks[0].files_block


def test_extracts_produces_lines():
    tasks = parse_plan_tasks(PLAN_TWO_TASKS)
    assert tasks[0].produces == ["`do_a(x: int) -> int`."]
    assert tasks[1].produces == ["`do_b() -> None`."]


def test_no_task_sections_returns_empty_list():
    assert parse_plan_tasks(PLAN_NO_TASKS) == []


def test_task_without_produces_line_has_empty_list():
    tasks = parse_plan_tasks(PLAN_TASK_WITHOUT_PRODUCES)
    assert tasks[0].produces == []
    assert "Modify: `pyproject.toml`" in tasks[0].files_block
