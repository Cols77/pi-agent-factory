# Factory Orchestrator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the deterministic Python orchestrator that consumes plan-time tasks and drives them through the pipeline (Context-Gatherer → Dev → Validation → Review → Session-Writer), spawning Pi agents with the `scope-guard` extension, routing purely on gate exit codes and validated artifacts, with circuit breakers and reliable session records.

**Architecture:** A pure-Python state machine. Agent execution and gate execution sit behind two interfaces — `AgentBackend` and `GateRunner` — each with a **Fake** (deterministic, no LLM/subprocess) and a real implementation. The entire graph, routing, and circuit-breaker logic is therefore unit-testable end-to-end without invoking Pi or pytest-in-pytest. Reuses Plan 1 (`validate_manifest`, `validate_session`, `select_entries`, `parse_entry`) and Plan 2 (the `scope-guard` extension) unchanged. Per-role write scope is injected via `PI_SCOPE_ALLOW`/`PI_SCOPE_BASH` env vars that the `scope-guard` extension enforces.

**Tech Stack:** Python 3.11, `pytest` (marker `unit`), `python-frontmatter` (task/KB parsing), `subprocess` (Pi + gate invocation). No new dependencies.

## Global Constraints

- Python **>= 3.11**; reuse Plan 1's env (`uv`), no new deps.
- **Routing is deterministic:** transitions depend only on `GateRunner` exit codes and schema-validated agent artifacts — never on free-form agent prose.
- **Fail-closed circuit breakers:** every loop is bounded (`max_dev_iters`, `max_review_cycles`); exhaustion ⇒ task outcome `escalated`, never an infinite loop.
- **Per-role scope is data, injected as env:** the orchestrator sets `PI_SCOPE_ALLOW`/`PI_SCOPE_BASH` from `ROLE_SCOPE`; the `scope-guard` extension (Plan 2) enforces it. The orchestrator does **not** add a git-diff backstop (design decision: extensions-only).
- **Every session record is validated** with Plan 1's `validate_session` before it is written; an invalid record is a hard error, not a warning.
- Fresh Pi process per node (isolation); the orchestrator never shares agent state across nodes except via files/artifacts.
- Every task ends green (`ruff`, `pyright`, unit tests) and is committed.

---

## File Structure

```
src/factory/orchestrator/
  __init__.py
  types.py         # AgentRole, NodeOutcome, AgentResult, NodeEvent, TaskResult
  roles.py         # ROLE_SKILLS, ROLE_SCOPE (Scope), ROLE_PROMPTS
  ledger.py        # Task, load_tasks, next_todo, set_status
  backends.py      # AgentBackend/GateRunner protocols; Fake* ; SubprocessGateRunner
  prompts.py       # compose_prompt(role, task, manifest, kb_entries, feedback)
  nodes.py         # run_context_gatherer, run_dev, run_validation, run_review
  session.py       # build_record, write_session
  runner.py        # run_task (state machine), run_next, _load_kb_entries
  pi_backend.py    # PiAgentBackend, parse_pi_json
  __main__.py      # CLI: python -m factory.orchestrator run
tasks/T-001-example.md            # sample task (also used by tests as a fixture shape)
tests/unit/orchestrator/          # one module per unit above
```

---

### Task 1: Core types + role tables

**Files:**
- Create: `src/factory/orchestrator/__init__.py`, `src/factory/orchestrator/types.py`, `src/factory/orchestrator/roles.py`
- Test: `tests/unit/orchestrator/__init__.py`, `tests/unit/orchestrator/test_roles.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `AgentRole` (str Enum): `CONTEXT_GATHERER`, `DEV`, `VALIDATION`, `REVIEW`, `SESSION_WRITER`.
  - `NodeOutcome` (str Enum): `PASS`, `FAIL`, `REJECT`, `CHANGES`, `ESCALATE`.
  - `AgentResult(ok: bool, output: dict, raw: str = "")`.
  - `NodeEvent(node: str, result: str, attempts: int = 1, extra: dict = {})`.
  - `TaskResult(task_id: str, title: str, outcome: str, iterations: int, events: list[NodeEvent], dod_met: bool, manifest: dict | None = None)`.
  - `Scope(allow: list[str], bash: str)`, plus `ROLE_SKILLS`, `ROLE_SCOPE`, `ROLE_PROMPTS` dicts keyed by `AgentRole`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/orchestrator/test_roles.py
import pytest
from factory.orchestrator.types import AgentRole
from factory.orchestrator.roles import ROLE_SKILLS, ROLE_SCOPE, ROLE_PROMPTS

pytestmark = pytest.mark.unit


def test_every_role_has_skills_scope_prompt():
    for role in AgentRole:
        assert ROLE_SKILLS[role]
        assert role in ROLE_SCOPE
        assert ROLE_PROMPTS[role]


def test_review_is_read_only():
    s = ROLE_SCOPE[AgentRole.REVIEW]
    assert s.allow == []
    assert s.bash == "deny"


def test_dev_can_write_src_and_run_bash():
    s = ROLE_SCOPE[AgentRole.DEV]
    assert "src/**" in s.allow
    assert s.bash == "allow"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/orchestrator/test_roles.py -v`
Expected: FAIL — modules missing.

- [ ] **Step 3: Write `types.py`**

```python
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class AgentRole(str, Enum):
    CONTEXT_GATHERER = "context-gatherer"
    DEV = "dev"
    VALIDATION = "validation"
    REVIEW = "review"
    SESSION_WRITER = "session-writer"


class NodeOutcome(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    REJECT = "reject"
    CHANGES = "changes-requested"
    ESCALATE = "escalate"


@dataclass
class AgentResult:
    ok: bool
    output: dict
    raw: str = ""


@dataclass
class NodeEvent:
    node: str
    result: str
    attempts: int = 1
    extra: dict = field(default_factory=dict)


@dataclass
class TaskResult:
    task_id: str
    title: str
    outcome: str  # completed | rejected | escalated
    iterations: int
    events: list[NodeEvent]
    dod_met: bool
    manifest: dict | None = None
```

- [ ] **Step 4: Write `roles.py`**

