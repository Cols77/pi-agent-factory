from pathlib import Path

import frontmatter
import pytest
from factory.orchestrator.plan_to_tasks import NoTasksFoundError, parse_plan_tasks, run

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


def _write_plan(tmp_path: Path, name: str, text: str) -> Path:
    plans_dir = tmp_path / "docs" / "superpowers" / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    path = plans_dir / name
    path.write_text(text, encoding="utf-8")
    return path


def test_run_creates_one_task_file_per_plan_task(tmp_path):
    plan_path = _write_plan(tmp_path, "2026-07-20-feature.md", PLAN_TWO_TASKS)
    created = run(plan_path, tmp_path)
    assert created == ["T-001", "T-002"]

    t1 = frontmatter.load(str(tmp_path / "tasks" / "T-001-first-component.md"))
    assert t1["title"] == "First Component"
    assert t1["status"] == "todo"
    assert "`do_a(x: int) -> int`." in t1["dod"]
    assert "tests/gates pass" in t1["dod"][-1]
    assert "Create: `src/a.py`" in t1.content
    assert "docs/superpowers/plans/2026-07-20-feature.md, Task 1." in t1.content
    assert t1["source_plan"] == "docs/superpowers/plans/2026-07-20-feature.md"
    assert t1["source_task"] == 1


def test_run_numbers_ids_after_existing_tasks(tmp_path):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "T-001-example.md").write_text(
        "---\nid: T-001\ntitle: existing\nstatus: todo\ndod:\n  - x\n---\nbody\n", encoding="utf-8")
    plan_path = _write_plan(tmp_path, "2026-07-20-feature.md", PLAN_TWO_TASKS)
    created = run(plan_path, tmp_path)
    assert created == ["T-002", "T-003"]


def test_run_is_idempotent_on_rerun(tmp_path):
    plan_path = _write_plan(tmp_path, "2026-07-20-feature.md", PLAN_TWO_TASKS)
    first = run(plan_path, tmp_path)
    second = run(plan_path, tmp_path)
    assert first == ["T-001", "T-002"]
    assert second == []
    assert len(list((tmp_path / "tasks").glob("T-*.md"))) == 2


def test_run_raises_and_writes_nothing_when_no_tasks_found(tmp_path):
    plan_path = _write_plan(tmp_path, "2026-07-20-empty.md", PLAN_NO_TASKS)
    with pytest.raises(NoTasksFoundError):
        run(plan_path, tmp_path)
    assert not (tmp_path / "tasks").exists() or list((tmp_path / "tasks").glob("T-*.md")) == []


PLAN_WITH_FENCED_FIXTURE = """\
### Task 1: Real Task

**Files:**
- Create: `src/a.py`

**Interfaces:**
- Produces: `do_a() -> None`.

```markdown
### Task 1: Fixture Inside A Fence
### Task 2: Another Fixture
```

### Task 2: Second Real Task

**Files:**
- Create: `src/b.py`

**Interfaces:**
- Produces: `do_b() -> None`.
"""


def test_task_headers_inside_a_fence_are_not_sections():
    tasks = parse_plan_tasks(PLAN_WITH_FENCED_FIXTURE)
    assert [t.number for t in tasks] == [1, 2]
    assert [t.title for t in tasks] == ["Real Task", "Second Real Task"]


def test_fenced_content_stays_in_the_section_body():
    tasks = parse_plan_tasks(PLAN_WITH_FENCED_FIXTURE)
    assert "### Task 1: Fixture Inside A Fence" in tasks[0].body
    assert "```markdown" in tasks[0].body


def test_body_stops_at_the_next_section():
    tasks = parse_plan_tasks(PLAN_WITH_FENCED_FIXTURE)
    assert "Second Real Task" not in tasks[0].body
    assert "`src/b.py`" in tasks[1].body


def test_tilde_fences_are_masked_too():
    text = "### Task 1: Real\n\n~~~\n### Task 9: Fake\n~~~\n"
    assert [t.number for t in parse_plan_tasks(text)] == [1]


def test_files_block_and_produces_survive_masking():
    tasks = parse_plan_tasks(PLAN_WITH_FENCED_FIXTURE)
    assert "Create: `src/a.py`" in tasks[0].files_block
    assert tasks[0].produces == ["`do_a() -> None`."]
