# /plan Command, Targeted /factory-run, and Hard Skill Loading Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an interactive `/plan` command (brainstorming -> writing-plans, ending in deterministically-parsed `tasks/T-*.md` files) and a `/factory-run [task-id]` command (target one specific task instead of always "whatever's next") to `pi-ext/factory-watch/`, and replace soft advertise-and-hope skill loading with deterministic content injection everywhere this repo loads a skill -- both for `/plan`'s own skills and the orchestrator's existing sub-agent roles.

**Architecture:** Same shape as the rest of `pi-ext/factory-watch/` and `src/factory/orchestrator/`: pure, unit-tested functions for parsing/building/formatting, thin wiring for the actual file I/O, subprocess, and Pi runtime calls. Two parallel (not shared-code) implementations of the same "hard skill load" pattern -- TypeScript using pi's own exported `loadSkills`/`stripFrontmatter`, Python using the already-installed `python-frontmatter` -- because they inject into two different runtimes (a live Pi session turn vs. a `pi -p` subprocess prompt string).

**Tech Stack:** Python (existing orchestrator, `python-frontmatter`), TypeScript/vitest (existing `pi-ext/factory-watch/`), no new dependencies in either.

## Global Constraints

- Every task ends green (`uv run pytest -m unit -q`, `npm --prefix pi-ext/factory-watch run typecheck`, `npm --prefix pi-ext/factory-watch test`, as applicable to what the task touched) and is committed.
- Python: `from __future__ import annotations` at the top of every new/modified module, matching every existing file in `src/factory/orchestrator/`.
- TypeScript: strict mode, NodeNext, matching `pi-ext/factory-watch/tsconfig.json` (unchanged).
- No changes to `pi-ext/scope-guard/` -- it's a separate extension for a separate process context (Plan 2), untouched by this work.

Full design: `docs/superpowers/specs/2026-07-20-factory-plan-and-run-design.md`.

---

## File Structure

```
src/factory/orchestrator/
  skills.py              # new: load_skill_block() -- pure, hard-loads one SKILL.md
  plan_to_tasks.py        # new: plan.md -> tasks/T-*.md parser + CLI
  prompts.py               # modified: compose_prompt() takes skills_dir, injects full blocks
  nodes.py                 # modified: run_dev/run_review take repo_root
  runner.py                 # modified: run_task passes repo_root through; run_next takes task_id
  ledger.py                  # modified: get_task(), TaskNotFoundError, TaskNotTodoError
  __main__.py                 # modified: --task on run, --json on list

tests/unit/orchestrator/
  _skill_fixtures.py       # new: write_skill_stubs() shared test helper
  test_skills.py            # new
  test_plan_to_tasks.py (at tests/unit/, see Task 8)
  test_prompts.py, test_nodes_context_dev.py, test_nodes_val_review.py,
  test_run_next.py, test_runner_e2e.py, test_ledger.py, test_main.py  # modified

.pi/skills/
  brainstorming/SKILL.md          # new (vendored, adapted)
  writing-plans/SKILL.md           # new (vendored, adapted)
  <8 existing skills>/SKILL.md      # modified: + disable-model-invocation: true

pi-ext/factory-watch/src/
  skill-prompt.ts            # new: buildSkillBlock(), buildPlanSeedPrompt()
  task-picker.ts               # new: formatTaskOption(), parseTaskIdFromOption()
  process-control.ts             # modified: buildRunCommand(taskId?), buildListJsonCommand()
  pi-types.ts                      # modified: + select, newSession, ReplacedSessionCtx
  index.ts                           # modified: + /plan, /factory-run; shared helpers extracted

pi-ext/factory-watch/test/
  skill-prompt.test.ts, task-picker.test.ts   # new
  process-control.test.ts, handler.test.ts      # modified
```

---

### Task 1: `load_skill_block` -- pure hard skill loading (Python)

**Files:**
- Create: `src/factory/orchestrator/skills.py`
- Create: `tests/unit/orchestrator/_skill_fixtures.py`
- Test: `tests/unit/orchestrator/test_skills.py`

**Interfaces:**
- Consumes: nothing new (uses `python-frontmatter`, already a dependency).
- Produces: `load_skill_block(skills_dir: Path, name: str) -> str`, raising `FileNotFoundError` if the skill isn't vendored. Also `write_skill_stubs(root: Path) -> None`, a test-only helper reused by later tasks.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/orchestrator/test_skills.py
import pytest
from pathlib import Path
from factory.orchestrator.skills import load_skill_block

pytestmark = pytest.mark.unit


def test_load_skill_block_wraps_stripped_content(tmp_path):
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: my-skill\ndescription: a test skill\n---\n\n# My Skill\n\nDo the thing.\n",
        encoding="utf-8",
    )
    block = load_skill_block(tmp_path, "my-skill")
    assert block.startswith('<skill name="my-skill" location="')
    assert "# My Skill" in block
    assert "Do the thing." in block
    assert block.endswith("</skill>")
    assert "---" not in block  # frontmatter stripped


def test_load_skill_block_missing_skill_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_skill_block(tmp_path, "does-not-exist")
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/orchestrator/test_skills.py -v`
Expected: FAIL -- `factory.orchestrator.skills` module not found.

- [ ] **Step 3: Implement `src/factory/orchestrator/skills.py`**

```python
from __future__ import annotations

from pathlib import Path

import frontmatter


def load_skill_block(skills_dir: Path, name: str) -> str:
    """Read skills_dir/<name>/SKILL.md, strip frontmatter, wrap in the same
    <skill name="..." location="..."> block shape Pi's own native
    /skill:name expansion produces (see pi-coding-agent's
    AgentSession._expandSkillCommand) -- so both this Python-side injection
    and the TypeScript-side one in pi-ext/factory-watch/src/skill-prompt.ts
    hard-load skill content deterministically instead of relying on the
    model choosing to read it.

    Raises FileNotFoundError if the skill file doesn't exist -- a role
    naming a skill that isn't vendored is a hard configuration error, not
    something to silently degrade past.
    """
    path = skills_dir / name / "SKILL.md"
    if not path.exists():
        raise FileNotFoundError(f"skill not found: {path}")
    post = frontmatter.load(str(path))
    body = post.content.strip()
    return f'<skill name="{name}" location="{path}">\n{body}\n</skill>'
```

- [ ] **Step 4: Write the shared test skill-stub helper**

```python
# tests/unit/orchestrator/_skill_fixtures.py
from __future__ import annotations

from pathlib import Path

SKILL_NAMES = [
    "verification-before-completion",
    "context-completeness-audit",
    "test-driven-development",
    "systematic-debugging",
    "receiving-code-review",
    "kb-lookup",
    "requesting-code-review",
    "coding-principles",
]


def write_skill_stubs(root: Path) -> None:
    """Write minimal SKILL.md stub files under root/.pi/skills/<name>/ for
    every skill the currently-invoked roles (context-gatherer/dev/review)
    need, at the real repo's .pi/skills/ layout. Used by any test that
    exercises compose_prompt, directly or via run_dev/run_review/run_task/
    run_next, now that skill loading is hard-required rather than optional.
    """
    for name in SKILL_NAMES:
        skill_dir = root / ".pi" / "skills" / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: stub for tests\n---\n\nStub content for {name}.\n",
            encoding="utf-8",
        )
```

- [ ] **Step 5: Run to pass**

Run: `uv run pytest tests/unit/orchestrator/test_skills.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add src/factory/orchestrator/skills.py tests/unit/orchestrator/_skill_fixtures.py tests/unit/orchestrator/test_skills.py
git commit -m "feat: pure hard skill-block loading for sub-agent prompts"
```

---

### Task 2: Wire hard skill loading into every sub-agent role's prompt

**Files:**
- Modify: `src/factory/orchestrator/prompts.py`
- Modify: `src/factory/orchestrator/nodes.py`
- Modify: `src/factory/orchestrator/runner.py`
- Modify: `tests/unit/orchestrator/test_prompts.py`
- Modify: `tests/unit/orchestrator/test_nodes_context_dev.py`
- Modify: `tests/unit/orchestrator/test_nodes_val_review.py`
- Modify: `tests/unit/orchestrator/test_run_next.py`
- Modify: `tests/unit/orchestrator/test_runner_e2e.py`

**Interfaces:**
- Consumes: `load_skill_block` (Task 1), `write_skill_stubs` (Task 1).
- Produces: `compose_prompt(..., *, skills_dir: Path) -> str` (new required kwarg); `run_dev`/`run_review` gain a `repo_root: Path` parameter (matching `run_context_gatherer`'s existing one).

This is one task, not several, because `compose_prompt` requiring `skills_dir` and `nodes.py`/`runner.py` supplying it are inseparable -- nothing compiles/passes mid-way.

- [ ] **Step 1: Update `compose_prompt`'s test to expect full skill blocks (RED)**

Replace `tests/unit/orchestrator/test_prompts.py` in full:

```python
import pytest
from pathlib import Path
from factory.orchestrator.types import AgentRole
from factory.orchestrator.ledger import Task
from factory.orchestrator.prompts import compose_prompt
from ._skill_fixtures import write_skill_stubs

pytestmark = pytest.mark.unit

TASK = Task(id="T-001", title="Do X", status="todo", dod=["crit A"], body="body text", path=Path("t"))


def test_prompt_is_deterministic_and_includes_key_parts(tmp_path):
    write_skill_stubs(tmp_path)
    skills_dir = tmp_path / ".pi" / "skills"
    kb = [{"id": "kb-0001", "title": "watch arming"}]
    a = compose_prompt(AgentRole.DEV, TASK, manifest=None, kb_entries=kb, feedback="fix Y", skills_dir=skills_dir)
    b = compose_prompt(AgentRole.DEV, TASK, manifest=None, kb_entries=kb, feedback="fix Y", skills_dir=skills_dir)
    assert a == b
    for needle in ["T-001", "Do X", "crit A", "kb-0001", "watch arming", "fix Y", "test-driven-development"]:
        assert needle in a
    assert '<skill name="test-driven-development"' in a


def test_no_feedback_no_kb_still_valid(tmp_path):
    write_skill_stubs(tmp_path)
    skills_dir = tmp_path / ".pi" / "skills"
    out = compose_prompt(AgentRole.REVIEW, TASK, skills_dir=skills_dir)
    assert "T-001" in out and "crit A" in out


def test_compose_prompt_tolerates_non_dict_manifest_context(tmp_path):
    """Malformed manifest with context=None should not raise AttributeError."""
    write_skill_stubs(tmp_path)
    skills_dir = tmp_path / ".pi" / "skills"
    manifest = {"context": None}
    out = compose_prompt(AgentRole.DEV, TASK, manifest=manifest, skills_dir=skills_dir)
    assert isinstance(out, str)
    assert "T-001" in out


def test_compose_prompt_tolerates_non_dict_context_value(tmp_path):
    """Malformed manifest with context as non-dict should degrade gracefully."""
    write_skill_stubs(tmp_path)
    skills_dir = tmp_path / ".pi" / "skills"
    manifest = {"context": "invalid_string"}
    out = compose_prompt(AgentRole.DEV, TASK, manifest=manifest, skills_dir=skills_dir)
    assert isinstance(out, str)
    assert "T-001" in out


def test_compose_prompt_requires_every_vendored_skill_to_exist(tmp_path):
    """Missing skill file for a role's ROLE_SKILLS entry is a hard error, not a
    silent fallback to a bare skill name."""
    (tmp_path / ".pi" / "skills").mkdir(parents=True)  # empty -- nothing vendored
    with pytest.raises(FileNotFoundError):
        compose_prompt(AgentRole.REVIEW, TASK, skills_dir=tmp_path / ".pi" / "skills")
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/orchestrator/test_prompts.py -v`
Expected: FAIL -- `compose_prompt() missing 1 required keyword-only argument: 'skills_dir'`.

- [ ] **Step 3: Update `compose_prompt`**

In `src/factory/orchestrator/prompts.py`, replace the whole file:

```python
from __future__ import annotations

from pathlib import Path

from factory.orchestrator.ledger import Task
from factory.orchestrator.roles import ROLE_PROMPTS, ROLE_SKILLS
from factory.orchestrator.skills import load_skill_block
from factory.orchestrator.types import AgentRole