```python
from __future__ import annotations

from dataclasses import dataclass

from factory.orchestrator.types import AgentRole


@dataclass(frozen=True)
class Scope:
    allow: list[str]  # writable path globs
    bash: str  # "allow" | "deny"


ROLE_SKILLS: dict[AgentRole, list[str]] = {
    AgentRole.CONTEXT_GATHERER: ["verification-before-completion", "context-completeness-audit"],
    AgentRole.DEV: [
        "test-driven-development",
        "systematic-debugging",
        "receiving-code-review",
        "kb-lookup",
    ],
    AgentRole.VALIDATION: ["verification-before-completion", "sim-functional-tests"],
    AgentRole.REVIEW: ["requesting-code-review", "verification-before-completion", "coding-principles"],
    AgentRole.SESSION_WRITER: ["session-report"],
}

ROLE_SCOPE: dict[AgentRole, Scope] = {
    AgentRole.CONTEXT_GATHERER: Scope(allow=["context-manifests/**"], bash="deny"),
    AgentRole.DEV: Scope(allow=["src/**", "tests/**"], bash="allow"),
    AgentRole.VALIDATION: Scope(allow=[], bash="allow"),
    AgentRole.REVIEW: Scope(allow=[], bash="deny"),
    AgentRole.SESSION_WRITER: Scope(allow=["sessions/**"], bash="deny"),
}

ROLE_PROMPTS: dict[AgentRole, str] = {
    AgentRole.CONTEXT_GATHERER: (
        "You verify that spec, plan, prior session, and this task are coherent and "
        "that context is complete. Emit ONLY a context manifest as a fenced ```json block "
        "matching the context_manifest schema. If you cannot prove coherence, set "
        "coherence.proven=false and populate reject."
    ),
    AgentRole.DEV: (
        "Implement the task using strict TDD (write the failing test first). "
        "Consult the provided knowledge-base entries. Do not stop until unit tests pass."
    ),
    AgentRole.VALIDATION: "Run the functional/sim suite. Do not modify source.",
    AgentRole.REVIEW: (
        "Review the change for YAGNI/DRY and against the Definition of Done. Emit ONLY a "
        "fenced ```json block: {\"dod_met\": bool, \"principles\": [..], \"findings\": [..]}."
    ),
    AgentRole.SESSION_WRITER: "Summarize what happened this session for reliable resume.",
}
```

- [ ] **Step 5: Run to pass**

Run: `uv run pytest tests/unit/orchestrator/test_roles.py -v` → 3 passed. Create empty `tests/unit/orchestrator/__init__.py`. Then `uv run ruff check . && uv run pyright`.

- [ ] **Step 6: Commit**

```bash
git add src/factory/orchestrator/__init__.py src/factory/orchestrator/types.py src/factory/orchestrator/roles.py tests/unit/orchestrator/__init__.py tests/unit/orchestrator/test_roles.py
git commit -m "feat: orchestrator core types and role skill/scope/prompt tables"
```

---

### Task 2: Task ledger

**Files:**
- Create: `src/factory/orchestrator/ledger.py`, `tasks/T-001-example.md`
- Test: `tests/unit/orchestrator/test_ledger.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `Task(id: str, title: str, status: str, dod: list[str], body: str, path: Path)`.
  - `load_tasks(tasks_dir: Path) -> list[Task]` — parses `T-*.md` (frontmatter `id`,`title`,`status`,`dod`), sorted by `id`; raises `ValueError` if a required field is missing.
  - `next_todo(tasks: list[Task]) -> Task | None` — first task with `status == "todo"`.
  - `set_status(task: Task, status: str) -> None` — rewrites the file's frontmatter `status` in place.

- [ ] **Step 1: Write the sample task**

`tasks/T-001-example.md`:
```markdown
---
id: T-001
title: "Example: FlightController.goto reaches waypoint"
status: todo
dod:
  - "goto(x,y,z) moves pose to within 0.5m of target in the fake"
  - "unit test covers success and battery decrement"
---

Implement `goto` waypoint behavior on the fake and pybullet controllers.
```

- [ ] **Step 2: Write the failing test**

```python
# tests/unit/orchestrator/test_ledger.py
import pytest
from pathlib import Path
from factory.orchestrator.ledger import load_tasks, next_todo, set_status

pytestmark = pytest.mark.unit


def _write(tmp_path, name, status="todo"):
    (tmp_path / name).write_text(
        f"---\nid: {name.split('-')[0]}-{name.split('-')[1]}\ntitle: t\n"
        f"status: {status}\ndod:\n  - x\n---\nbody\n",
        encoding="utf-8",
    )


def test_load_and_next_todo(tmp_path):
    _write(tmp_path, "T-002-b.md", status="done")
    _write(tmp_path, "T-001-a.md", status="todo")
    tasks = load_tasks(tmp_path)
    assert [t.id for t in tasks] == ["T-001", "T-002"]
    assert next_todo(tasks).id == "T-001"


def test_missing_required_field_raises(tmp_path):
    (tmp_path / "T-003-x.md").write_text("---\nid: T-003\n---\nb\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_tasks(tmp_path)


def test_set_status_rewrites(tmp_path):
    _write(tmp_path, "T-001-a.md")
    task = load_tasks(tmp_path)[0]
    set_status(task, "done")
    assert load_tasks(tmp_path)[0].status == "done"
```

- [ ] **Step 3: Run to verify it fails**

Run: `uv run pytest tests/unit/orchestrator/test_ledger.py -v` → FAIL (module missing).

- [ ] **Step 4: Implement `ledger.py`**

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import frontmatter

_REQUIRED = ("id", "title", "status", "dod")


@dataclass
class Task:
    id: str
    title: str
    status: str
    dod: list[str]
    body: str
    path: Path


def _parse(path: Path) -> Task:
    post = frontmatter.load(str(path))
    meta = post.metadata
    missing = [k for k in _REQUIRED if k not in meta]
    if missing:
        raise ValueError(f"{path.name}: missing required field(s): {missing}")
    return Task(
        id=str(meta["id"]),
        title=str(meta["title"]),
        status=str(meta["status"]),
        dod=list(meta["dod"]),
        body=post.content,
        path=path,
    )


def load_tasks(tasks_dir: Path) -> list[Task]:
    return sorted((_parse(p) for p in tasks_dir.glob("T-*.md")), key=lambda t: t.id)


def next_todo(tasks: list[Task]) -> Task | None:
    return next((t for t in tasks if t.status == "todo"), None)


def set_status(task: Task, status: str) -> None:
    post = frontmatter.load(str(task.path))
    post["status"] = status
    task.path.write_text(frontmatter.dumps(post), encoding="utf-8")
    task.status = status
```

- [ ] **Step 5: Run to pass**

Run: `uv run pytest tests/unit/orchestrator/test_ledger.py -v` → 3 passed. Then `ruff` + `pyright`.

- [ ] **Step 6: Commit**

```bash
git add src/factory/orchestrator/ledger.py tasks/T-001-example.md tests/unit/orchestrator/test_ledger.py
git commit -m "feat: task ledger with frontmatter parsing and status updates"
```

---

### Task 3: Backend & gate interfaces + fakes + real gate runner

**Files:**
- Create: `src/factory/orchestrator/backends.py`
- Test: `tests/unit/orchestrator/test_backends.py`

**Interfaces:**
- Consumes: `AgentRole` (Task 1), `AgentResult` (Task 1).
- Produces:
  - `AgentBackend` Protocol: `run(role: AgentRole, prompt: str) -> AgentResult`.
  - `GateRunner` Protocol: `run(name: str) -> int`.
  - `FakeAgentBackend(scripts: dict[AgentRole, list[AgentResult]])` — pops the next scripted result per role; raises if none left.
  - `FakeGateRunner(results: dict[str, list[int]] | None = None)` — pops the next code for `name`; defaults to `0` when unscripted.
  - `SubprocessGateRunner(repo_root: Path)` — maps `"unit"|"sim"|"full"` to the Plan 1 gate scripts and returns the child exit code.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/orchestrator/test_backends.py
import pytest
from factory.orchestrator.types import AgentRole, AgentResult
from factory.orchestrator.backends import FakeAgentBackend, FakeGateRunner

pytestmark = pytest.mark.unit


def test_fake_backend_pops_in_order():
    b = FakeAgentBackend({AgentRole.DEV: [AgentResult(True, {"n": 1}), AgentResult(True, {"n": 2})]})
    assert b.run(AgentRole.DEV, "p").output["n"] == 1
    assert b.run(AgentRole.DEV, "p").output["n"] == 2


def test_fake_backend_exhausted_raises():
    b = FakeAgentBackend({AgentRole.DEV: []})
    with pytest.raises(AssertionError):
        b.run(AgentRole.DEV, "p")


def test_fake_gate_defaults_to_zero_then_scripted():
    g = FakeGateRunner({"unit": [1, 0]})
    assert g.run("unit") == 1
    assert g.run("unit") == 0
    assert g.run("sim") == 0  # unscripted default
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/orchestrator/test_backends.py -v` → FAIL (module missing).

- [ ] **Step 3: Implement `backends.py`**

```python
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Protocol

from factory.orchestrator.types import AgentResult, AgentRole


class AgentBackend(Protocol):
    def run(self, role: AgentRole, prompt: str) -> AgentResult: ...


class GateRunner(Protocol):
    def run(self, name: str) -> int: ...


class FakeAgentBackend:
    def __init__(self, scripts: dict[AgentRole, list[AgentResult]]) -> None:
        self._scripts = {k: list(v) for k, v in scripts.items()}

    def run(self, role: AgentRole, prompt: str) -> AgentResult:
        queue = self._scripts.get(role)
        assert queue, f"FakeAgentBackend: no scripted result for {role}"
        return queue.pop(0)


class FakeGateRunner:
    def __init__(self, results: dict[str, list[int]] | None = None) -> None:
        self._results = {k: list(v) for k, v in (results or {}).items()}

    def run(self, name: str) -> int:
        queue = self._results.get(name)
        if queue:
            return queue.pop(0)
        return 0


class SubprocessGateRunner:
    _SCRIPTS = {
        "unit": "scripts/gates/unit.py",
        "sim": "scripts/gates/sim_smoke.py",
        "full": "scripts/gates/all.py",
    }

    def __init__(self, repo_root: Path) -> None:
        self._repo_root = repo_root

    def run(self, name: str) -> int:
        script = self._SCRIPTS[name]
        return subprocess.run([sys.executable, script], cwd=self._repo_root).returncode
```

- [ ] **Step 4: Run to pass**

Run: `uv run pytest tests/unit/orchestrator/test_backends.py -v` → 3 passed. Then `ruff` + `pyright`.

- [ ] **Step 5: Commit**

```bash
git add src/factory/orchestrator/backends.py tests/unit/orchestrator/test_backends.py
git commit -m "feat: agent/gate interfaces with fakes and subprocess gate runner"
```

---

### Task 4: Prompt composition

**Files:**
- Create: `src/factory/orchestrator/prompts.py`
- Test: `tests/unit/orchestrator/test_prompts.py`

**Interfaces:**
- Consumes: `AgentRole`, `ROLE_PROMPTS`, `ROLE_SKILLS` (Tasks 1), `Task` (Task 2).
- Produces: `compose_prompt(role: AgentRole, task: Task, manifest: dict | None = None, kb_entries: list[dict] | None = None, feedback: str | None = None) -> str` — deterministic assembly: role instruction, loaded skills, task id/title/body, DoD list, KB rules (id + `title`), optional manifest context files, optional feedback. Same inputs ⇒ byte-identical output.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/orchestrator/test_prompts.py
import pytest
from pathlib import Path
from factory.orchestrator.types import AgentRole
from factory.orchestrator.ledger import Task
from factory.orchestrator.prompts import compose_prompt

pytestmark = pytest.mark.unit

TASK = Task(id="T-001", title="Do X", status="todo", dod=["crit A"], body="body text", path=Path("t"))


def test_prompt_is_deterministic_and_includes_key_parts():
    kb = [{"id": "kb-0001", "title": "watch arming"}]
    a = compose_prompt(AgentRole.DEV, TASK, manifest=None, kb_entries=kb, feedback="fix Y")
    b = compose_prompt(AgentRole.DEV, TASK, manifest=None, kb_entries=kb, feedback="fix Y")
    assert a == b
    for needle in ["T-001", "Do X", "crit A", "kb-0001", "watch arming", "fix Y", "test-driven-development"]:
        assert needle in a


def test_no_feedback_no_kb_still_valid():
    out = compose_prompt(AgentRole.REVIEW, TASK)
    assert "T-001" in out and "crit A" in out
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/orchestrator/test_prompts.py -v` → FAIL (module missing).

- [ ] **Step 3: Implement `prompts.py`**

```python
from __future__ import annotations

from factory.orchestrator.ledger import Task
from factory.orchestrator.roles import ROLE_PROMPTS, ROLE_SKILLS
from factory.orchestrator.types import AgentRole


def compose_prompt(
    role: AgentRole,
    task: Task,
    manifest: dict | None = None,
    kb_entries: list[dict] | None = None,
    feedback: str | None = None,
) -> str:
    lines: list[str] = []
    lines.append(f"# Role: {role.value}")
    lines.append(ROLE_PROMPTS[role])
    lines.append("")
    lines.append("## Loaded skills")
    for skill in ROLE_SKILLS[role]:
        lines.append(f"- {skill}")
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
        for f in manifest.get("context", {}).get("source_files", []):
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

- [ ] **Step 4: Run to pass**