def compose_prompt(
    role: AgentRole,
    task: Task,
    manifest: dict | None = None,
    kb_entries: list[dict] | None = None,
    feedback: str | None = None,
    *,
    skills_dir: Path,
) -> str:
    lines: list[str] = []
    lines.append(f"# Role: {role.value}")
    lines.append(ROLE_PROMPTS[role])
    lines.append("")
    lines.append("## Loaded skills")
    for skill in ROLE_SKILLS[role]:
        lines.append(load_skill_block(skills_dir, skill))
    lines.append("")
    lines.append(f"## Task {task.id}: {task.title}")
    lines.append(task.body.strip())
    lines.append("")
    lines.append("## Definition of Done")
    for crit in task.dod:
        lines.append(f"- {crit}")

    if manifest is not None:
        lines.append("")
        lines.append("## Context (from manifest)")
        ctx = manifest.get("context")
        if not isinstance(ctx, dict):
            ctx = {}
        for f in ctx.get("source_files", []):
            lines.append(f"- {f}")

    if kb_entries:
        lines.append("")
        lines.append("## Known issues (knowledge base)")
        for e in kb_entries:
            lines.append(f"- {e.get('id')}: {e.get('title')}")

    if feedback:
        lines.append("")
        lines.append("## Feedback to address")
        lines.append(feedback)

    return "\n".join(lines)
```

- [ ] **Step 4: Run to verify `test_prompts.py` passes, then update `nodes.py`'s tests (RED)**

Run: `uv run pytest tests/unit/orchestrator/test_prompts.py -v` -> 5 passed.

Replace `tests/unit/orchestrator/test_nodes_context_dev.py` in full:

```python
import pytest
from pathlib import Path
from factory.orchestrator.types import AgentRole, AgentResult, NodeOutcome
from factory.orchestrator.ledger import Task
from factory.orchestrator.backends import FakeAgentBackend, FakeGateRunner
from factory.orchestrator.nodes import run_context_gatherer, run_dev
from factory.orchestrator.status import FakeStatusReporter
from ._skill_fixtures import write_skill_stubs

pytestmark = pytest.mark.unit


def _task():
    return Task("T-001", "t", "todo", ["c"], "body", Path("t"))


def _manifest(tmp_path, proven=True, reject=None):
    (tmp_path / "tasks").mkdir(exist_ok=True)
    (tmp_path / "tasks" / "T-001.md").write_text("dod", encoding="utf-8")
    return {
        "task_id": "T-001", "generated_by": "context-gatherer",
        "generated_at": "2026-07-16T14:32:10Z",
        "coherence": {"proven": proven, "checks": [{"name": "x", "pass": proven}]},
        "context": {"task": "tasks/T-001.md", "source_files": [], "skills": []},
        "reject": reject,
    }


def test_context_gatherer_pass(tmp_path):
    write_skill_stubs(tmp_path)
    b = FakeAgentBackend({AgentRole.CONTEXT_GATHERER: [AgentResult(True, _manifest(tmp_path))]})
    outcome, manifest, ev = run_context_gatherer(b, _task(), tmp_path)
    assert outcome == NodeOutcome.PASS and manifest is not None and ev.result == "pass"


def test_context_gatherer_reject_on_reject_field(tmp_path):
    write_skill_stubs(tmp_path)
    m = _manifest(tmp_path, proven=False, reject={"reason": "DoD unclear"})
    b = FakeAgentBackend({AgentRole.CONTEXT_GATHERER: [AgentResult(True, m)]})
    outcome, manifest, ev = run_context_gatherer(b, _task(), tmp_path)
    assert outcome == NodeOutcome.REJECT and manifest is None


def test_dev_passes_when_unit_green(tmp_path):
    write_skill_stubs(tmp_path)
    b = FakeAgentBackend({AgentRole.DEV: [AgentResult(True, {})]})
    g = FakeGateRunner({"unit": [0]})
    outcome, ev = run_dev(b, g, _task(), {}, [], tmp_path)
    assert outcome == NodeOutcome.PASS


def test_dev_escalates_when_unit_never_green(tmp_path):
    write_skill_stubs(tmp_path)
    b = FakeAgentBackend({AgentRole.DEV: [AgentResult(True, {}) for _ in range(3)]})
    g = FakeGateRunner({"unit": [1, 1, 1]})
    outcome, ev = run_dev(b, g, _task(), {}, [], tmp_path, max_iters=3)
    assert outcome == NodeOutcome.ESCALATE and ev.attempts == 3


def test_context_gatherer_notes_backend_failure(tmp_path):
    write_skill_stubs(tmp_path)
    b = FakeAgentBackend({AgentRole.CONTEXT_GATHERER: [
        AgentResult(False, {}, "simulated backend failure"),
        AgentResult(False, {}, "simulated backend failure"),
    ]})
    outcome, manifest, ev = run_context_gatherer(b, _task(), tmp_path)
    assert outcome == NodeOutcome.REJECT and manifest is None
    assert ev.extra["backend_ok"] is False
    assert ev.extra["backend_raw"] == "simulated backend failure"


def test_dev_notes_backend_failure_on_escalate(tmp_path):
    write_skill_stubs(tmp_path)
    b = FakeAgentBackend({AgentRole.DEV: [
        AgentResult(False, {}, "simulated backend failure") for _ in range(3)
    ]})
    g = FakeGateRunner({"unit": [1, 1, 1]})
    outcome, ev = run_dev(b, g, _task(), {}, [], tmp_path, max_iters=3)
    assert outcome == NodeOutcome.ESCALATE
    assert ev.extra["backend_ok"] is False
    assert ev.extra["backend_raw"] == "simulated backend failure"


def test_dev_does_not_note_backend_failure_when_ok(tmp_path):
    write_skill_stubs(tmp_path)
    b = FakeAgentBackend({AgentRole.DEV: [AgentResult(True, {})]})
    g = FakeGateRunner({"unit": [0]})
    outcome, ev = run_dev(b, g, _task(), {}, [], tmp_path)
    assert outcome == NodeOutcome.PASS
    assert "backend_ok" not in ev.extra


def test_context_gatherer_reports_running_each_attempt(tmp_path):
    write_skill_stubs(tmp_path)
    status = FakeStatusReporter()
    b = FakeAgentBackend({AgentRole.CONTEXT_GATHERER: [AgentResult(True, _manifest(tmp_path))]})
    run_context_gatherer(b, _task(), tmp_path, status=status)
    assert status.calls[0]["node"] == "context-gather"
    assert status.calls[0]["node_state"] == "running"
    assert status.calls[0]["attempt"] == 1
    assert status.calls[0]["max_attempts"] == 2


def test_dev_reports_running_each_attempt_and_passes_on_snippet(tmp_path):
    write_skill_stubs(tmp_path)
    status = FakeStatusReporter()

    class SnippetCapturingBackend:
        def run(self, role, prompt, on_snippet=None):
            if on_snippet is not None:
                on_snippet("partial output")
            return AgentResult(True, {})

    b = SnippetCapturingBackend()
    g = FakeGateRunner({"unit": [0]})
    run_dev(b, g, _task(), {}, [], tmp_path, status=status)
    assert status.calls[0]["node"] == "dev"
    assert status.calls[0]["node_state"] == "running"
    snippets = [c["snippet"] for c in status.calls if c["snippet"]]
    assert snippets == ["partial output"]
```

Replace `tests/unit/orchestrator/test_nodes_val_review.py` in full:

```python
import pytest
from pathlib import Path
from factory.orchestrator.types import AgentRole, AgentResult, NodeOutcome
from factory.orchestrator.ledger import Task
from factory.orchestrator.backends import FakeAgentBackend, FakeGateRunner
from factory.orchestrator.nodes import run_validation, run_review
from factory.orchestrator.status import FakeStatusReporter
from ._skill_fixtures import write_skill_stubs

pytestmark = pytest.mark.unit


def _task():
    return Task("T-001", "t", "todo", ["c"], "body", Path("t"))


def test_validation_pass_and_fail():
    assert run_validation(FakeGateRunner({"sim": [0]}))[0] == NodeOutcome.PASS
    assert run_validation(FakeGateRunner({"sim": [1]}))[0] == NodeOutcome.FAIL


def test_review_pass_requires_green_gate_and_dod_and_no_findings(tmp_path):
    write_skill_stubs(tmp_path)
    b = FakeAgentBackend({AgentRole.REVIEW: [AgentResult(True, {"dod_met": True, "findings": []})]})
    outcome, ev, findings = run_review(b, FakeGateRunner({"full": [0]}), _task(), tmp_path)
    assert outcome == NodeOutcome.PASS and findings == []


def test_review_changes_when_findings_present(tmp_path):
    write_skill_stubs(tmp_path)
    b = FakeAgentBackend({AgentRole.REVIEW: [AgentResult(True, {"dod_met": True, "findings": ["DRY: dup"]})]})
    outcome, ev, findings = run_review(b, FakeGateRunner({"full": [0]}), _task(), tmp_path)
    assert outcome == NodeOutcome.CHANGES and findings == ["DRY: dup"]


def test_review_changes_when_gate_red_even_if_dod_claimed(tmp_path):
    write_skill_stubs(tmp_path)
    b = FakeAgentBackend({AgentRole.REVIEW: [AgentResult(True, {"dod_met": True, "findings": []})]})
    outcome, ev, findings = run_review(b, FakeGateRunner({"full": [1]}), _task(), tmp_path)
    assert outcome == NodeOutcome.CHANGES  # cannot self-certify past a red gate


def test_review_notes_backend_failure(tmp_path):
    write_skill_stubs(tmp_path)
    b = FakeAgentBackend({AgentRole.REVIEW: [AgentResult(False, {}, "simulated backend failure")]})
    outcome, ev, findings = run_review(b, FakeGateRunner({"full": [0]}), _task(), tmp_path)
    assert outcome == NodeOutcome.CHANGES
    assert ev.extra["backend_ok"] is False
    assert ev.extra["backend_raw"] == "simulated backend failure"


def test_review_does_not_note_backend_failure_when_ok(tmp_path):
    write_skill_stubs(tmp_path)
    b = FakeAgentBackend({AgentRole.REVIEW: [AgentResult(True, {"dod_met": True, "findings": []})]})
    outcome, ev, findings = run_review(b, FakeGateRunner({"full": [0]}), _task(), tmp_path)
    assert outcome == NodeOutcome.PASS
    assert "backend_ok" not in ev.extra


def test_validation_reports_running():
    status = FakeStatusReporter()
    run_validation(FakeGateRunner({"sim": [0]}), "T-001", status=status)
    assert status.calls[0]["node"] == "validation"
    assert status.calls[0]["node_state"] == "running"
    assert status.calls[0]["task_id"] == "T-001"


def test_review_reports_running(tmp_path):
    write_skill_stubs(tmp_path)
    status = FakeStatusReporter()
    b = FakeAgentBackend({AgentRole.REVIEW: [AgentResult(True, {"dod_met": True, "findings": []})]})
    run_review(b, FakeGateRunner({"full": [0]}), _task(), tmp_path, status=status)
    assert status.calls[0]["node"] == "review"
    assert status.calls[0]["node_state"] == "running"
```

- [ ] **Step 5: Run to verify these fail**

Run: `uv run pytest tests/unit/orchestrator/test_nodes_context_dev.py tests/unit/orchestrator/test_nodes_val_review.py -v`
Expected: FAIL -- `run_dev()`/`run_review()` don't accept a `repo_root` positional argument yet.

- [ ] **Step 6: Update `nodes.py`**

In `src/factory/orchestrator/nodes.py`:

Replace:
```python
def run_context_gatherer(
    backend: AgentBackend,
    task: Task,
    repo_root: Path,
    max_attempts: int = 2,
    status: StatusReporter = NullStatusReporter(),
) -> tuple[NodeOutcome, dict | None, NodeEvent]:
```
with (unchanged signature, only the body's `compose_prompt` call changes):
```python
def run_context_gatherer(
    backend: AgentBackend,
    task: Task,
    repo_root: Path,
    max_attempts: int = 2,
    status: StatusReporter = NullStatusReporter(),
) -> tuple[NodeOutcome, dict | None, NodeEvent]:
```
(no signature change here -- `repo_root` was already present)

Replace:
```python
        result = backend.run(
            AgentRole.CONTEXT_GATHERER, compose_prompt(AgentRole.CONTEXT_GATHERER, task),
            on_snippet=_on_snippet,
        )