Run: `uv run pytest tests/unit/orchestrator/test_prompts.py -v` → 2 passed. Then `ruff` + `pyright`.

- [ ] **Step 5: Commit**

```bash
git add src/factory/orchestrator/prompts.py tests/unit/orchestrator/test_prompts.py
git commit -m "feat: deterministic prompt composition per agent role"
```

---

### Task 5: Node executors — Context-Gatherer & Dev

**Files:**
- Create: `src/factory/orchestrator/nodes.py`
- Test: `tests/unit/orchestrator/test_nodes_context_dev.py`

**Interfaces:**
- Consumes: `AgentBackend`, `GateRunner` (Task 3), `compose_prompt` (Task 4), `validate_manifest` (Plan 1 Task 5), `NodeOutcome`, `NodeEvent`, `AgentRole` (Task 1), `Task` (Task 2).
- Produces:
  - `run_context_gatherer(backend, task, repo_root, max_attempts=2) -> tuple[NodeOutcome, dict | None, NodeEvent]` — runs the agent; if its output declares `reject` or fails schema/`proven`, retries up to `max_attempts`, else `REJECT`. On a valid proven manifest ⇒ `(PASS, manifest, event)`.
  - `run_dev(backend, gates, task, manifest, kb_entries, max_iters=3, feedback=None) -> tuple[NodeOutcome, NodeEvent]` — loops: run Dev agent, run `unit` gate; `PASS` when green, else retry; exhaustion ⇒ `ESCALATE`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/orchestrator/test_nodes_context_dev.py
import pytest
from pathlib import Path
from factory.orchestrator.types import AgentRole, AgentResult, NodeOutcome
from factory.orchestrator.ledger import Task
from factory.orchestrator.backends import FakeAgentBackend, FakeGateRunner
from factory.orchestrator.nodes import run_context_gatherer, run_dev

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
    b = FakeAgentBackend({AgentRole.CONTEXT_GATHERER: [AgentResult(True, _manifest(tmp_path))]})
    outcome, manifest, ev = run_context_gatherer(b, _task(), tmp_path)
    assert outcome == NodeOutcome.PASS and manifest is not None and ev.result == "pass"


def test_context_gatherer_reject_on_reject_field(tmp_path):
    m = _manifest(tmp_path, proven=False, reject={"reason": "DoD unclear"})
    b = FakeAgentBackend({AgentRole.CONTEXT_GATHERER: [AgentResult(True, m)]})
    outcome, manifest, ev = run_context_gatherer(b, _task(), tmp_path)
    assert outcome == NodeOutcome.REJECT and manifest is None


def test_dev_passes_when_unit_green():
    b = FakeAgentBackend({AgentRole.DEV: [AgentResult(True, {})]})
    g = FakeGateRunner({"unit": [0]})
    outcome, ev = run_dev(b, g, _task(), {}, [])
    assert outcome == NodeOutcome.PASS


def test_dev_escalates_when_unit_never_green():
    b = FakeAgentBackend({AgentRole.DEV: [AgentResult(True, {}) for _ in range(3)]})
    g = FakeGateRunner({"unit": [1, 1, 1]})
    outcome, ev = run_dev(b, g, _task(), {}, [], max_iters=3)
    assert outcome == NodeOutcome.ESCALATE and ev.attempts == 3
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/orchestrator/test_nodes_context_dev.py -v` → FAIL (module missing).

- [ ] **Step 3: Implement the two executors in `nodes.py`**

```python
from __future__ import annotations

from pathlib import Path

from factory.orchestrator.backends import AgentBackend, GateRunner
from factory.orchestrator.ledger import Task
from factory.orchestrator.prompts import compose_prompt
from factory.orchestrator.types import AgentRole, NodeEvent, NodeOutcome
from factory.validation.manifest_validator import validate_manifest


def run_context_gatherer(
    backend: AgentBackend, task: Task, repo_root: Path, max_attempts: int = 2
) -> tuple[NodeOutcome, dict | None, NodeEvent]:
    errors: list[str] = []
    for attempt in range(1, max_attempts + 1):
        result = backend.run(AgentRole.CONTEXT_GATHERER, compose_prompt(AgentRole.CONTEXT_GATHERER, task))
        manifest = result.output
        if manifest.get("reject"):
            return NodeOutcome.REJECT, None, NodeEvent("context-gather", "reject", attempt,
                                                       {"reason": manifest["reject"]})
        errors = validate_manifest(manifest, repo_root)
        if not errors and manifest.get("coherence", {}).get("proven"):
            return NodeOutcome.PASS, manifest, NodeEvent("context-gather", "pass", attempt)
    return NodeOutcome.REJECT, None, NodeEvent("context-gather", "reject", max_attempts, {"errors": errors})


def run_dev(
    backend: AgentBackend,
    gates: GateRunner,
    task: Task,
    manifest: dict,
    kb_entries: list[dict],
    max_iters: int = 3,
    feedback: str | None = None,
) -> tuple[NodeOutcome, NodeEvent]:
    for attempt in range(1, max_iters + 1):
        backend.run(AgentRole.DEV, compose_prompt(AgentRole.DEV, task, manifest, kb_entries, feedback))
        if gates.run("unit") == 0:
            return NodeOutcome.PASS, NodeEvent("dev", "pass", attempt, {"tests": "green"})
    return NodeOutcome.ESCALATE, NodeEvent("dev", "escalate", max_iters, {"reason": "unit tests red"})
```

- [ ] **Step 4: Run to pass**

Run: `uv run pytest tests/unit/orchestrator/test_nodes_context_dev.py -v` → 4 passed. Then `ruff` + `pyright`.

- [ ] **Step 5: Commit**

```bash
git add src/factory/orchestrator/nodes.py tests/unit/orchestrator/test_nodes_context_dev.py
git commit -m "feat: context-gatherer and dev node executors"
```

---

### Task 6: Node executors — Validation & Review

**Files:**
- Modify: `src/factory/orchestrator/nodes.py`
- Test: `tests/unit/orchestrator/test_nodes_val_review.py`

**Interfaces:**
- Consumes: same as Task 5.
- Produces:
  - `run_validation(gates) -> tuple[NodeOutcome, NodeEvent]` — runs the `sim` gate; `PASS` on 0 else `FAIL`.
  - `run_review(backend, gates, task) -> tuple[NodeOutcome, NodeEvent, list[str]]` — runs the Review agent (expects output `{dod_met, findings}`) and the `full` gate; `PASS` only when `full == 0` AND `dod_met` truthy AND no findings; otherwise `CHANGES` with the findings list returned for feedback.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/orchestrator/test_nodes_val_review.py
import pytest
from pathlib import Path
from factory.orchestrator.types import AgentRole, AgentResult, NodeOutcome
from factory.orchestrator.ledger import Task
from factory.orchestrator.backends import FakeAgentBackend, FakeGateRunner
from factory.orchestrator.nodes import run_validation, run_review

pytestmark = pytest.mark.unit


def _task():
    return Task("T-001", "t", "todo", ["c"], "body", Path("t"))


def test_validation_pass_and_fail():
    assert run_validation(FakeGateRunner({"sim": [0]}))[0] == NodeOutcome.PASS
    assert run_validation(FakeGateRunner({"sim": [1]}))[0] == NodeOutcome.FAIL


def test_review_pass_requires_green_gate_and_dod_and_no_findings():
    b = FakeAgentBackend({AgentRole.REVIEW: [AgentResult(True, {"dod_met": True, "findings": []})]})
    outcome, ev, findings = run_review(b, FakeGateRunner({"full": [0]}), _task())
    assert outcome == NodeOutcome.PASS and findings == []


def test_review_changes_when_findings_present():
    b = FakeAgentBackend({AgentRole.REVIEW: [AgentResult(True, {"dod_met": True, "findings": ["DRY: dup"]})]})
    outcome, ev, findings = run_review(b, FakeGateRunner({"full": [0]}), _task())
    assert outcome == NodeOutcome.CHANGES and findings == ["DRY: dup"]


def test_review_changes_when_gate_red_even_if_dod_claimed():
    b = FakeAgentBackend({AgentRole.REVIEW: [AgentResult(True, {"dod_met": True, "findings": []})]})
    outcome, ev, findings = run_review(b, FakeGateRunner({"full": [1]}), _task())
    assert outcome == NodeOutcome.CHANGES  # cannot self-certify past a red gate
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/orchestrator/test_nodes_val_review.py -v` → FAIL (functions missing).

- [ ] **Step 3: Append to `nodes.py`**

```python
def run_validation(gates: GateRunner) -> tuple[NodeOutcome, NodeEvent]:
    if gates.run("sim") == 0:
        return NodeOutcome.PASS, NodeEvent("validation", "pass")
    return NodeOutcome.FAIL, NodeEvent("validation", "fail")


def run_review(
    backend: AgentBackend, gates: GateRunner, task: Task
) -> tuple[NodeOutcome, NodeEvent, list[str]]:
    result = backend.run(AgentRole.REVIEW, compose_prompt(AgentRole.REVIEW, task))
    out = result.output
    findings = list(out.get("findings", []))
    dod_met = bool(out.get("dod_met"))
    gate = gates.run("full")
    if gate == 0 and dod_met and not findings:
        return NodeOutcome.PASS, NodeEvent("review", "pass"), []
    return (
        NodeOutcome.CHANGES,
        NodeEvent("review", "changes-requested", 1, {"findings": len(findings), "gate": gate}),
        findings,
    )
```

- [ ] **Step 4: Run to pass**

Run: `uv run pytest tests/unit/orchestrator/test_nodes_val_review.py -v` → 4 passed. Then `ruff` + `pyright`.

- [ ] **Step 5: Commit**

```bash
git add src/factory/orchestrator/nodes.py tests/unit/orchestrator/test_nodes_val_review.py
git commit -m "feat: validation and review node executors with deterministic gate"
```

---

### Task 7: Session record builder & writer

**Files:**
- Create: `src/factory/orchestrator/session.py`
- Test: `tests/unit/orchestrator/test_session.py`