```
with:
```python
        result = backend.run(
            AgentRole.CONTEXT_GATHERER,
            compose_prompt(AgentRole.CONTEXT_GATHERER, task, skills_dir=repo_root / ".pi" / "skills"),
            on_snippet=_on_snippet,
        )
```

Replace:
```python
def run_dev(
    backend: AgentBackend,
    gates: GateRunner,
    task: Task,
    manifest: dict,
    kb_entries: list[dict],
    max_iters: int = 3,
    feedback: str | None = None,
    status: StatusReporter = NullStatusReporter(),
) -> tuple[NodeOutcome, NodeEvent]:
```
with:
```python
def run_dev(
    backend: AgentBackend,
    gates: GateRunner,
    task: Task,
    manifest: dict,
    kb_entries: list[dict],
    repo_root: Path,
    max_iters: int = 3,
    feedback: str | None = None,
    status: StatusReporter = NullStatusReporter(),
) -> tuple[NodeOutcome, NodeEvent]:
```

Replace:
```python
        result = backend.run(
            AgentRole.DEV, compose_prompt(AgentRole.DEV, task, manifest, kb_entries, feedback),
            on_snippet=_on_snippet,
        )
```
with:
```python
        result = backend.run(
            AgentRole.DEV,
            compose_prompt(
                AgentRole.DEV, task, manifest, kb_entries, feedback,
                skills_dir=repo_root / ".pi" / "skills",
            ),
            on_snippet=_on_snippet,
        )
```

Replace:
```python
def run_review(
    backend: AgentBackend,
    gates: GateRunner,
    task: Task,
    status: StatusReporter = NullStatusReporter(),
) -> tuple[NodeOutcome, NodeEvent, list[str]]:
```
with:
```python
def run_review(
    backend: AgentBackend,
    gates: GateRunner,
    task: Task,
    repo_root: Path,
    status: StatusReporter = NullStatusReporter(),
) -> tuple[NodeOutcome, NodeEvent, list[str]]:
```

Replace:
```python
    result = backend.run(AgentRole.REVIEW, compose_prompt(AgentRole.REVIEW, task), on_snippet=_on_snippet)
```
with:
```python
    result = backend.run(
        AgentRole.REVIEW,
        compose_prompt(AgentRole.REVIEW, task, skills_dir=repo_root / ".pi" / "skills"),
        on_snippet=_on_snippet,
    )
```

- [ ] **Step 7: Run to verify `nodes.py`'s own tests pass, then update `runner.py`'s call sites (RED for `run_task`'s tests)**

Run: `uv run pytest tests/unit/orchestrator/test_nodes_context_dev.py tests/unit/orchestrator/test_nodes_val_review.py -v` -> all pass.

In `src/factory/orchestrator/runner.py`, replace:
```python
        d_outcome, d_ev = run_dev(
            backend, gates, task, manifest, kb_entries, max_dev_iters, feedback, status=status
        )
```
with:
```python
        d_outcome, d_ev = run_dev(
            backend, gates, task, manifest, kb_entries, repo_root, max_dev_iters, feedback, status=status
        )
```

Replace:
```python
        r_outcome, r_ev, findings = run_review(backend, gates, task, status=status)
```
with:
```python
        r_outcome, r_ev, findings = run_review(backend, gates, task, repo_root, status=status)
```

- [ ] **Step 8: Update the run_task/run_next end-to-end tests to write skill stubs**

In `tests/unit/orchestrator/test_runner_e2e.py`, add the import and update `_repo`:

Replace:
```python
import pytest
from factory.orchestrator.types import AgentRole, AgentResult
from factory.orchestrator.ledger import Task
from factory.orchestrator.backends import FakeAgentBackend, FakeGateRunner
from factory.orchestrator.runner import run_task
from factory.orchestrator.status import FakeStatusReporter

pytestmark = pytest.mark.unit


def _repo(tmp_path):
    (tmp_path / "tasks").mkdir()
    (tmp_path / "tasks" / "T-001.md").write_text("dod", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "x.py").write_text("x = 1\n", encoding="utf-8")
    return tmp_path
```
with:
```python
import pytest
from factory.orchestrator.types import AgentRole, AgentResult
from factory.orchestrator.ledger import Task
from factory.orchestrator.backends import FakeAgentBackend, FakeGateRunner
from factory.orchestrator.runner import run_task
from factory.orchestrator.status import FakeStatusReporter
from ._skill_fixtures import write_skill_stubs

pytestmark = pytest.mark.unit


def _repo(tmp_path):
    (tmp_path / "tasks").mkdir()
    (tmp_path / "tasks" / "T-001.md").write_text("dod", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "x.py").write_text("x = 1\n", encoding="utf-8")
    write_skill_stubs(tmp_path)
    return tmp_path
```

In `tests/unit/orchestrator/test_run_next.py`, apply the same two changes (add the import, add `write_skill_stubs(tmp_path)` to `_repo`):

Replace:
```python
import json
import pytest
from factory.orchestrator.types import AgentRole, AgentResult
from factory.orchestrator.backends import FakeAgentBackend, FakeGateRunner
from factory.orchestrator.ledger import load_tasks
from factory.orchestrator.runner import run_next
from factory.orchestrator.status import FakeStatusReporter

pytestmark = pytest.mark.unit