**Interfaces:**
- Consumes: `TaskResult`, `NodeEvent` (Task 1), `validate_session` (Plan 1 Task 6).
- Produces:
  - `build_record(session_id, model_backend, results: list[TaskResult], git_info: dict) -> dict` — assembles a session record matching the Plan 1 schema (`nodes` from each result's events; `dod.met` from `dod_met`).
  - `write_session(sessions_dir: Path, record: dict) -> Path` — validates via `validate_session`, raises `ValueError` on any error, else writes `<session_id>.session.json` and a `latest.md` digest; returns the JSON path.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/orchestrator/test_session.py
import json
import pytest
from factory.orchestrator.types import TaskResult, NodeEvent
from factory.orchestrator.session import build_record, write_session

pytestmark = pytest.mark.unit


def _result(outcome="completed", dod_met=True):
    return TaskResult("T-001", "t", outcome, 1, [NodeEvent("dev", "pass")], dod_met, None)


def test_build_and_write_valid(tmp_path):
    rec = build_record("s1", "anthropic:claude-opus-4-8", [_result()], {"branch": "main"})
    path = write_session(tmp_path, rec)
    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8"))["tasks"][0]["task_id"] == "T-001"
    assert (tmp_path / "latest.md").exists()


def test_write_rejects_invalid_record(tmp_path):
    # completed but dod not met -> Plan 1 session validator fails
    rec = build_record("s1", "backend", [_result(dod_met=False)], {})
    with pytest.raises(ValueError):
        write_session(tmp_path, rec)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/orchestrator/test_session.py -v` → FAIL (module missing).

- [ ] **Step 3: Implement `session.py`**

```python
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from factory.orchestrator.types import TaskResult
from factory.validation.session_validator import validate_session


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_record(
    session_id: str, model_backend: str, results: list[TaskResult], git_info: dict
) -> dict:
    tasks = []
    for r in results:
        tasks.append(
            {
                "task_id": r.task_id,
                "title": r.title,
                "outcome": r.outcome,
                "iterations": r.iterations,
                "nodes": [
                    {"node": e.node, "result": e.result, "attempts": e.attempts} for e in r.events
                ],
                "commits": [],
                "dod": {"met": r.dod_met},
            }
        )
    return {
        "session_id": session_id,
        "started_at": _now(),
        "ended_at": _now(),
        "model_backend": model_backend,
        "git": git_info,
        "tasks": tasks,
        "kb_changes": {"added": [], "updated": [], "pruned": []},
        "escalations": [t["task_id"] for t in tasks if t["outcome"] == "escalated"],
        "resume": {"next_task": None, "hint": ""},
    }


def write_session(sessions_dir: Path, record: dict) -> Path:
    errors = validate_session(record)
    if errors:
        raise ValueError(f"invalid session record: {errors}")
    sessions_dir.mkdir(parents=True, exist_ok=True)
    path = sessions_dir / f"{record['session_id']}.session.json"
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")

    digest = [f"# Session {record['session_id']}", ""]
    for t in record["tasks"]:
        digest.append(f"- {t['task_id']} ({t['outcome']}, {t['iterations']} iters): {t.get('title', '')}")
    (sessions_dir / "latest.md").write_text("\n".join(digest) + "\n", encoding="utf-8")
    return path
```

- [ ] **Step 4: Run to pass**

Run: `uv run pytest tests/unit/orchestrator/test_session.py -v` → 2 passed. Then `ruff` + `pyright`.

- [ ] **Step 5: Commit**

```bash
git add src/factory/orchestrator/session.py tests/unit/orchestrator/test_session.py
git commit -m "feat: session record builder and validated writer"
```

---

### Task 8: State machine `run_task` + KB loading (deterministic e2e)

**Files:**
- Create: `src/factory/orchestrator/runner.py`
- Test: `tests/unit/orchestrator/test_runner_e2e.py`

**Interfaces:**
- Consumes: all node executors (Tasks 5–6), `select_entries` (Plan 1 Task 8), `parse_entry` (Plan 1 Task 7), `Task` (Task 2), `TaskResult` (Task 1).
- Produces:
  - `_load_kb_entries(kb_dir: Path, ids: list[str]) -> list[dict]`.
  - `run_task(task, backend, gates, repo_root, *, max_dev_iters=3, max_review_cycles=3) -> TaskResult` — the full graph with circuit breakers. Context reject ⇒ `rejected`; Dev escalate or review-cycle exhaustion ⇒ `escalated`; review pass ⇒ `completed`. Validation fail loops back to Dev with feedback.

- [ ] **Step 1: Write the failing e2e test**

```python
# tests/unit/orchestrator/test_runner_e2e.py
import pytest
from pathlib import Path
from factory.orchestrator.types import AgentRole, AgentResult
from factory.orchestrator.ledger import Task
from factory.orchestrator.backends import FakeAgentBackend, FakeGateRunner
from factory.orchestrator.runner import run_task

pytestmark = pytest.mark.unit


def _repo(tmp_path):
    (tmp_path / "tasks").mkdir()
    (tmp_path / "tasks" / "T-001.md").write_text("dod", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "x.py").write_text("x = 1\n", encoding="utf-8")
    return tmp_path


def _manifest():
    return {
        "task_id": "T-001", "generated_by": "context-gatherer",
        "generated_at": "2026-07-16T14:32:10Z",
        "coherence": {"proven": True, "checks": [{"name": "x", "pass": True}]},
        "context": {"task": "tasks/T-001.md", "source_files": ["src/x.py"], "skills": []},
        "reject": None,
    }


def _scripts():
    # review: changes once, then pass -> exercises the dev<->review loop
    return {
        AgentRole.CONTEXT_GATHERER: [AgentResult(True, _manifest())],
        AgentRole.DEV: [AgentResult(True, {}), AgentResult(True, {})],
        AgentRole.REVIEW: [
            AgentResult(True, {"dod_met": False, "findings": ["fix"]}),
            AgentResult(True, {"dod_met": True, "findings": []}),
        ],
    }


def test_full_pipeline_completes_and_is_deterministic(tmp_path):
    repo = _repo(tmp_path)
    task = Task("T-001", "t", "todo", ["c"], "body", repo / "tasks" / "T-001.md")

    def run():
        return run_task(task, FakeAgentBackend(_scripts()), FakeGateRunner(), repo,
                        max_review_cycles=3)

    r1 = run()
    r2 = run()
    assert r1.outcome == "completed" and r1.dod_met is True
    assert r1.iterations == 2
    seq1 = [(e.node, e.result) for e in r1.events]
    seq2 = [(e.node, e.result) for e in r2.events]
    assert seq1 == seq2  # deterministic routing
    assert ("review", "pass") in seq1


def test_context_reject_short_circuits(tmp_path):
    repo = _repo(tmp_path)
    task = Task("T-001", "t", "todo", ["c"], "body", repo / "tasks" / "T-001.md")
    scripts = {AgentRole.CONTEXT_GATHERER: [AgentResult(True, {**_manifest(), "reject": {"reason": "x"},
                                                              "coherence": {"proven": False, "checks": []}})]}
    r = run_task(task, FakeAgentBackend(scripts), FakeGateRunner(), repo)
    assert r.outcome == "rejected"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/orchestrator/test_runner_e2e.py -v` → FAIL (module missing).

- [ ] **Step 3: Implement `runner.py`**

```python
from __future__ import annotations

from pathlib import Path

from factory.kb.retrieval import select_entries
from factory.orchestrator.backends import AgentBackend, GateRunner
from factory.orchestrator.ledger import Task
from factory.orchestrator.nodes import (
    run_context_gatherer,
    run_dev,
    run_review,
    run_validation,
)
from factory.orchestrator.types import NodeEvent, NodeOutcome, TaskResult
from factory.validation.kb_validator import parse_entry


def _load_kb_entries(kb_dir: Path, ids: list[str]) -> list[dict]:
    if not kb_dir.exists():
        return []
    wanted = set(ids)
    out = []
    for path in sorted(kb_dir.glob("kb-*.md")):
        entry = parse_entry(path)
        if str(entry.get("id")) in wanted:
            out.append(entry)
    return out


def run_task(
    task: Task,
    backend: AgentBackend,
    gates: GateRunner,
    repo_root: Path,
    *,
    max_dev_iters: int = 3,
    max_review_cycles: int = 3,
) -> TaskResult:
    events: list[NodeEvent] = []

    c_outcome, manifest, c_ev = run_context_gatherer(backend, task, repo_root)
    events.append(c_ev)
    if c_outcome == NodeOutcome.REJECT or manifest is None:
        return TaskResult(task.id, task.title, "rejected", 1, events, False, None)

    kb_ids = select_entries(repo_root / "kb", manifest["context"].get("source_files", []), [])
    kb_entries = _load_kb_entries(repo_root / "kb", kb_ids)

    feedback: str | None = None
    iterations = 0
    for _ in range(max_review_cycles):
        iterations += 1

        d_outcome, d_ev = run_dev(backend, gates, task, manifest, kb_entries, max_dev_iters, feedback)
        events.append(d_ev)
        if d_outcome == NodeOutcome.ESCALATE:
            return TaskResult(task.id, task.title, "escalated", iterations, events, False, manifest)

        v_outcome, v_ev = run_validation(gates)
        events.append(v_ev)
        if v_outcome == NodeOutcome.FAIL:
            feedback = "functional/sim tests failed"
            continue

        r_outcome, r_ev, findings = run_review(backend, gates, task)
        events.append(r_ev)
        if r_outcome == NodeOutcome.PASS:
            return TaskResult(task.id, task.title, "completed", iterations, events, True, manifest)
        feedback = "\n".join(findings) if findings else "review requested changes"

    return TaskResult(task.id, task.title, "escalated", iterations, events, False, manifest)
```

- [ ] **Step 4: Run to pass**

Run: `uv run pytest tests/unit/orchestrator/test_runner_e2e.py -v` → 2 passed. Then `ruff` + `pyright`.

- [ ] **Step 5: Commit**

```bash
git add src/factory/orchestrator/runner.py tests/unit/orchestrator/test_runner_e2e.py
git commit -m "feat: deterministic run_task state machine with circuit breakers"
```

---

### Task 9: `run_next` + CLI entrypoint

**Files:**
- Create: `src/factory/orchestrator/__main__.py`
- Modify: `src/factory/orchestrator/runner.py`
- Test: `tests/unit/orchestrator/test_run_next.py`

**Interfaces:**
- Consumes: `load_tasks`, `next_todo`, `set_status` (Task 2), `run_task` (Task 8), `build_record`, `write_session` (Task 7).
- Produces:
  - `run_next(repo_root, backend, gates, *, model_backend="anthropic:claude-opus-4-8", session_id=None, git_info=None) -> Path | None` — picks the next todo task, runs it, updates ledger status (`completed`→`done`, else the outcome), writes a validated session record, returns the session path (or `None` if no todo).
  - `__main__.py`: `python -m factory.orchestrator run` wiring `PiAgentBackend` + `SubprocessGateRunner`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/orchestrator/test_run_next.py
import json
import pytest
from pathlib import Path
from factory.orchestrator.types import AgentRole, AgentResult
from factory.orchestrator.backends import FakeAgentBackend, FakeGateRunner
from factory.orchestrator.ledger import load_tasks
from factory.orchestrator.runner import run_next

pytestmark = pytest.mark.unit


def _repo(tmp_path):
    (tmp_path / "tasks").mkdir()
    (tmp_path / "tasks" / "T-001.md").write_text(
        "---\nid: T-001\ntitle: t\nstatus: todo\ndod:\n  - c\n---\nbody\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "x.py").write_text("x = 1\n", encoding="utf-8")
    return tmp_path


def _scripts():
    manifest = {
        "task_id": "T-001", "generated_by": "context-gatherer",
        "generated_at": "2026-07-16T14:32:10Z",
        "coherence": {"proven": True, "checks": [{"name": "x", "pass": True}]},
        "context": {"task": "tasks/T-001.md", "source_files": ["src/x.py"], "skills": []},
        "reject": None,
    }
    return {
        AgentRole.CONTEXT_GATHERER: [AgentResult(True, manifest)],
        AgentRole.DEV: [AgentResult(True, {})],
        AgentRole.REVIEW: [AgentResult(True, {"dod_met": True, "findings": []})],
    }


def test_run_next_writes_session_and_marks_done(tmp_path):
    repo = _repo(tmp_path)
    path = run_next(repo, FakeAgentBackend(_scripts()), FakeGateRunner(),
                    session_id="s1", git_info={"branch": "main"})
    assert path and path.exists()
    assert json.loads(path.read_text(encoding="utf-8"))["tasks"][0]["outcome"] == "completed"
    assert load_tasks(repo / "tasks")[0].status == "done"


def test_run_next_none_when_no_todo(tmp_path):
    (tmp_path / "tasks").mkdir()
    assert run_next(tmp_path, FakeAgentBackend({}), FakeGateRunner(), session_id="s1") is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/orchestrator/test_run_next.py -v` → FAIL (`run_next` missing).

- [ ] **Step 3: Append `run_next` to `runner.py`**

```python
from factory.orchestrator.ledger import load_tasks, next_todo, set_status
from factory.orchestrator.session import build_record, write_session


def run_next(
    repo_root: Path,
    backend: AgentBackend,
    gates: GateRunner,
    *,
    model_backend: str = "anthropic:claude-opus-4-8",
    session_id: str | None = None,
    git_info: dict | None = None,
) -> Path | None:
    tasks = load_tasks(repo_root / "tasks")
    task = next_todo(tasks)
    if task is None:
        return None

    result = run_task(task, backend, gates, repo_root)
    set_status(task, "done" if result.outcome == "completed" else result.outcome)

    sid = session_id or _default_session_id()
    record = build_record(sid, model_backend, [result], git_info or {})
    return write_session(repo_root / "sessions", record)


def _default_session_id() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
```

- [ ] **Step 4: Write `__main__.py`**

```python
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from factory.orchestrator.backends import SubprocessGateRunner
from factory.orchestrator.pi_backend import PiAgentBackend
from factory.orchestrator.runner import run_next


def _git_info(repo_root: Path) -> dict:
    def _cmd(args: list[str]) -> str:
        return subprocess.run(["git", *args], cwd=repo_root, capture_output=True, text=True).stdout.strip()

    return {"branch": _cmd(["rev-parse", "--abbrev-ref", "HEAD"]), "head": _cmd(["rev-parse", "HEAD"])}


def main() -> None:
    parser = argparse.ArgumentParser(prog="factory.orchestrator")
    parser.add_argument("command", choices=["run"])
    parser.add_argument("--repo", default=".")
    args = parser.parse_args()

    repo_root = Path(args.repo).resolve()
    ext = repo_root / "pi-ext" / "scope-guard" / "src" / "index.ts"
    backend = PiAgentBackend(repo_root=repo_root, extension_path=ext)
    gates = SubprocessGateRunner(repo_root)

    path = run_next(repo_root, backend, gates, git_info=_git_info(repo_root))
    print("no todo tasks" if path is None else f"session written: {path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run to pass**

Run: `uv run pytest tests/unit/orchestrator/test_run_next.py -v` → 2 passed. (`__main__` imports `pi_backend`, delivered next task; if running the CLI before Task 10, it will error — the unit tests here do not import `__main__`.) Then `ruff` + `pyright` (pyright will flag the missing `pi_backend` import until Task 10 — implement Task 10 before the final green check, or run `pyright` after Task 10).

- [ ] **Step 6: Commit**

```bash
git add src/factory/orchestrator/runner.py src/factory/orchestrator/__main__.py tests/unit/orchestrator/test_run_next.py
git commit -m "feat: run_next orchestration entry and CLI"
```

---

### Task 10: `PiAgentBackend` (real) + JSON parsing + live spike

**Files:**
- Create: `src/factory/orchestrator/pi_backend.py`
- Test: `tests/unit/orchestrator/test_pi_parse.py`

**Interfaces:**
- Consumes: `AgentRole`, `AgentResult` (Task 1), `ROLE_SCOPE` (Task 1).
- Produces:
  - `parse_pi_json(stdout: str) -> dict` — given Pi's `--mode json` line-delimited event stream, reconstruct the assistant's final text and extract the last fenced ```json block as a dict (returns `{}` if none).
  - `PiAgentBackend(repo_root, extension_path, model=None)` implementing `AgentBackend.run` by spawning `pi -p <prompt> --mode json --extension <ext>` with `PI_SCOPE_ALLOW`/`PI_SCOPE_BASH` from `ROLE_SCOPE[role]`.

- [ ] **Step 1: Write the failing test (against a captured fixture stream)**

```python
# tests/unit/orchestrator/test_pi_parse.py
import pytest
from factory.orchestrator.pi_backend import parse_pi_json

pytestmark = pytest.mark.unit

# Minimal stand-in for Pi's json event stream: assistant text deltas carrying a json block.
STREAM = "\n".join([
    '{"type": "assistant_text", "text": "Here is the manifest:\\n```json\\n{\\"task_id\\": \\"T-001\\","}',
    '{"type": "assistant_text", "text": " \\"ok\\": true}\\n```\\nDone."}',
])


def test_parse_extracts_last_json_block():
    out = parse_pi_json(STREAM)
    assert out["task_id"] == "T-001"
    assert out["ok"] is True


def test_parse_returns_empty_when_no_block():
    assert parse_pi_json('{"type":"assistant_text","text":"no json here"}') == {}
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/orchestrator/test_pi_parse.py -v` → FAIL (module missing).

- [ ] **Step 3: Implement `pi_backend.py`**

```python
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from factory.orchestrator.roles import ROLE_SCOPE
from factory.orchestrator.types import AgentResult, AgentRole

_JSON_BLOCK = re.compile(r"```json\s*(.*?)```", re.DOTALL)


def parse_pi_json(stdout: str) -> dict:
    """Reconstruct assistant text from Pi's json event stream, return last ```json block."""
    text_parts: list[str] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and isinstance(event.get("text"), str):
            text_parts.append(event["text"])
    full = "".join(text_parts)
    blocks = _JSON_BLOCK.findall(full)
    if not blocks:
        return {}
    try:
        return json.loads(blocks[-1])
    except json.JSONDecodeError:
        return {}


class PiAgentBackend:
    def __init__(self, repo_root: Path, extension_path: Path, model: str | None = None) -> None:
        self._repo_root = repo_root
        self._extension_path = extension_path
        self._model = model

    def run(self, role: AgentRole, prompt: str) -> AgentResult:
        scope = ROLE_SCOPE[role]
        env = {
            **os.environ,
            "PI_SCOPE_ALLOW": ",".join(scope.allow),
            "PI_SCOPE_BASH": scope.bash,
        }
        cmd = ["pi", "-p", prompt, "--mode", "json", "--extension", str(self._extension_path)]
        proc = subprocess.run(
            cmd, cwd=self._repo_root, env=env, capture_output=True, text=True
        )
        return AgentResult(ok=proc.returncode == 0, output=parse_pi_json(proc.stdout), raw=proc.stdout)