def _repo(tmp_path):
    (tmp_path / "tasks").mkdir()
    (tmp_path / "tasks" / "T-001.md").write_text(
        "---\nid: T-001\ntitle: t\nstatus: todo\ndod:\n  - c\n---\nbody\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "x.py").write_text("x = 1\n", encoding="utf-8")
    return tmp_path
```
with:
```python
import json
import pytest
from factory.orchestrator.types import AgentRole, AgentResult
from factory.orchestrator.backends import FakeAgentBackend, FakeGateRunner
from factory.orchestrator.ledger import load_tasks
from factory.orchestrator.runner import run_next
from factory.orchestrator.status import FakeStatusReporter
from ._skill_fixtures import write_skill_stubs

pytestmark = pytest.mark.unit


def _repo(tmp_path):
    (tmp_path / "tasks").mkdir()
    (tmp_path / "tasks" / "T-001.md").write_text(
        "---\nid: T-001\ntitle: t\nstatus: todo\ndod:\n  - c\n---\nbody\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "x.py").write_text("x = 1\n", encoding="utf-8")
    write_skill_stubs(tmp_path)
    return tmp_path
```

- [ ] **Step 9: Run the full orchestrator unit suite**

Run: `uv run pytest tests/unit/orchestrator -q`
Expected: all pass (test count unchanged except +1 for the new `test_compose_prompt_requires_every_vendored_skill_to_exist`).

- [ ] **Step 10: Commit**

```bash
git add src/factory/orchestrator/prompts.py src/factory/orchestrator/nodes.py src/factory/orchestrator/runner.py tests/unit/orchestrator/test_prompts.py tests/unit/orchestrator/test_nodes_context_dev.py tests/unit/orchestrator/test_nodes_val_review.py tests/unit/orchestrator/test_run_next.py tests/unit/orchestrator/test_runner_e2e.py
git commit -m "feat: hard-load full skill content into every sub-agent role's prompt"
```

---

### Task 3: Vendor `brainstorming`/`writing-plans`; lock all 10 skills to hard-loading only

**Files:**
- Create: `.pi/skills/brainstorming/SKILL.md`
- Create: `.pi/skills/writing-plans/SKILL.md`
- Modify: all 8 existing `.pi/skills/*/SKILL.md` files (frontmatter only)

**Interfaces:**
- Consumes: nothing.
- Produces: two new vendored skills; all 10 skills marked `disable-model-invocation: true`.

- [ ] **Step 1: Add `disable-model-invocation: true` to each of the 8 existing skills' frontmatter**

For each of `.pi/skills/coding-principles/SKILL.md`, `.pi/skills/context-completeness-audit/SKILL.md`, `.pi/skills/kb-lookup/SKILL.md`, `.pi/skills/receiving-code-review/SKILL.md`, `.pi/skills/requesting-code-review/SKILL.md`, `.pi/skills/systematic-debugging/SKILL.md`, `.pi/skills/test-driven-development/SKILL.md`, `.pi/skills/verification-before-completion/SKILL.md`:

Add one line, `disable-model-invocation: true`, to the file's YAML frontmatter block (between `---` markers), e.g. for `systematic-debugging`:

```yaml
---
name: systematic-debugging
description: Use when encountering any bug, test failure, or unexpected behavior, before proposing fixes
disable-model-invocation: true
---
```

Apply the same one-line addition to the other 7 files, preserving each file's existing `name`/`description` values exactly as they are today.

- [ ] **Step 2: Vendor `brainstorming`**

Copy the content of the local superpowers plugin's `brainstorming/SKILL.md` (the same content already loaded into this session earlier as the `superpowers:brainstorming` skill instructions) into `.pi/skills/brainstorming/SKILL.md`, with two adaptations:
1. Add `disable-model-invocation: true` to its frontmatter.
2. Remove the entire "Visual Companion" section (the browser-based mockup tool has no equivalent in `pi`) and its bullet in the Checklist ("Offer the visual companion just-in-time").

- [ ] **Step 3: Vendor `writing-plans`**

Copy the content of the local superpowers plugin's `writing-plans/SKILL.md` (already loaded into this session earlier) into `.pi/skills/writing-plans/SKILL.md`, adding `disable-model-invocation: true` to its frontmatter. No other content changes needed -- it has no Claude-Code-specific mechanics to remove.

- [ ] **Step 4: Verify pi's real skill loader still finds all 10 with the new frontmatter field**

```bash
cd C:/coding/cool_physical_ai_project
node -e "
const { loadSkills } = require('@earendil-works/pi-coding-agent');
" 2>&1 || true
```
(This package is ESM-only per `pi-ext/factory-watch/package.json`'s `\"type\": \"module\"` -- if the inline `node -e` `require` fails with an ESM error, that's expected and not a real check failure.) Instead verify via the existing extension's own test suite, which already exercises `loadSkills` indirectly once Task 7 lands; for now, just confirm no skill file is malformed YAML:

```bash
uv run python -c "
import frontmatter
from pathlib import Path
for p in sorted(Path('.pi/skills').glob('*/SKILL.md')):
    post = frontmatter.load(str(p))
    assert post.get('disable-model-invocation') is True, p
    print(p, '->', post.get('name'))
"
```
Expected: 10 lines printed, one per skill directory, no assertion error.

- [ ] **Step 5: Run the full gate to confirm nothing else broke**

Run: `uv run python scripts/gates/all.py; echo "exit=$?"`
Expected: exit=0.

- [ ] **Step 6: Commit**

```bash
git add .pi/skills/
git commit -m "feat: vendor brainstorming/writing-plans; lock all skills to hard-loading only"
```

---

### Task 4: `ledger.py` -- `get_task`, `TaskNotFoundError`, `TaskNotTodoError`

**Files:**
- Modify: `src/factory/orchestrator/ledger.py`
- Test: `tests/unit/orchestrator/test_ledger.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `get_task(tasks: list[Task], task_id: str) -> Task | None`; `TaskNotFoundError(RuntimeError)`; `TaskNotTodoError(RuntimeError)`.

- [ ] **Step 1: Write the failing test**

Add to the end of `tests/unit/orchestrator/test_ledger.py`:

```python
from factory.orchestrator.ledger import TaskNotFoundError, TaskNotTodoError, get_task


def test_get_task_found():
    tasks = [_task("T-001", "a", "todo"), _task("T-002", "b", "done")]
    assert get_task(tasks, "T-002").title == "b"


def test_get_task_not_found_returns_none():
    tasks = [_task("T-001", "a", "todo")]
    assert get_task(tasks, "T-999") is None


def test_task_not_found_error_message():
    err = TaskNotFoundError("T-999")
    assert err.task_id == "T-999"
    assert "T-999" in str(err)


def test_task_not_todo_error_message():
    err = TaskNotTodoError("T-001", "done")
    assert err.task_id == "T-001"
    assert err.status == "done"
    assert "T-001" in str(err) and "done" in str(err)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/orchestrator/test_ledger.py -v`
Expected: FAIL -- `ImportError: cannot import name 'get_task'`.

- [ ] **Step 3: Implement in `src/factory/orchestrator/ledger.py`**

Add, after the existing `next_todo` function:

```python
def get_task(tasks: list[Task], task_id: str) -> Task | None:
    return next((t for t in tasks if t.id == task_id), None)


class TaskNotFoundError(RuntimeError):
    def __init__(self, task_id: str) -> None:
        super().__init__(f"task not found: {task_id}")
        self.task_id = task_id


class TaskNotTodoError(RuntimeError):
    def __init__(self, task_id: str, status: str) -> None:
        super().__init__(f"task {task_id} is not todo (status: {status})")
        self.task_id = task_id
        self.status = status
```

- [ ] **Step 4: Run to pass**

Run: `uv run pytest tests/unit/orchestrator/test_ledger.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/factory/orchestrator/ledger.py tests/unit/orchestrator/test_ledger.py
git commit -m "feat: get_task lookup and task-targeting errors in the ledger"
```

---

### Task 5: `run_next(task_id=...)` -- target one specific task

**Files:**
- Modify: `src/factory/orchestrator/runner.py`
- Test: `tests/unit/orchestrator/test_run_next.py`

**Interfaces:**
- Consumes: `get_task`, `TaskNotFoundError`, `TaskNotTodoError` (Task 4).
- Produces: `run_next(..., task_id: str | None = None) -> Path | None`.

- [ ] **Step 1: Write the failing tests**

At the top of `tests/unit/orchestrator/test_run_next.py`, add one import line alongside the existing ones:
```python
from factory.orchestrator.ledger import TaskNotFoundError, TaskNotTodoError
```

Then add these three test functions to the end of the file:

```python
def test_run_next_targets_specific_task_id(tmp_path):
    repo = _repo(tmp_path)
    (repo / "tasks" / "T-002.md").write_text(
        "---\nid: T-002\ntitle: second\nstatus: todo\ndod:\n  - c\n---\nbody\n", encoding="utf-8")
    path = run_next(repo, FakeAgentBackend(_scripts()), FakeGateRunner(),
                    session_id="s1", git_info={"branch": "main"}, task_id="T-002")
    assert path and path.exists()
    tasks = {t.id: t.status for t in load_tasks(repo / "tasks")}
    assert tasks["T-002"] == "done"
    assert tasks["T-001"] == "todo"  # untouched -- T-002 was targeted, not T-001


def test_run_next_raises_for_unknown_task_id(tmp_path):
    repo = _repo(tmp_path)
    with pytest.raises(TaskNotFoundError):
        run_next(repo, FakeAgentBackend({}), FakeGateRunner(), session_id="s1", task_id="T-999")


def test_run_next_raises_for_non_todo_task_id(tmp_path):
    repo = _repo(tmp_path)
    (repo / "tasks" / "T-001.md").write_text(
        "---\nid: T-001\ntitle: t\nstatus: done\ndod:\n  - c\n---\nbody\n", encoding="utf-8")
    with pytest.raises(TaskNotTodoError):
        run_next(repo, FakeAgentBackend({}), FakeGateRunner(), session_id="s1", task_id="T-001")
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/orchestrator/test_run_next.py -v`
Expected: FAIL -- `run_next() got an unexpected keyword argument 'task_id'`.

- [ ] **Step 3: Implement in `src/factory/orchestrator/runner.py`**

Replace:
```python
def run_next(
    repo_root: Path,
    backend: AgentBackend,
    gates: GateRunner,
    *,
    # Finding 3 (final review), corrected 2026-07-20: PiAgentBackend DOES pass
    # --provider/--model through to the real `pi` CLI when the caller supplies
    # them (see pi_backend.py's _build_command, and __main__.py's --provider/
    # --model flags) -- verified live via `pi -p` with an explicit override.
    # This default only covers the case where the caller supplies neither, in
    # which case the run falls back to Pi's own ambient/default model
    # selection, so "pi:unspecified" still honestly labels that fallback path
    # (as opposed to a model that was actively chosen but not recorded).
    model_backend: str = "pi:unspecified",
    session_id: str | None = None,
    git_info: dict | None = None,
    status: StatusReporter = NullStatusReporter(),
) -> Path | None:
    tasks = load_tasks(repo_root / "tasks")
    task = next_todo(tasks)
    if task is None:
        return None
```
with:
```python
def run_next(
    repo_root: Path,
    backend: AgentBackend,
    gates: GateRunner,
    *,
    # Finding 3 (final review), corrected 2026-07-20: PiAgentBackend DOES pass
    # --provider/--model through to the real `pi` CLI when the caller supplies
    # them (see pi_backend.py's _build_command, and __main__.py's --provider/
    # --model flags) -- verified live via `pi -p` with an explicit override.
    # This default only covers the case where the caller supplies neither, in
    # which case the run falls back to Pi's own ambient/default model
    # selection, so "pi:unspecified" still honestly labels that fallback path
    # (as opposed to a model that was actively chosen but not recorded).
    model_backend: str = "pi:unspecified",
    session_id: str | None = None,
    git_info: dict | None = None,
    status: StatusReporter = NullStatusReporter(),
    task_id: str | None = None,
) -> Path | None:
    tasks = load_tasks(repo_root / "tasks")
    if task_id is not None:
        task = get_task(tasks, task_id)
        if task is None:
            raise TaskNotFoundError(task_id)
        if task.status != "todo":
            raise TaskNotTodoError(task_id, task.status)
    else:
        task = next_todo(tasks)
        if task is None:
            return None
```

And update the import line:
```python
from factory.orchestrator.ledger import Task, load_tasks, next_todo, set_status
```
becomes:
```python
from factory.orchestrator.ledger import (
    Task,
    TaskNotFoundError,
    TaskNotTodoError,
    get_task,
    load_tasks,
    next_todo,
    set_status,
)
```

- [ ] **Step 4: Run to pass**

Run: `uv run pytest tests/unit/orchestrator/test_run_next.py -v`
Expected: all pass (6 tests: 3 existing + 3 new).

- [ ] **Step 5: Commit**

```bash
git add src/factory/orchestrator/runner.py tests/unit/orchestrator/test_run_next.py
git commit -m "feat: run_next(task_id=...) to target one specific task"
```

---

### Task 6: `__main__.py` -- `--task` on `run`, `--json` on `list`

**Files:**
- Modify: `src/factory/orchestrator/__main__.py`
- Test: `tests/unit/orchestrator/test_main.py`

**Interfaces:**
- Consumes: `run_next(task_id=...)` (Task 5).
- Produces: `factory.orchestrator run --task <id>`; `factory.orchestrator list --json`.

- [ ] **Step 1: Write the failing tests**

Add to the end of `tests/unit/orchestrator/test_main.py`:

```python
def test_main_run_passes_task_id_through(tmp_path, monkeypatch):
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    (tmp_path / "tasks").mkdir()

    monkeypatch.setattr(
        sys, "argv",
        ["factory.orchestrator", "run", "--repo", str(tmp_path), "--task", "T-042"],
    )

    captured = {}

    def fake_run_next(*args, **kwargs):
        captured["task_id"] = kwargs.get("task_id")
        return None

    monkeypatch.setattr("factory.orchestrator.__main__.run_next", fake_run_next)
    main()
    assert captured["task_id"] == "T-042"


def test_main_list_json_outputs_structured_tasks(tmp_path, monkeypatch, capsys):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "T-001-a.md").write_text(
        "---\nid: T-001\ntitle: Example task\nstatus: todo\ndod:\n  - x\n---\nbody\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(sys, "argv", ["factory.orchestrator", "list", "--repo", str(tmp_path), "--json"])
    main()

    out = json.loads(capsys.readouterr().out)
    assert out == [{"id": "T-001", "title": "Example task", "status": "todo"}]
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/orchestrator/test_main.py -v`
Expected: FAIL -- `error: unrecognized arguments: --task T-042`.

- [ ] **Step 3: Implement in `src/factory/orchestrator/__main__.py`**

Replace:
```python
from __future__ import annotations

import argparse
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from factory.orchestrator.backends import SubprocessGateRunner
from factory.orchestrator.ledger import format_task_board, load_tasks
from factory.orchestrator.lock import AlreadyRunningError, acquire_lock, remove_lock
from factory.orchestrator.pi_backend import PiAgentBackend
from factory.orchestrator.runner import run_next
from factory.orchestrator.status import FileStatusReporter
```
with:
```python
from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from factory.orchestrator.backends import SubprocessGateRunner
from factory.orchestrator.ledger import format_task_board, load_tasks
from factory.orchestrator.lock import AlreadyRunningError, acquire_lock, remove_lock
from factory.orchestrator.pi_backend import PiAgentBackend
from factory.orchestrator.runner import run_next
from factory.orchestrator.status import FileStatusReporter
```

Replace:
```python
    parser.add_argument("command", choices=["run", "list"])
    parser.add_argument("--repo", default=".")
    parser.add_argument("--provider", default=None, help="Pi provider, e.g. openrouter")
    parser.add_argument("--model", default=None, help="Pi model id, e.g. anthropic/claude-opus-4")
    args = parser.parse_args()

    repo_root = Path(args.repo).resolve()

    if args.command == "list":
        print(format_task_board(load_tasks(repo_root / "tasks")))
        return
```
with:
```python
    parser.add_argument("command", choices=["run", "list"])
    parser.add_argument("--repo", default=".")
    parser.add_argument("--provider", default=None, help="Pi provider, e.g. openrouter")
    parser.add_argument("--model", default=None, help="Pi model id, e.g. anthropic/claude-opus-4")
    parser.add_argument("--task", default=None, help="Task id to run (default: next todo task)")
    parser.add_argument("--json", action="store_true", help="list command only: output tasks as JSON")
    args = parser.parse_args()

    repo_root = Path(args.repo).resolve()

    if args.command == "list":
        tasks = load_tasks(repo_root / "tasks")
        if args.json:
            print(json.dumps([{"id": t.id, "title": t.title, "status": t.status} for t in tasks]))
        else:
            print(format_task_board(tasks))
        return
```

Replace:
```python
        path = run_next(
            repo_root, backend, gates, git_info=_git_info(repo_root),
            session_id=session_id, status=status, **kwargs,
        )
```
with:
```python
        path = run_next(
            repo_root, backend, gates, git_info=_git_info(repo_root),
            session_id=session_id, status=status, task_id=args.task, **kwargs,
        )
```

- [ ] **Step 4: Run to pass**

Run: `uv run pytest tests/unit/orchestrator/test_main.py -v`
Expected: all pass (4 tests: 2 existing + 2 new).

- [ ] **Step 5: Run the full gate**

Run: `uv run python scripts/gates/all.py; echo "exit=$?"`
Expected: exit=0.

- [ ] **Step 6: Commit**

```bash
git add src/factory/orchestrator/__main__.py tests/unit/orchestrator/test_main.py
git commit -m "feat: --task on run, --json on list in the orchestrator CLI"
```

---

### Task 7: `plan_to_tasks` -- pure plan.md parser

**Files:**
- Create: `src/factory/orchestrator/plan_to_tasks.py`
- Test: `tests/unit/test_plan_to_tasks.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `ParsedPlanTask` dataclass; `parse_plan_tasks(text: str) -> list[ParsedPlanTask]` (pure).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_plan_to_tasks.py
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_plan_to_tasks.py -v`
Expected: FAIL -- `factory.orchestrator.plan_to_tasks` module not found.

- [ ] **Step 3: Implement `src/factory/orchestrator/plan_to_tasks.py`**

```python
from __future__ import annotations

import re
from dataclasses import dataclass

_TASK_HEADER = re.compile(r"^### Task (\d+): (.+)$", re.MULTILINE)
_FILES_BLOCK = re.compile(r"\*\*Files:\*\*\n(.*?)(?=\n\n\*\*Interfaces:\*\*)", re.DOTALL)
_PRODUCES_LINE = re.compile(r"^- Produces:\s*(.+)$", re.MULTILINE)


@dataclass
class ParsedPlanTask:
    number: int
    title: str
    files_block: str
    produces: list[str]


def parse_plan_tasks(text: str) -> list[ParsedPlanTask]:
    """Parse every `### Task N: Title` section out of a writing-plans-format
    plan document. Pure: no file I/O, no side effects. Returns an empty list
    if no task sections are found -- callers decide whether that's an error.
    """
    headers = list(_TASK_HEADER.finditer(text))
    tasks: list[ParsedPlanTask] = []
    for i, m in enumerate(headers):
        start = m.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        chunk = text[start:end]

        files_match = _FILES_BLOCK.search(chunk)
        files_block = files_match.group(1).strip() if files_match else ""
        produces = [p.strip() for p in _PRODUCES_LINE.findall(chunk)]

        tasks.append(
            ParsedPlanTask(
                number=int(m.group(1)),
                title=m.group(2).strip(),
                files_block=files_block,
                produces=produces,
            )
        )
    return tasks
```

- [ ] **Step 4: Run to pass**

Run: `uv run pytest tests/unit/test_plan_to_tasks.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/factory/orchestrator/plan_to_tasks.py tests/unit/test_plan_to_tasks.py
git commit -m "feat: pure plan.md task-section parser"
```

---

### Task 8: `plan_to_tasks` -- CLI wrapper (id assignment, idempotency, file writing)

**Files:**
- Modify: `src/factory/orchestrator/plan_to_tasks.py`
- Modify: `tests/unit/test_plan_to_tasks.py`

**Interfaces:**
- Consumes: `parse_plan_tasks` (Task 7).
- Produces: `run(plan_path: Path, repo_root: Path) -> list[str]`; `NoTasksFoundError`; CLI entry `main()`, invoked as `uv run python -m factory.orchestrator.plan_to_tasks <plan-file> [--repo .]`.

- [ ] **Step 1: Write the failing tests**

Add to the end of `tests/unit/test_plan_to_tasks.py`:

```python
import frontmatter
from pathlib import Path
from factory.orchestrator.plan_to_tasks import NoTasksFoundError, run


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
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_plan_to_tasks.py -v`
Expected: FAIL -- `ImportError: cannot import name 'run'`.

- [ ] **Step 3: Implement the rest of `src/factory/orchestrator/plan_to_tasks.py`**

Replace the whole file:

```python
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import frontmatter

_TASK_HEADER = re.compile(r"^### Task (\d+): (.+)$", re.MULTILINE)
_FILES_BLOCK = re.compile(r"\*\*Files:\*\*\n(.*?)(?=\n\n\*\*Interfaces:\*\*)", re.DOTALL)
_PRODUCES_LINE = re.compile(r"^- Produces:\s*(.+)$", re.MULTILINE)
_ID_RE = re.compile(r"^T-(\d+)$")

_FIXED_DOD_ITEM = "All steps in this task complete; tests/gates pass; committed"


@dataclass
class ParsedPlanTask:
    number: int
    title: str
    files_block: str
    produces: list[str]


class NoTasksFoundError(RuntimeError):
    def __init__(self, plan_path: str) -> None:
        super().__init__(f"no '### Task N:' sections found in {plan_path}")
        self.plan_path = plan_path


def parse_plan_tasks(text: str) -> list[ParsedPlanTask]:
    """Parse every `### Task N: Title` section out of a writing-plans-format
    plan document. Pure: no file I/O, no side effects. Returns an empty list
    if no task sections are found -- callers decide whether that's an error.
    """
    headers = list(_TASK_HEADER.finditer(text))
    tasks: list[ParsedPlanTask] = []
    for i, m in enumerate(headers):
        start = m.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        chunk = text[start:end]

        files_match = _FILES_BLOCK.search(chunk)
        files_block = files_match.group(1).strip() if files_match else ""
        produces = [p.strip() for p in _PRODUCES_LINE.findall(chunk)]

        tasks.append(
            ParsedPlanTask(
                number=int(m.group(1)),
                title=m.group(2).strip(),
                files_block=files_block,
                produces=produces,
            )
        )
    return tasks


def _slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug or "task"


def _max_existing_id(tasks_dir: Path) -> int:
    max_n = 0
    if not tasks_dir.exists():
        return max_n
    for path in tasks_dir.glob("T-*.md"):
        post = frontmatter.load(str(path))
        m = _ID_RE.match(str(post.get("id", "")))
        if m:
            max_n = max(max_n, int(m.group(1)))
    return max_n


def _already_parsed_task_numbers(tasks_dir: Path, source_plan: str) -> set[int]:
    done: set[int] = set()
    if not tasks_dir.exists():
        return done
    for path in tasks_dir.glob("T-*.md"):
        post = frontmatter.load(str(path))
        if post.get("source_plan") == source_plan and "source_task" in post.metadata:
            done.add(int(post["source_task"]))
    return done


def _write_task_file(tasks_dir: Path, task_id: str, task: ParsedPlanTask, source_plan: str) -> Path:
    dod = list(task.produces)
    dod.append(_FIXED_DOD_ITEM)
    body = f"{task.files_block}\n\nFull steps: {source_plan}, Task {task.number}.\n"
    post = frontmatter.Post(
        body,
        id=task_id,
        title=task.title,
        status="todo",
        dod=dod,
        source_plan=source_plan,
        source_task=task.number,
    )
    path = tasks_dir / f"{task_id}-{_slugify(task.title)}.md"
    path.write_text(frontmatter.dumps(post), encoding="utf-8")
    return path


def run(plan_path: Path, repo_root: Path) -> list[str]:
    """Parse plan_path and write one tasks/T-*.md per task section found.
    Returns the list of newly-created task ids (empty if this plan was
    already fully parsed -- idempotent on rerun). Raises NoTasksFoundError,
    writing nothing, if the plan has zero '### Task N:' sections."""
    text = plan_path.read_text(encoding="utf-8")
    parsed = parse_plan_tasks(text)
    if not parsed:
        raise NoTasksFoundError(str(plan_path))

    tasks_dir = repo_root / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)

    source_plan = plan_path.resolve().relative_to(repo_root.resolve()).as_posix()
    already_done = _already_parsed_task_numbers(tasks_dir, source_plan)
    next_n = _max_existing_id(tasks_dir) + 1

    created: list[str] = []
    for task in parsed:
        if task.number in already_done:
            continue
        task_id = f"T-{next_n:03d}"
        next_n += 1
        _write_task_file(tasks_dir, task_id, task, source_plan)
        created.append(task_id)
    return created


def main() -> None:
    parser = argparse.ArgumentParser(prog="factory.orchestrator.plan_to_tasks")
    parser.add_argument("plan_file")
    parser.add_argument("--repo", default=".")
    args = parser.parse_args()

    repo_root = Path(args.repo).resolve()
    plan_path = Path(args.plan_file).resolve()

    try:
        created = run(plan_path, repo_root)
    except NoTasksFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if not created:
        print("no new tasks (already parsed)")
    else:
        print("created: " + ", ".join(created))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run to pass**

Run: `uv run pytest tests/unit/test_plan_to_tasks.py -v`
Expected: all pass (9 tests: 5 from Task 7 + 4 new).

- [ ] **Step 5: Manual CLI smoke check**

```bash
cd C:/coding/cool_physical_ai_project
uv run python -m factory.orchestrator.plan_to_tasks docs/superpowers/plans/2026-07-16-scope-guard-pi-extension.md --repo /tmp/plan-to-tasks-smoke 2>&1 || true
```
(Any real existing plan file works for this smoke check -- it just needs `### Task N:` sections. Using a scratch `--repo` avoids touching this repo's real `tasks/` directory. Confirm it prints `created: T-001, T-002, ...` and exits 0; then delete the scratch directory.)

- [ ] **Step 6: Run the full gate**

Run: `uv run python scripts/gates/all.py; echo "exit=$?"`
Expected: exit=0.

- [ ] **Step 7: Commit**

```bash
git add src/factory/orchestrator/plan_to_tasks.py tests/unit/test_plan_to_tasks.py
git commit -m "feat: plan_to_tasks CLI -- deterministic plan.md to tasks/T-*.md"
```

---

### Task 9: TS -- `pi-types.ts` gains `select`/`newSession`; `process-control.ts` gains task targeting

**Files:**
- Modify: `pi-ext/factory-watch/src/pi-types.ts`
- Modify: `pi-ext/factory-watch/src/process-control.ts`
- Modify: `pi-ext/factory-watch/test/process-control.test.ts`

**Interfaces:**
- Consumes: nothing new.
- Produces: `UiApi.select`, `ExtCommandCtx.newSession`, `ReplacedSessionCtx`; `buildRunCommand(provider, modelId, taskId?)`, `buildListJsonCommand()`.

- [ ] **Step 1: Write the failing tests**

Add to the end of `pi-ext/factory-watch/test/process-control.test.ts`:

```typescript
describe("buildRunCommand with a task id", () => {
  test("appends --task when a task id is given", () => {
    const cmd = buildRunCommand("openrouter", "anthropic/claude-opus-4", "T-003");
    expect(cmd.args).toEqual([
      "run", "python", "-m", "factory.orchestrator", "run",
      "--provider", "openrouter",
      "--model", "anthropic/claude-opus-4",
      "--task", "T-003",
    ]);
  });
});

describe("buildListJsonCommand", () => {
  test("builds the orchestrator list --json invocation", () => {
    const cmd = buildListJsonCommand();
    expect(cmd.bin).toBe("uv");
    expect(cmd.args).toEqual(["run", "python", "-m", "factory.orchestrator", "list", "--json"]);
  });
});
```

Update the import line at the top of the same file:
```typescript
import { buildListCommand, buildRunCommand, buildWindowsKillArgs } from "../src/process-control.js";
```
becomes:
```typescript
import { buildListCommand, buildListJsonCommand, buildRunCommand, buildWindowsKillArgs } from "../src/process-control.js";
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd pi-ext/factory-watch && npm test`
Expected: FAIL -- `buildListJsonCommand` is not exported.

- [ ] **Step 3: Implement in `src/process-control.ts`**

Replace:
```typescript
export function buildRunCommand(provider: string, modelId: string): Command {
  return {
    bin: "uv",
    args: [
      "run", "python", "-m", "factory.orchestrator", "run",
      "--provider", provider,
      "--model", modelId,
    ],
  };
}

export function buildListCommand(): Command {
  return {
    bin: "uv",
    args: ["run", "python", "-m", "factory.orchestrator", "list"],
  };
}
```
with:
```typescript
export function buildRunCommand(provider: string, modelId: string, taskId?: string): Command {
  const args = [
    "run", "python", "-m", "factory.orchestrator", "run",
    "--provider", provider,
    "--model", modelId,
  ];
  if (taskId !== undefined) {
    args.push("--task", taskId);
  }
  return { bin: "uv", args };
}

export function buildListCommand(): Command {
  return {
    bin: "uv",
    args: ["run", "python", "-m", "factory.orchestrator", "list"],
  };
}

export function buildListJsonCommand(): Command {
  return {
    bin: "uv",
    args: ["run", "python", "-m", "factory.orchestrator", "list", "--json"],
  };
}
```

- [ ] **Step 4: Extend `src/pi-types.ts`**

Replace the whole file:

```typescript
// Minimal structural subset of Pi's real ExtensionAPI/ExtensionContext that
// this extension actually uses. Pinned against the real
// @earendil-works/pi-coding-agent package's types by type-compat-check.ts
// so drift is caught at typecheck time, not discovered later.

export interface ModelInfo {
  provider: string;
  id: string;
}

export interface ReplacedSessionCtx {
  sendUserMessage(
    content: string,
    options?: { deliverAs?: "steer" | "followUp" },
  ): Promise<void>;
}

export interface UiApi {
  notify(message: string, type?: "info" | "warning" | "error"): void;
  setStatus(key: string, text: string | undefined): void;
  setWidget(key: string, content: string[] | undefined): void;
  select(title: string, options: string[]): Promise<string | undefined>;
}

export interface ExtCommandCtx {
  cwd: string;
  ui: UiApi;
  model: ModelInfo | undefined;
  newSession(options?: {
    withSession?: (ctx: ReplacedSessionCtx) => Promise<void>;
  }): Promise<{ cancelled: boolean }>;
}

export interface CommandDef {
  description?: string;
  handler: (args: string, ctx: ExtCommandCtx) => Promise<void>;
}

export interface PiApi {
  registerCommand(name: string, def: CommandDef): void;
}
```

- [ ] **Step 5: Run to pass**

Run: `cd pi-ext/factory-watch && npm test && npm run typecheck`
Expected: all tests pass; typecheck clean (this also re-validates `type-compat-check.ts` against the real installed package's `ExtensionCommandContext`/`ExtensionUIContext`).

- [ ] **Step 6: Commit**

```bash
git add pi-ext/factory-watch/src/pi-types.ts pi-ext/factory-watch/src/process-control.ts pi-ext/factory-watch/test/process-control.test.ts
git commit -m "feat: task-targeted run command and session-control types"
```

---

### Task 10: TS -- `task-picker.ts` (pure)

**Files:**
- Create: `pi-ext/factory-watch/src/task-picker.ts`
- Test: `pi-ext/factory-watch/test/task-picker.test.ts`

**Interfaces:**
- Consumes: nothing.
- Produces: `TaskSummary`, `formatTaskOption(task)`, `parseTaskIdFromOption(option)`.

- [ ] **Step 1: Write the failing test**

```typescript
// test/task-picker.test.ts
import { describe, expect, test } from "vitest";
import { formatTaskOption, parseTaskIdFromOption } from "../src/task-picker.js";

describe("formatTaskOption", () => {
  test("formats id and title as a single picker line", () => {
    expect(formatTaskOption({ id: "T-003", title: "Add battery-aware RTB", status: "todo" })).toBe(
      "T-003  Add battery-aware RTB",
    );
  });
});

describe("parseTaskIdFromOption", () => {
  test("recovers the id from a formatted option", () => {
    expect(parseTaskIdFromOption("T-003  Add battery-aware RTB")).toBe("T-003");
  });

  test("handles a title with no spaces", () => {
    expect(parseTaskIdFromOption("T-003  X")).toBe("T-003");
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd pi-ext/factory-watch && npm test`
Expected: FAIL -- `../src/task-picker.js` not found.

- [ ] **Step 3: Implement `src/task-picker.ts`**

```typescript
export interface TaskSummary {
  id: string;
  title: string;
  status: string;
}

export function formatTaskOption(task: TaskSummary): string {
  return `${task.id}  ${task.title}`;
}

export function parseTaskIdFromOption(option: string): string {
  const [id] = option.split(/\s+/);
  return id;
}
```

- [ ] **Step 4: Run to pass**

Run: `cd pi-ext/factory-watch && npm test && npm run typecheck`
Expected: all pass; typecheck clean.

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/task-picker.ts pi-ext/factory-watch/test/task-picker.test.ts
git commit -m "feat: pure task-picker option formatting"
```

---

### Task 11: TS -- `skill-prompt.ts` (pure)

**Files:**
- Create: `pi-ext/factory-watch/src/skill-prompt.ts`
- Test: `pi-ext/factory-watch/test/skill-prompt.test.ts`

**Interfaces:**
- Consumes: nothing.
- Produces: `SkillContent`, `buildSkillBlock(skill)`, `buildPlanSeedPrompt(topic, skillBlocks)`.

- [ ] **Step 1: Write the failing test**

```typescript
// test/skill-prompt.test.ts
import { describe, expect, test } from "vitest";
import { buildPlanSeedPrompt, buildSkillBlock } from "../src/skill-prompt.js";

describe("buildSkillBlock", () => {
  test("wraps skill content in the same <skill> shape Pi's native /skill:name expansion produces", () => {
    const block = buildSkillBlock({
      name: "brainstorming",
      location: "/repo/.pi/skills/brainstorming/SKILL.md",
      body: "# Brainstorming\n\nSome content.",
    });
    expect(block).toBe(
      '<skill name="brainstorming" location="/repo/.pi/skills/brainstorming/SKILL.md">\n' +
        "# Brainstorming\n\nSome content.\n</skill>",
    );
  });
});

describe("buildPlanSeedPrompt", () => {
  test("includes every skill block, the plan_to_tasks override instructions, and the topic", () => {
    const prompt = buildPlanSeedPrompt("add battery-aware RTB", ["<skill1/>", "<skill2/>"]);
    expect(prompt).toContain("<skill1/>");
    expect(prompt).toContain("<skill2/>");
    expect(prompt).toContain("factory.orchestrator.plan_to_tasks");
    expect(prompt).toContain("Topic: add battery-aware RTB");
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd pi-ext/factory-watch && npm test`
Expected: FAIL -- `../src/skill-prompt.js` not found.

- [ ] **Step 3: Implement `src/skill-prompt.ts`**

```typescript
export interface SkillContent {
  name: string;
  location: string;
  body: string;
}

export function buildSkillBlock(skill: SkillContent): string {
  return `<skill name="${skill.name}" location="${skill.location}">\n${skill.body}\n</skill>`;
}

export function buildPlanSeedPrompt(topic: string, skillBlocks: string[]): string {
  const instructions = [
    "You're in plan-time for this repo's dev factory. Use the loaded `brainstorming` skill on the topic below.",
    "When brainstorming reaches its handoff to `writing-plans`, proceed into `writing-plans` as usual; save the plan under `docs/superpowers/plans/`.",
    'Override writing-plans\' own "Execution Handoff" step: once the plan is saved, do not offer subagent-driven or inline execution. Instead run `uv run python -m factory.orchestrator.plan_to_tasks <plan-file>` and report the task ids it created. Actual execution happens later via /factory-run.',
  ].join("\n\n");
  return [...skillBlocks, instructions, `Topic: ${topic}`].join("\n\n");
}
```

- [ ] **Step 4: Run to pass**

Run: `cd pi-ext/factory-watch && npm test && npm run typecheck`
Expected: all pass; typecheck clean.

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/skill-prompt.ts pi-ext/factory-watch/test/skill-prompt.test.ts
git commit -m "feat: pure skill-block and plan seed-prompt builders"
```

---

### Task 12: TS -- refactor `index.ts` to share lock-check/launch logic between `/factory` and `/factory-run`

**Files:**
- Modify: `pi-ext/factory-watch/src/index.ts`
- Modify: `pi-ext/factory-watch/test/handler.test.ts`

**Interfaces:**
- Consumes: nothing new (pure internal refactor).
- Produces: internal `isAlreadyRunning(ctx, lockPath)` and `launchAndWatch(ctx, cmd, label)` helpers, extracted from `/factory`'s existing handler with identical behavior.

This task changes no observable behavior -- it only extracts shared helpers `/factory-run` (Task 14) will also use, so the existing test suite is the regression check.

- [ ] **Step 1: Confirm the existing test suite passes before refactoring (baseline)**

Run: `cd pi-ext/factory-watch && npm test`
Expected: all existing tests pass (this is the safety net for the refactor below).

- [ ] **Step 2: Refactor `src/index.ts`**

Replace the whole file:

```typescript
// Pi loads this via: pi --extension pi-ext/factory-watch/src/index.ts
// (project-local auto-discovery via .pi/extensions/ also works once installed there)

import { spawn, spawnSync } from "node:child_process";
import { openSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { isPidAlive, parseLock } from "./lock-status.js";
import { buildListCommand, buildRunCommand, buildWindowsKillArgs } from "./process-control.js";
import type { Command } from "./process-control.js";
import type { ExtCommandCtx, PiApi } from "./pi-types.js";
import { formatStatusLines, parseStatus } from "./status-format.js";

const STATUS_FILE = "sessions/.factory-status.json";
const LOCK_FILE = "sessions/.factory-run.lock";
const LOG_FILE = "sessions/.factory-run.log";
const POLL_INTERVAL_MS = 1000;
const POSIX_GRACEFUL_TIMEOUT_MS = 3000;

function readFileIfExists(path: string): string | null {
  try {
    return readFileSync(path, "utf-8");
  } catch {
    return null;
  }
}

export default function factoryWatch(pi: PiApi): void {
  let pollHandle: ReturnType<typeof setInterval> | undefined;

  function stopPolling(): void {
    if (pollHandle !== undefined) {
      clearInterval(pollHandle);
      pollHandle = undefined;
    }
  }

  function isAlreadyRunning(ctx: ExtCommandCtx, lockPath: string): boolean {
    const existingLockRaw = readFileIfExists(lockPath);
    if (existingLockRaw === null) {
      return false;
    }
    const existingLock = parseLock(existingLockRaw);
    if (existingLock !== null && isPidAlive(existingLock.pid)) {
      ctx.ui.notify(
        `factory already running (pid ${existingLock.pid}) -- use /factory-stop first`,
        "warning",
      );
      return true;
    }
    return false;
  }

  function launchAndWatch(ctx: ExtCommandCtx, cmd: Command, label: string): void {
    const statusPath = join(ctx.cwd, STATUS_FILE);
    const lockPath = join(ctx.cwd, LOCK_FILE);
    const logFd = openSync(join(ctx.cwd, LOG_FILE), "a");
    const child = spawn(cmd.bin, cmd.args, {
      cwd: ctx.cwd,
      detached: true,
      stdio: ["ignore", logFd, logFd],
    });
    child.unref();

    stopPolling();
    pollHandle = setInterval(() => {
      // ctx captured by this closure can outlive its session (e.g. a
      // single `-p` turn ending, or ctx.newSession()/fork()/reload() in an
      // interactive one) -- touching ctx.ui after that throws. Stop
      // polling instead of taking the whole host process down with an
      // uncaught exception on the next tick.
      try {
        const raw = readFileIfExists(statusPath);
        const record = raw === null ? null : parseStatus(raw);
        ctx.ui.setWidget("factory", formatStatusLines(record));

        const stillLocked = readFileIfExists(lockPath) !== null;
        if (!stillLocked) {
          stopPolling();
          ctx.ui.notify("factory run finished", "info");
        }
      } catch {
        stopPolling();
      }
    }, POLL_INTERVAL_MS);

    ctx.ui.notify(`factory started (${label})`, "info");
  }

  pi.registerCommand("factory", {
    description: "Run the next todo factory task, watching progress live",
    handler: async (_args: string, ctx: ExtCommandCtx) => {
      const lockPath = join(ctx.cwd, LOCK_FILE);
      if (isAlreadyRunning(ctx, lockPath)) {
        return;
      }

      if (ctx.model === undefined) {
        ctx.ui.notify("no model selected in this session -- can't launch factory", "error");
        return;
      }

      const cmd = buildRunCommand(ctx.model.provider, ctx.model.id);
      launchAndWatch(ctx, cmd, `${ctx.model.provider}/${ctx.model.id}`);
    },
  });

  pi.registerCommand("factory-stop", {
    description: "Stop the currently running factory task",
    handler: async (_args: string, ctx: ExtCommandCtx) => {
      const lockPath = join(ctx.cwd, LOCK_FILE);
      const raw = readFileIfExists(lockPath);
      if (raw === null) {
        ctx.ui.notify("factory is not running", "info");
        return;
      }
      const lock = parseLock(raw);
      if (lock === null || !isPidAlive(lock.pid)) {
        ctx.ui.notify("factory lock is stale (process already gone)", "info");
        return;
      }

      if (process.platform === "win32") {
        spawnSync("taskkill", buildWindowsKillArgs(lock.pid));
      } else {
        try {
          process.kill(-lock.pid, "SIGTERM");
        } catch {
          // process group may already be gone; the liveness check below handles it
        }
        await new Promise((resolve) => setTimeout(resolve, POSIX_GRACEFUL_TIMEOUT_MS));
        if (isPidAlive(lock.pid)) {
          try {
            process.kill(-lock.pid, "SIGKILL");
          } catch {
            // already gone
          }
        }
      }

      stopPolling();
      ctx.ui.setWidget("factory", undefined);
      ctx.ui.notify("factory stopped", "info");
    },
  });

  pi.registerCommand("factory-tasks", {
    description: "List factory tasks grouped by status",
    handler: async (_args: string, ctx: ExtCommandCtx) => {
      const cmd = buildListCommand();
      const result = spawnSync(cmd.bin, cmd.args, { cwd: ctx.cwd, encoding: "utf-8" });
      if (result.status !== 0) {
        ctx.ui.notify(`factory-tasks failed: ${result.stderr || "unknown error"}`, "error");
        return;
      }
      const lines = result.stdout.split(/\r?\n/).filter((line) => line.length > 0);
      ctx.ui.setWidget("factory-tasks", lines);
    },
  });
}
```

- [ ] **Step 3: Run to confirm the refactor is behavior-preserving**

Run: `cd pi-ext/factory-watch && npm test && npm run typecheck`
Expected: same test results as the Step 1 baseline (all pass); typecheck clean.

- [ ] **Step 4: Commit**

```bash
git add pi-ext/factory-watch/src/index.ts
git commit -m "refactor: extract shared lock-check/launch helpers in factory-watch"
```

---

### Task 13: TS -- `/plan` command wiring

**Files:**
- Modify: `pi-ext/factory-watch/src/index.ts`
- Modify: `pi-ext/factory-watch/test/handler.test.ts`
- Modify: `pi-ext/factory-watch/package.json` (move `@earendil-works/pi-coding-agent` usage from types-only to a real runtime import -- no version/dependency-list change needed, it's already installed)

**Interfaces:**
- Consumes: `buildSkillBlock`/`buildPlanSeedPrompt` (Task 11), `ExtCommandCtx.newSession`/`UiApi.select` (Task 9), pi's real `loadSkills`/`stripFrontmatter`.
- Produces: `/plan <topic>` command.

- [ ] **Step 1: Write the failing tests**

Replace `pi-ext/factory-watch/test/handler.test.ts` in full:

```typescript
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import { EventEmitter } from "node:events";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import factoryWatch from "../src/index.js";
import type { CommandDef, ExtCommandCtx, PiApi, ReplacedSessionCtx, UiApi } from "../src/pi-types.js";

vi.mock("node:child_process", () => ({
  spawn: vi.fn(() => {
    const child = new EventEmitter() as EventEmitter & { unref: () => void };
    child.unref = () => {};
    return child;
  }),
  spawnSync: vi.fn(),
}));
vi.mock("node:fs", async (importOriginal) => {
  const actual = await importOriginal<typeof import("node:fs")>();
  return { ...actual, openSync: vi.fn(() => 0) };
});

function capture(): { commands: Map<string, CommandDef>; pi: PiApi } {
  const commands = new Map<string, CommandDef>();
  const pi: PiApi = {
    registerCommand: (name, def) => commands.set(name, def),
  };
  factoryWatch(pi);
  return { commands, pi };
}

function fakeCtx(overrides: Partial<ExtCommandCtx> = {}): ExtCommandCtx {
  const ui: UiApi = {
    notify: vi.fn(),
    setStatus: vi.fn(),
    setWidget: vi.fn(),
    select: vi.fn(),
  };
  return {
    cwd: overrides.cwd ?? process.cwd(),
    ui: overrides.ui ?? ui,
    model:
      "model" in overrides ? overrides.model : { provider: "openrouter", id: "anthropic/claude-opus-4" },
    newSession: overrides.newSession ?? vi.fn(async () => ({ cancelled: false })),
  };
}

describe("factory-watch commands", () => {
  beforeEach(() => {
    vi.mocked(spawnSync).mockReset();
  });

  test("registers factory, factory-stop, factory-tasks, factory-run, and plan", () => {
    const { commands } = capture();
    expect(commands.has("factory")).toBe(true);
    expect(commands.has("factory-stop")).toBe(true);
    expect(commands.has("factory-tasks")).toBe(true);
    expect(commands.has("factory-run")).toBe(true);
    expect(commands.has("plan")).toBe(true);
  });

  test("/factory notifies an error and does nothing else when no model is active", async () => {
    const { commands } = capture();
    const ctx = fakeCtx({ model: undefined });
    await commands.get("factory")!.handler("", ctx);
    expect(ctx.ui.notify).toHaveBeenCalledWith(expect.stringContaining("no model"), "error");
  });

  test("/factory-stop notifies when nothing is running (no lock file)", async () => {
    const { commands } = capture();
    const ctx = fakeCtx({ cwd: "/nonexistent/path/for/this/test/only" });
    await commands.get("factory-stop")!.handler("", ctx);
    expect(ctx.ui.notify).toHaveBeenCalledWith(expect.stringContaining("not running"), "info");
  });

  test("/factory's poll loop stops instead of crashing once ctx goes stale", async () => {
    // Reproduces a real crash seen running `pi -p "/factory"`: in print mode
    // (and after ctx.newSession()/fork()/reload() in an interactive one),
    // ctx.ui becomes stale and throws on access. Before the fix, the next
    // setInterval tick threw uncaught and took the whole host process down.
    vi.useFakeTimers();
    try {
      const { commands } = capture();
      const setWidget = vi.fn(() => {
        throw new Error("This extension ctx is stale after session replacement or reload.");
      });
      const ui: UiApi = { notify: vi.fn(), setStatus: vi.fn(), setWidget, select: vi.fn() };
      const ctx = fakeCtx({ cwd: "/nonexistent/path/for/this/test/only", ui });

      await commands.get("factory")!.handler("", ctx);

      expect(() => vi.advanceTimersByTime(5_000)).not.toThrow();
      expect(setWidget).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });

  test("/factory-tasks renders the task board via a widget", async () => {
    vi.mocked(spawnSync).mockReturnValue({
      status: 0,
      stdout: "TODO (1)\n  T-001  Example task\n",
      stderr: "",
    } as ReturnType<typeof spawnSync>);

    const { commands } = capture();
    const ctx = fakeCtx();
    await commands.get("factory-tasks")!.handler("", ctx);

    expect(ctx.ui.setWidget).toHaveBeenCalledWith("factory-tasks", [
      "TODO (1)",
      "  T-001  Example task",
    ]);
  });

  test("/factory-tasks notifies an error when the CLI call fails", async () => {
    vi.mocked(spawnSync).mockReturnValue({
      status: 1,
      stdout: "",
      stderr: "boom",
    } as ReturnType<typeof spawnSync>);

    const { commands } = capture();
    const ctx = fakeCtx();
    await commands.get("factory-tasks")!.handler("", ctx);

    expect(ctx.ui.notify).toHaveBeenCalledWith(expect.stringContaining("boom"), "error");
  });

  test("/plan rejects an empty topic without starting a session", async () => {
    const { commands } = capture();
    const ctx = fakeCtx();
    await commands.get("plan")!.handler("   ", ctx);
    expect(ctx.ui.notify).toHaveBeenCalledWith(expect.stringContaining("usage: /plan"), "error");
    expect(ctx.newSession).not.toHaveBeenCalled();
  });

  test("/plan notifies when a required skill isn't vendored in this repo", async () => {
    const { commands } = capture();
    const emptyDir = mkdtempSync(join(tmpdir(), "factory-watch-plan-test-"));
    const ctx = fakeCtx({ cwd: emptyDir });
    await commands.get("plan")!.handler("some topic", ctx);
    expect(ctx.ui.notify).toHaveBeenCalledWith(expect.stringContaining("skill not found"), "error");
    expect(ctx.newSession).not.toHaveBeenCalled();
  });

  test("/plan seeds a fresh session with the topic once skills are found", async () => {
    const { commands } = capture();
    // This repo's real .pi/skills/ has brainstorming + writing-plans vendored
    // (Task 3), so running from the real repo cwd exercises the real
    // loadSkills()+readFileSync() path end to end.
    const ctx = fakeCtx({ cwd: process.cwd() });
    await commands.get("plan")!.handler("add battery-aware RTB", ctx);
    expect(ctx.newSession).toHaveBeenCalledTimes(1);
    const call = vi.mocked(ctx.newSession).mock.calls[0][0];
    const session: ReplacedSessionCtx = { sendUserMessage: vi.fn() };
    await call!.withSession!(session);
    expect(session.sendUserMessage).toHaveBeenCalledWith(
      expect.stringContaining("add battery-aware RTB"),
      { deliverAs: "followUp" },
    );
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd pi-ext/factory-watch && npm test`
Expected: FAIL -- `commands.get("plan")` is `undefined`.

- [ ] **Step 3: Wire `/plan` into `src/index.ts`**

Add these imports at the top (after the existing `formatStatusLines`/`parseStatus` import):
```typescript
import { homedir } from "node:os";
import { loadSkills, stripFrontmatter } from "@earendil-works/pi-coding-agent";
import { buildPlanSeedPrompt, buildSkillBlock } from "./skill-prompt.js";
import type { ReplacedSessionCtx } from "./pi-types.js";
```

Add a constant near the top, alongside the existing `POSIX_GRACEFUL_TIMEOUT_MS`:
```typescript
const PLAN_SKILL_NAMES = ["brainstorming", "writing-plans"];
```

Add the new command registration at the end of `factoryWatch`, right before the closing `}` of the function (after the existing `factory-tasks` registration):

```typescript
  pi.registerCommand("plan", {
    description: "Start an interactive planning session (brainstorming -> writing-plans)",
    handler: async (args: string, ctx: ExtCommandCtx) => {
      const topic = args.trim();
      if (topic === "") {
        ctx.ui.notify("usage: /plan <topic>", "error");
        return;
      }

      const { skills } = loadSkills({
        cwd: ctx.cwd,
        agentDir: join(homedir(), ".pi", "agent"),
        skillPaths: [],
        includeDefaults: true,
      });

      const skillBlocks: string[] = [];
      for (const name of PLAN_SKILL_NAMES) {
        const skill = skills.find((s) => s.name === name);
        if (skill === undefined) {
          ctx.ui.notify(`/plan: skill not found: ${name}`, "error");
          return;
        }
        const content = readFileSync(skill.filePath, "utf-8");
        const body = stripFrontmatter(content).trim();
        skillBlocks.push(buildSkillBlock({ name: skill.name, location: skill.filePath, body }));
      }

      const seedText = buildPlanSeedPrompt(topic, skillBlocks);
      await ctx.newSession({
        withSession: async (session: ReplacedSessionCtx) => {
          await session.sendUserMessage(seedText, { deliverAs: "followUp" });
        },
      });
    },
  });
```

- [ ] **Step 4: Run to pass**

Run: `cd pi-ext/factory-watch && npm test && npm run typecheck`
Expected: all pass; typecheck clean.

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/index.ts pi-ext/factory-watch/test/handler.test.ts
git commit -m "feat: /plan command -- hard-loaded brainstorming+writing-plans seed"
```

---

### Task 14: TS -- `/factory-run` command wiring

**Files:**
- Modify: `pi-ext/factory-watch/src/index.ts`
- Modify: `pi-ext/factory-watch/test/handler.test.ts`

**Interfaces:**
- Consumes: `buildRunCommand(taskId)`/`buildListJsonCommand` (Task 9), `formatTaskOption`/`parseTaskIdFromOption` (Task 10), `isAlreadyRunning`/`launchAndWatch` (Task 12).
- Produces: `/factory-run [task-id]` command.

- [ ] **Step 1: Write the failing tests**

Add to the end of the `describe("factory-watch commands", ...)` block in `pi-ext/factory-watch/test/handler.test.ts` (immediately before its closing `});`):

```typescript
  test("/factory-run notifies when no todo tasks exist, without spawning", async () => {
    vi.mocked(spawnSync).mockReturnValue({
      status: 0,
      stdout: JSON.stringify([{ id: "T-001", title: "done one", status: "done" }]),
      stderr: "",
    } as ReturnType<typeof spawnSync>);

    const { commands } = capture();
    const ctx = fakeCtx();
    await commands.get("factory-run")!.handler("", ctx);

    expect(ctx.ui.notify).toHaveBeenCalledWith(expect.stringContaining("no todo tasks"), "info");
    expect(ctx.ui.select).not.toHaveBeenCalled();
  });

  test("/factory-run shows a picker over todo tasks and does nothing if cancelled", async () => {
    vi.mocked(spawnSync).mockReturnValue({
      status: 0,
      stdout: JSON.stringify([
        { id: "T-001", title: "First", status: "todo" },
        { id: "T-002", title: "Second", status: "todo" },
      ]),
      stderr: "",
    } as ReturnType<typeof spawnSync>);

    const ui: UiApi = {
      notify: vi.fn(),
      setStatus: vi.fn(),
      setWidget: vi.fn(),
      select: vi.fn().mockResolvedValue(undefined),
    };
    const { commands } = capture();
    const ctx = fakeCtx({ ui });
    await commands.get("factory-run")!.handler("", ctx);

    expect(ui.select).toHaveBeenCalledWith("Run which task?", ["T-001  First", "T-002  Second"]);
  });

  test("/factory-run uses an inline task id without listing or showing a picker", async () => {
    const { commands } = capture();
    const ui: UiApi = { notify: vi.fn(), setStatus: vi.fn(), setWidget: vi.fn(), select: vi.fn() };
    const ctx = fakeCtx({ cwd: "/nonexistent/path/for/this/test/only", ui });
    await commands.get("factory-run")!.handler("T-003", ctx);

    expect(spawnSync).not.toHaveBeenCalled();
    expect(ui.select).not.toHaveBeenCalled();
    expect(ui.notify).toHaveBeenCalledWith(expect.stringContaining("T-003"), "info");
  });

  test("/factory-run notifies an error and does nothing else when no model is active", async () => {
    const { commands } = capture();
    const ctx = fakeCtx({ model: undefined });
    await commands.get("factory-run")!.handler("", ctx);
    expect(ctx.ui.notify).toHaveBeenCalledWith(expect.stringContaining("no model"), "error");
  });
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd pi-ext/factory-watch && npm test`
Expected: FAIL -- `commands.get("factory-run")` is `undefined`.

- [ ] **Step 3: Wire `/factory-run` into `src/index.ts`**

Add to the imports (extending the existing `process-control.js` import line):
```typescript
import { buildListCommand, buildListJsonCommand, buildRunCommand, buildWindowsKillArgs } from "./process-control.js";
```
and add a new import:
```typescript
import { formatTaskOption, parseTaskIdFromOption } from "./task-picker.js";
import type { TaskSummary } from "./task-picker.js";
```

Add the new command registration, after `factory-tasks` and before `plan` (order doesn't matter functionally, but this keeps `/factory*` commands grouped):

```typescript
  pi.registerCommand("factory-run", {
    description: "Run the factory on one specific task",
    handler: async (args: string, ctx: ExtCommandCtx) => {
      const lockPath = join(ctx.cwd, LOCK_FILE);
      if (isAlreadyRunning(ctx, lockPath)) {
        return;
      }

      if (ctx.model === undefined) {
        ctx.ui.notify("no model selected in this session -- can't launch factory", "error");
        return;
      }

      let taskId = args.trim();
      if (taskId === "") {
        const cmd = buildListJsonCommand();
        const result = spawnSync(cmd.bin, cmd.args, { cwd: ctx.cwd, encoding: "utf-8" });
        if (result.status !== 0) {
          ctx.ui.notify(`factory-run failed to list tasks: ${result.stderr || "unknown error"}`, "error");
          return;
        }
        let tasks: TaskSummary[];
        try {
          tasks = JSON.parse(result.stdout) as TaskSummary[];
        } catch {
          ctx.ui.notify("factory-run failed to parse task list", "error");
          return;
        }
        const todoTasks = tasks.filter((t) => t.status === "todo");
        if (todoTasks.length === 0) {
          ctx.ui.notify("no todo tasks", "info");
          return;
        }
        const selected = await ctx.ui.select("Run which task?", todoTasks.map(formatTaskOption));
        if (selected === undefined) {
          return;
        }
        taskId = parseTaskIdFromOption(selected);
      }

      const cmd = buildRunCommand(ctx.model.provider, ctx.model.id, taskId);
      launchAndWatch(ctx, cmd, `${ctx.model.provider}/${ctx.model.id}, task ${taskId}`);
    },
  });
```

- [ ] **Step 4: Run to pass**

Run: `cd pi-ext/factory-watch && npm test && npm run typecheck`
Expected: all pass; typecheck clean.

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/index.ts pi-ext/factory-watch/test/handler.test.ts
git commit -m "feat: /factory-run command -- target one specific task, with a picker"
```

---

### Task 15: Docs and gate

**Files:**
- Modify: `pi-ext/factory-watch/README.md`

**Interfaces:**
- Consumes: nothing.
- Produces: updated docs covering `/plan` and `/factory-run`.

- [ ] **Step 1: Update `pi-ext/factory-watch/README.md`**

Replace the `## Commands` section:

```markdown
## Commands

- `/factory` — reads the session's currently active model (`ctx.model`), runs
  `uv run python -m factory.orchestrator run --provider <provider> --model <id>`
  detached, and polls `sessions/.factory-status.json` (written by the
  orchestrator, see Plan A) once a second, rendering it via a widget. Refuses
  to start a second run while `sessions/.factory-run.lock` shows a live PID.
- `/factory-run [task-id]` — like `/factory`, but targets one specific task
  (`status: todo` only). With no argument, lists todo tasks via
  `factory.orchestrator list --json` and shows an interactive picker.
- `/factory-stop` — reads the lock file's PID and terminates it: a forceful
  process-tree kill on Windows (`taskkill /PID <pid> /T /F` — a non-forceful
  `/T` alone is unreliable for plain console processes on Windows, so this
  skips straight to force), or `SIGTERM` to the process group followed by
  `SIGKILL` after a few seconds if still alive on POSIX.
- `/factory-tasks` — shows the task ledger, grouped by status, as a widget.
- `/plan <topic>` — starts a fresh session seeded with the real, full content
  of the vendored `brainstorming`/`writing-plans` skills (hard-loaded via
  Pi's own exported `loadSkills`/`stripFrontmatter`, not the soft
  advertise-and-hope-the-model-reads-it path) plus the topic. Ends with
  `uv run python -m factory.orchestrator.plan_to_tasks <plan-file>`
  deterministically turning the saved plan into `tasks/T-*.md` files, ready
  for `/factory-run`.
```

Add a note after the existing "## No new IPC" section:

```markdown
## Hard skill loading

`/plan` never relies on the model choosing to read a skill file. It reads
`.pi/skills/brainstorming/SKILL.md` and `.pi/skills/writing-plans/SKILL.md`
itself (via Pi's own exported `loadSkills`/`stripFrontmatter`) and injects
their full content into the seed message -- the same `<skill name="..."
location="...">` shape Pi's native `/skill:name` expansion produces. The
orchestrator's sub-agent roles do the equivalent on the Python side
(`factory/orchestrator/skills.py`'s `load_skill_block`, used by
`compose_prompt`). All 10 vendored skills are marked
`disable-model-invocation: true` in their frontmatter -- they're never meant
to be reachable any other way.
```

- [ ] **Step 2: Run the full gate**

Run: `uv run python scripts/gates/all.py; echo "exit=$?"`
Expected: exit=0.

Run: `uv run python scripts/gates/watch_ext.py; echo "exit=$?"`
Expected: exit=0.

- [ ] **Step 3: Commit**

```bash
git add pi-ext/factory-watch/README.md
git commit -m "docs: document /plan and /factory-run in factory-watch's README"
```

---

### Task 16: Required manual verification

Same category as Plan 4's Task 6 -- these properties can't be fully proven by unit tests alone and must be checked against a real interactive session.

- [ ] **Step 1: Verify `/plan`'s seed message actually contains full skill content**

From a real interactive `pi` session in this repo (`pi --extension pi-ext/factory-watch/src/index.ts`), type `/plan try a tiny throwaway topic like "rename a variable"`. Confirm:
- A fresh session starts.
- The very first thing the model does/says reflects having read the full `brainstorming` skill content (e.g. it starts asking clarifying questions per that skill's process), not just a bare skill name.
- No crash, no stack trace.

Then cancel/abandon this session (Ctrl+C or close it) -- no need to complete a real plan for this check.

- [ ] **Step 2: Verify `/factory-run`'s picker actually constrains which task executes**

With at least two `status: todo` tasks in `tasks/` (temporarily add a second scratch one if needed, matching `tasks/T-001-example.md`'s frontmatter shape, and remove it afterward), run `/factory-run` with no argument. Confirm the picker shows both, and that picking one launches the orchestrator with exactly that task's id (check `sessions/.factory-status.json`'s `task_id` field once the run starts) -- not always the first todo task.

- [ ] **Step 3: Verify a real sub-agent prompt actually contains hard-loaded skill content**

Run a real (billed) `/factory-run` against a trivial task, or replay the `pi -p` verification technique used earlier this session (an explicit `--provider`/`--model` override, naming a skill in the prompt) directly against one of the now-hard-loaded roles' prompts. Confirm the sub-agent's actual `pi -p` invocation (visible via `sessions/.factory-run.log`, which `factory-watch` already writes the child process's stdout/stderr to) shows the full `<skill name="..." location="...">...</skill>` block for each of that role's `ROLE_SKILLS`, not bare bullet names.

- [ ] **Step 4: Record what was actually observed**

Note what was actually run and seen (not what was expected to happen) in this task's commit message or a follow-up report -- matching this repo's existing precedent (Plan 4's Task 6, the `bb77fb3` commit's honesty about what wasn't verified).

- [ ] **Step 5: Commit**

If step 3 required adding/removing a scratch task file, confirm `git status` is clean before finishing (no stray scratch files left behind). No code commit is expected from this task unless verification surfaces a real bug needing a fix -- if it does, fix it, add a regression test, and commit that fix following the same TDD pattern as every other task in this plan.

---

## Self-Review

**Spec coverage** (against `docs/superpowers/specs/2026-07-20-factory-plan-and-run-design.md`):
- §3.1 vendored skills + disable-model-invocation -> Task 3.
- §3.2 `/plan` command -> Tasks 9 (types), 11 (pure seed-prompt builder), 13 (wiring).
- §3.3 `plan_to_tasks.py` -> Tasks 7 (pure parser), 8 (CLI wrapper). Invocation path refined from the spec's literal `scripts/plan_to_tasks.py` to `uv run python -m factory.orchestrator.plan_to_tasks`, matching this repo's actual existing CLI convention (`-m factory.orchestrator run/list`) and making the parser directly unit-testable via import rather than only via subprocess -- a implementation-level refinement consistent with the spec's architecture, not a change to it.
- §3.4 sub-agent hard-loading -> Tasks 1 (pure `load_skill_block`), 2 (wiring into `compose_prompt`/`nodes.py`/`runner.py`).
- §3.5 orchestrator `--task`/`--json` -> Tasks 4 (`get_task`/errors), 5 (`run_next`), 6 (`__main__.py`).
- §3.6 `/factory-run` -> Tasks 9 (command builders), 10 (picker formatting), 12 (shared helper extraction), 14 (wiring).
- §4 error handling -> covered throughout (missing skill -> `FileNotFoundError` in Task 1/2; bad task id -> `TaskNotFoundError`/`TaskNotTodoError` surfacing via the existing status-file error path in Task 5/6; empty `/plan` topic and picker-cancel/no-todo-tasks in Task 13/14).
- §6 testing strategy -> pure functions vitest/pytest-covered throughout; Task 16 is the explicit required-manual-verification step.

**Placeholder scan:** none. Every step ships exact, complete code and exact commands with expected output.

**Type consistency:** `Command` (existing `process-control.ts`) used unchanged by `buildRunCommand`'s new optional third parameter and by `buildListJsonCommand`. `TaskSummary` (Task 10) matches exactly what `factory.orchestrator list --json` (Task 6) emits and what `/factory-run`'s handler (Task 14) parses. `ParsedPlanTask` (Task 7) fields (`number`, `title`, `files_block`, `produces`) used unchanged by `run`/`_write_task_file` (Task 8). `ReplacedSessionCtx.sendUserMessage` (Task 9) signature matches its one call site in `/plan`'s handler (Task 13) exactly.

**Cross-task dependency note:** Task 2 threads `repo_root` through `run_dev`/`run_review`, which changes their call signature -- every existing direct caller (in `nodes.py` itself, `runner.py`, and the test files) is updated within that same task, not left dangling. Task 12's refactor is verified behavior-preserving (Step 1 baseline vs. Step 3 result) before Tasks 13/14 build on its extracted helpers, so a reviewer can approve the refactor independently of the two new commands that consume it.