```

- [ ] **Step 4: Run to pass**

Run: `uv run pytest tests/unit/orchestrator/test_pi_parse.py -v` → 2 passed. Then `uv run ruff check . && uv run pyright` (now green — `pi_backend` exists for Task 9's CLI import).

- [ ] **Step 5: Live spike — confirm the real event shape (one-time)**

> `parse_pi_json` assumes events carry assistant text on a `text` field. Confirm against the real stream from Plan 2's Task 5 spike (or run now):

```bash
pi -p "Reply with a fenced json block: {\"ok\": true}" --mode json > /tmp/pi_stream.txt
uv run python -c "from pathlib import Path; from factory.orchestrator.pi_backend import parse_pi_json; print(parse_pi_json(Path('/tmp/pi_stream.txt').read_text()))"
```
Expected: `{'ok': True}`. If the field name differs (e.g. `delta`/`content`), adjust the `event.get("text")` line and the fixture in Step 1 to match, then re-run.

- [ ] **Step 6: Commit**

```bash
git add src/factory/orchestrator/pi_backend.py tests/unit/orchestrator/test_pi_parse.py
git commit -m "feat: PiAgentBackend driving pi with scope-guard and json parsing"
```

---

## Self-Review

**Spec coverage (against `2026-07-16-deterministic-agent-dev-factory-design.md`):**
- §4 orchestrator (task ledger, context injection, gates, routing, circuit breakers, model-backend) → Tasks 2, 4, 8, 9, 10.
- §5 pipeline + routing-on-exit-codes + `dod_met ⇒ gates green` → Tasks 5–8 (`run_review` cannot PASS past a red `full` gate).
- §6 per-agent skills + permission profiles → Task 1 (`ROLE_SKILLS`, `ROLE_SCOPE`) injected to `scope-guard` via env (Task 10).
- §7 context manifest consumed + validated → Task 5 (`run_context_gatherer` uses Plan 1 `validate_manifest`).
- §8 deterministic KB retrieval feeding Dev → Task 8 (`select_entries` + `_load_kb_entries`).
- §9 session record written + validated + resume digest → Task 7 + Task 9.
- §5 circuit breaker (max iters → escalate) → Tasks 5, 8.
- §12 KB-Manager deferred; §10 local-model backend deferred (interface `AgentBackend` ready) — both explicitly out of scope.

**Placeholder scan:** none. The two non-code steps (Task 10 Step 5 live spike; the pyright note in Task 9 Step 5) are exact commands with expected output, not hidden logic.

**Type consistency:** `AgentRole`/`AgentResult`/`NodeEvent`/`NodeOutcome`/`TaskResult` (Task 1) used unchanged throughout; `AgentBackend`/`GateRunner` (Task 3) consumed by all node executors and `run_task`; `compose_prompt` signature (Task 4) matches every call site in Tasks 5–6; `run_context_gatherer`/`run_dev`/`run_validation`/`run_review` signatures (Tasks 5–6) match `run_task`'s calls (Task 8); `build_record`/`write_session` (Task 7) match `run_next` (Task 9); `parse_pi_json`/`PiAgentBackend` (Task 10) match the CLI wiring (Task 9).

**Cross-plan dependency note:** consumes Plan 1 (`validate_manifest`, `validate_session`, `select_entries`, `parse_entry`, gate scripts) and Plan 2 (`scope-guard` extension path + env contract). Task 9's `pyright` goes fully green only after Task 10 (the CLI imports `pi_backend`); implement 9→10 back-to-back.
```
