# Factory Status Reporting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the factory orchestrator a live, file-based status channel (current node, attempt, outcome, a short live snippet of the running sub-agent's output) and a PID lock file, so a separate watcher (Plan B: the `factory-watch` Pi extension) can observe and cancel a run without any new IPC mechanism.

**Architecture:** An optional, injectable `StatusReporter` (mirroring the existing `AgentBackend`/`GateRunner` Protocol+Fake pattern) is threaded through the node executors and `run_task`/`run_next`, defaulting to a no-op so every existing test is untouched. `PiAgentBackend` switches from blocking `subprocess.run` to streaming `Popen`, so it can report a live snippet as sub-agent output arrives. `__main__.py` owns all the "real world" plumbing (the actual status file, the PID lock file, crash-to-error-status handling) — the core orchestrator stays fully unit-testable with fakes and gains zero new runtime dependencies.

**Tech Stack:** Python 3.11, `pytest` (marker `unit`), stdlib only (`json`, `os`, `subprocess`, `dataclasses`). No new dependencies.

## Global Constraints

- Python **>= 3.11**; reuse the existing `uv` env, no new dependencies.
- **No new IPC mechanism.** Status and lock state are files under `sessions/`, matching the factory's existing file-based communication convention (task ledger, session records, KB).
- **The status file is NOT JSON-Schema-validated.** Unlike context manifests/session records, nothing routes on it — it's purely observational. Adding schema validation here would be unneeded machinery (see spec §6).
- **All new `status`/callback parameters are optional with safe defaults.** Every existing test in `tests/unit/orchestrator/` must keep passing unmodified.
- **Windows is a first-class target** (this project runs on Windows 10 + PowerShell). PID-liveness checking must actually work there, not just assume POSIX `os.kill(pid, 0)` semantics.
- Every task ends green (`ruff`, `pyright`, unit tests) and is committed.
- This is Plan A of a two-plan feature. Plan B (`pi-ext/factory-watch/`, a new Pi extension) consumes this plan's status file format and PID lock file and is planned/implemented separately.

Full design: `docs/superpowers/specs/2026-07-20-factory-live-visualization-design.md`.

---

## File Structure

```
src/factory/orchestrator/
  status.py          # NEW: StatusReporter protocol, Null/File/Fake implementations
  lock.py             # NEW: PID lock file (read/write/remove/is_pid_alive/acquire_lock)
  backends.py         # MODIFY: AgentBackend.run gains on_snippet param
  nodes.py            # MODIFY: node executors accept+report status
  runner.py           # MODIFY: run_task/run_next thread status through
  pi_backend.py       # MODIFY: streaming Popen + live snippet
  __main__.py         # MODIFY: lock file lifecycle, FileStatusReporter wiring, crash handling
tests/unit/orchestrator/
  test_status.py      # NEW
  test_lock.py         # NEW
  test_backends.py     # MODIFY
  test_nodes_context_dev.py   # MODIFY
  test_nodes_val_review.py    # MODIFY
  test_runner_e2e.py   # MODIFY
  test_run_next.py     # MODIFY
  test_pi_parse.py     # MODIFY
```

---

### Task 1: Status reporter

**Files:**
- Create: `src/factory/orchestrator/status.py`
- Test: `tests/unit/orchestrator/test_status.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `StatusReporter` Protocol: `report(*, task_id: str, node: str, node_state: str, attempt: int, max_attempts: int, snippet: str = "", outcome: str | None = None) -> None`.
  - `NullStatusReporter` — no-op implementation; the default everywhere `status` is threaded through in later tasks.
  - `FileStatusReporter(path: Path, session_id: str)` — writes the current status as JSON via a temp-file-then-`os.replace` (atomic on both POSIX and Windows, unlike plain `os.rename`).
  - `FakeStatusReporter` — records every `report(...)` call (as a list of dicts) for test assertions, following the same "record calls" pattern used by nothing else yet in this codebase but matching the spirit of `FakeAgentBackend`/`FakeGateRunner` in `backends.py`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/orchestrator/test_status.py
import json

import pytest
from factory.orchestrator.status import FakeStatusReporter, FileStatusReporter, NullStatusReporter

pytestmark = pytest.mark.unit


def test_null_status_reporter_does_nothing():
    NullStatusReporter().report(
        task_id="T-001", node="dev", node_state="running", attempt=1, max_attempts=3
    )


def test_file_status_reporter_writes_json(tmp_path):
    path = tmp_path / "status.json"
    reporter = FileStatusReporter(path=path, session_id="s1")
    reporter.report(
        task_id="T-001",
        node="dev",
        node_state="running",
        attempt=2,
        max_attempts=3,
        snippet="working on it",
        outcome=None,
    )
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["session_id"] == "s1"
    assert record["task_id"] == "T-001"
    assert record["node"] == "dev"
    assert record["node_state"] == "running"
    assert record["attempt"] == 2
    assert record["max_attempts"] == 3
    assert record["snippet"] == "working on it"
    assert record["outcome"] is None
    assert "updated_at" in record


def test_file_status_reporter_overwrites_on_each_report(tmp_path):
    path = tmp_path / "status.json"
    reporter = FileStatusReporter(path=path, session_id="s1")
    reporter.report(task_id="T-001", node="context-gather", node_state="running", attempt=1, max_attempts=2)
    reporter.report(task_id="T-001", node="dev", node_state="pass", attempt=1, max_attempts=3)
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["node"] == "dev"
    assert record["node_state"] == "pass"


def test_file_status_reporter_leaves_no_tmp_file(tmp_path):
    path = tmp_path / "status.json"
    FileStatusReporter(path=path, session_id="s1").report(
        task_id="T-001", node="dev", node_state="running", attempt=1, max_attempts=3
    )
    assert not (tmp_path / "status.json.tmp").exists()


def test_file_status_reporter_creates_parent_dir(tmp_path):
    path = tmp_path / "nested" / "status.json"
    FileStatusReporter(path=path, session_id="s1").report(
        task_id="T-001", node="dev", node_state="running", attempt=1, max_attempts=3
    )
    assert path.exists()


def test_fake_status_reporter_records_calls():
    fake = FakeStatusReporter()
    fake.report(task_id="T-001", node="dev", node_state="running", attempt=1, max_attempts=3)
    fake.report(task_id="T-001", node="dev", node_state="pass", attempt=1, max_attempts=3, outcome="completed")
    assert [(c["node"], c["node_state"]) for c in fake.calls] == [("dev", "running"), ("dev", "pass")]
    assert fake.calls[-1]["outcome"] == "completed"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/orchestrator/test_status.py -v`
Expected: FAIL — `factory.orchestrator.status` module missing.

- [ ] **Step 3: Implement `status.py`**

```python
# src/factory/orchestrator/status.py
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class StatusReporter(Protocol):
    def report(
        self,
        *,
        task_id: str,
        node: str,
        node_state: str,
        attempt: int,
        max_attempts: int,
        snippet: str = "",
        outcome: str | None = None,
    ) -> None: ...


class NullStatusReporter:
    def report(
        self,
        *,
        task_id: str,
        node: str,
        node_state: str,
        attempt: int,
        max_attempts: int,
        snippet: str = "",
        outcome: str | None = None,
    ) -> None:
        pass


@dataclass
class FileStatusReporter:
    path: Path
    session_id: str
    started_at: str = field(default_factory=_now)

    def report(
        self,
        *,
        task_id: str,
        node: str,
        node_state: str,
        attempt: int,
        max_attempts: int,
        snippet: str = "",
        outcome: str | None = None,
    ) -> None:
        record = {
            "session_id": self.session_id,
            "task_id": task_id,
            "node": node,
            "node_state": node_state,
            "attempt": attempt,
            "max_attempts": max_attempts,
            "snippet": snippet,
            "outcome": outcome,
            "started_at": self.started_at,
            "updated_at": _now(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_name(self.path.name + ".tmp")
        tmp_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        os.replace(tmp_path, self.path)


class FakeStatusReporter:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def report(
        self,
        *,
        task_id: str,
        node: str,
        node_state: str,
        attempt: int,
        max_attempts: int,
        snippet: str = "",
        outcome: str | None = None,
    ) -> None:
        self.calls.append(
            {
                "task_id": task_id,
                "node": node,
                "node_state": node_state,
                "attempt": attempt,
                "max_attempts": max_attempts,
                "snippet": snippet,
                "outcome": outcome,
            }
        )
```

- [ ] **Step 4: Run to pass**

Run: `uv run pytest tests/unit/orchestrator/test_status.py -v` → 6 passed. Then `uv run ruff check . && uv run pyright`.

- [ ] **Step 5: Commit**

```bash
git add src/factory/orchestrator/status.py tests/unit/orchestrator/test_status.py
git commit -m "feat: file-based status reporter for live factory progress"
```

---

### Task 2: `AgentBackend` gains an `on_snippet` callback

**Files:**
- Modify: `src/factory/orchestrator/backends.py`
- Test: `tests/unit/orchestrator/test_backends.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `AgentBackend.run(role, prompt, on_snippet: Callable[[str], None] | None = None) -> AgentResult` — the Protocol and `FakeAgentBackend` both gain this optional parameter. `FakeAgentBackend` accepts and ignores it (fakes don't produce real streaming text). This is the prerequisite `PiAgentBackend` (Task 5) needs to actually call `on_snippet`, and that node executors (Task 3) need in order to pass a snippet-reporting closure without a `TypeError`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/orchestrator/test_backends.py
# ADD to the existing file (do not remove existing tests):

def test_fake_backend_accepts_and_ignores_on_snippet():
    b = FakeAgentBackend({AgentRole.DEV: [AgentResult(True, {"n": 1})]})
    seen: list[str] = []
    result = b.run(AgentRole.DEV, "p", on_snippet=seen.append)
    assert result.output["n"] == 1
    assert seen == []  # FakeAgentBackend never calls it -- no real streaming to report
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/orchestrator/test_backends.py -v`
Expected: FAIL — `TypeError: run() got an unexpected keyword argument 'on_snippet'`.

- [ ] **Step 3: Update `backends.py`**

```python
# src/factory/orchestrator/backends.py
from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from factory.orchestrator.types import AgentResult, AgentRole


class AgentBackend(Protocol):
    def run(
        self, role: AgentRole, prompt: str, on_snippet: Callable[[str], None] | None = None
    ) -> AgentResult: ...


class GateRunner(Protocol):
    def run(self, name: str) -> int: ...


class FakeAgentBackend:
    def __init__(self, scripts: dict[AgentRole, list[AgentResult]]) -> None:
        self._scripts = {k: list(v) for k, v in scripts.items()}

    def run(
        self, role: AgentRole, prompt: str, on_snippet: Callable[[str], None] | None = None
    ) -> AgentResult:
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

Only `AgentBackend` and `FakeAgentBackend` changed; `GateRunner`/`FakeGateRunner`/`SubprocessGateRunner` are shown for context and are byte-identical to before.

- [ ] **Step 4: Run to pass**

Run: `uv run pytest tests/unit/orchestrator/test_backends.py -v` → 4 passed (3 existing + 1 new). Then `uv run ruff check . && uv run pyright`.

- [ ] **Step 5: Commit**

```bash
git add src/factory/orchestrator/backends.py tests/unit/orchestrator/test_backends.py
git commit -m "feat: AgentBackend.run gains an optional on_snippet callback"
```

---

### Task 3: Node executors report progress

**Files:**
- Modify: `src/factory/orchestrator/nodes.py`
- Test: `tests/unit/orchestrator/test_nodes_context_dev.py`, `tests/unit/orchestrator/test_nodes_val_review.py`

**Interfaces:**
- Consumes: `StatusReporter`, `NullStatusReporter`, `FakeStatusReporter` (Task 1); `AgentBackend.run(..., on_snippet=...)` (Task 2).
- Produces: all four node executors gain an optional `status: StatusReporter = NullStatusReporter()` keyword parameter. Each reports `node_state="running"` at the start of every attempt (with a live-snippet callback wired into the `backend.run(...)` call); callers (Task 4) additionally report the definitive outcome after each executor returns, so this task's own reports only ever carry `node_state="running"` and `outcome=None`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/orchestrator/test_nodes_context_dev.py
# ADD to the existing file (do not remove existing tests); add this import
# alongside the existing ones at the top of the file:
# from factory.orchestrator.status import FakeStatusReporter


def test_context_gatherer_reports_running_each_attempt(tmp_path):
    status = FakeStatusReporter()
    b = FakeAgentBackend({AgentRole.CONTEXT_GATHERER: [AgentResult(True, _manifest(tmp_path))]})
    run_context_gatherer(b, _task(), tmp_path, status=status)
    assert status.calls[0]["node"] == "context-gather"
    assert status.calls[0]["node_state"] == "running"
    assert status.calls[0]["attempt"] == 1
    assert status.calls[0]["max_attempts"] == 2


def test_dev_reports_running_each_attempt_and_passes_on_snippet():
    status = FakeStatusReporter()

    class SnippetCapturingBackend:
        def run(self, role, prompt, on_snippet=None):
            if on_snippet is not None:
                on_snippet("partial output")
            return AgentResult(True, {})

    b = SnippetCapturingBackend()
    g = FakeGateRunner({"unit": [0]})
    run_dev(b, g, _task(), {}, [], status=status)
    assert status.calls[0]["node"] == "dev"
    assert status.calls[0]["node_state"] == "running"
    # A second report should have arrived carrying the live snippet.
    snippets = [c["snippet"] for c in status.calls if c["snippet"]]
    assert snippets == ["partial output"]
```

```python
# tests/unit/orchestrator/test_nodes_val_review.py
# ADD to the existing file (do not remove existing tests); add this import
# alongside the existing ones at the top of the file:
# from factory.orchestrator.status import FakeStatusReporter


def test_validation_reports_running():
    status = FakeStatusReporter()
    run_validation(FakeGateRunner({"sim": [0]}), "T-001", status=status)
    assert status.calls[0]["node"] == "validation"
    assert status.calls[0]["node_state"] == "running"
    assert status.calls[0]["task_id"] == "T-001"


def test_review_reports_running():
    status = FakeStatusReporter()
    b = FakeAgentBackend({AgentRole.REVIEW: [AgentResult(True, {"dod_met": True, "findings": []})]})
    run_review(b, FakeGateRunner({"full": [0]}), _task(), status=status)
    assert status.calls[0]["node"] == "review"
    assert status.calls[0]["node_state"] == "running"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/orchestrator/test_nodes_context_dev.py tests/unit/orchestrator/test_nodes_val_review.py -v`
Expected: FAIL — `TypeError: run_context_gatherer() got an unexpected keyword argument 'status'` (and similarly for the other three).

- [ ] **Step 3: Update `nodes.py`**

```python
# src/factory/orchestrator/nodes.py
from __future__ import annotations

from pathlib import Path

from factory.orchestrator.backends import AgentBackend, GateRunner
from factory.orchestrator.ledger import Task
from factory.orchestrator.prompts import compose_prompt
from factory.orchestrator.status import NullStatusReporter, StatusReporter
from factory.orchestrator.types import AgentResult, AgentRole, NodeEvent, NodeOutcome
from factory.validation.manifest_validator import validate_manifest


def _note_backend_failure(extra: dict, result: AgentResult) -> dict:
    """Finding 1+2 (final review): surface `result.ok is False` as a distinct
    diagnostic signal in NodeEvent.extra, separate from a legitimately bad/empty
    agent output, without changing retry/circuit-breaker control flow or outcomes.
    """
    if not result.ok:
        extra["backend_ok"] = False
        extra["backend_raw"] = result.raw
    return extra


def run_context_gatherer(
    backend: AgentBackend,
    task: Task,
    repo_root: Path,
    max_attempts: int = 2,
    status: StatusReporter = NullStatusReporter(),
) -> tuple[NodeOutcome, dict | None, NodeEvent]:
    errors: list[str] = []
    result: AgentResult | None = None
    for attempt in range(1, max_attempts + 1):
        status.report(
            task_id=task.id, node="context-gather", node_state="running",
            attempt=attempt, max_attempts=max_attempts,
        )

        def _on_snippet(text: str) -> None:
            status.report(
                task_id=task.id, node="context-gather", node_state="running",
                attempt=attempt, max_attempts=max_attempts, snippet=text,
            )

        result = backend.run(
            AgentRole.CONTEXT_GATHERER, compose_prompt(AgentRole.CONTEXT_GATHERER, task),
            on_snippet=_on_snippet,
        )
        manifest = result.output
        if manifest.get("reject"):
            extra = _note_backend_failure({"reason": manifest["reject"]}, result)
            return NodeOutcome.REJECT, None, NodeEvent("context-gather", "reject", attempt, extra)
        errors = validate_manifest(manifest, repo_root)
        if not errors and manifest.get("coherence", {}).get("proven"):
            extra = _note_backend_failure({}, result)
            return NodeOutcome.PASS, manifest, NodeEvent("context-gather", "pass", attempt, extra)
    extra = {"errors": errors}
    if result is not None:
        extra = _note_backend_failure(extra, result)
    return NodeOutcome.REJECT, None, NodeEvent("context-gather", "reject", max_attempts, extra)


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
    result: AgentResult | None = None
    for attempt in range(1, max_iters + 1):
        status.report(
            task_id=task.id, node="dev", node_state="running",
            attempt=attempt, max_attempts=max_iters,
        )

        def _on_snippet(text: str) -> None:
            status.report(
                task_id=task.id, node="dev", node_state="running",
                attempt=attempt, max_attempts=max_iters, snippet=text,
            )

        result = backend.run(
            AgentRole.DEV, compose_prompt(AgentRole.DEV, task, manifest, kb_entries, feedback),
            on_snippet=_on_snippet,
        )
        if gates.run("unit") == 0:
            extra = _note_backend_failure({"tests": "green"}, result)
            return NodeOutcome.PASS, NodeEvent("dev", "pass", attempt, extra)
    extra = {"reason": "unit tests red"}
    if result is not None:
        extra = _note_backend_failure(extra, result)
    return NodeOutcome.ESCALATE, NodeEvent("dev", "escalate", max_iters, extra)


def run_validation(
    gates: GateRunner, task_id: str = "", status: StatusReporter = NullStatusReporter()
) -> tuple[NodeOutcome, NodeEvent]:
    status.report(task_id=task_id, node="validation", node_state="running", attempt=1, max_attempts=1)
    if gates.run("sim") == 0:
        return NodeOutcome.PASS, NodeEvent("validation", "pass")
    return NodeOutcome.FAIL, NodeEvent("validation", "fail")


def run_review(
    backend: AgentBackend,
    gates: GateRunner,
    task: Task,
    status: StatusReporter = NullStatusReporter(),
) -> tuple[NodeOutcome, NodeEvent, list[str]]:
    status.report(task_id=task.id, node="review", node_state="running", attempt=1, max_attempts=1)

    def _on_snippet(text: str) -> None:
        status.report(
            task_id=task.id, node="review", node_state="running",
            attempt=1, max_attempts=1, snippet=text,
        )

    result = backend.run(AgentRole.REVIEW, compose_prompt(AgentRole.REVIEW, task), on_snippet=_on_snippet)
    out = result.output
    findings = list(out.get("findings", []))
    dod_met = bool(out.get("dod_met"))
    gate = gates.run("full")
    if gate == 0 and dod_met and not findings:
        extra = _note_backend_failure({}, result)
        return NodeOutcome.PASS, NodeEvent("review", "pass", 1, extra), []
    extra = _note_backend_failure({"findings": len(findings), "gate": gate}, result)
    return (
        NodeOutcome.CHANGES,
        NodeEvent("review", "changes-requested", 1, extra),
        findings,
    )
```

- [ ] **Step 4: Run to pass**

Run: `uv run pytest tests/unit/orchestrator/test_nodes_context_dev.py tests/unit/orchestrator/test_nodes_val_review.py -v`
Expected: 8 passed (4 existing in each file + 2 new in each file = 12 total; verify the exact count against your checkout — the point is every previously-passing test still passes and every new one goes green). Then `uv run ruff check . && uv run pyright`.

- [ ] **Step 5: Commit**

```bash
git add src/factory/orchestrator/nodes.py tests/unit/orchestrator/test_nodes_context_dev.py tests/unit/orchestrator/test_nodes_val_review.py
git commit -m "feat: node executors report live progress via StatusReporter"
```

---

### Task 4: `run_task`/`run_next` report node outcomes and final task outcome

**Files:**
- Modify: `src/factory/orchestrator/runner.py`
- Test: `tests/unit/orchestrator/test_runner_e2e.py`, `tests/unit/orchestrator/test_run_next.py`

**Interfaces:**
- Consumes: `StatusReporter`, `NullStatusReporter` (Task 1); node executors now accepting `status=` (Task 3).
- Produces: `run_task(..., status: StatusReporter = NullStatusReporter())` and `run_next(..., status: StatusReporter = NullStatusReporter())` — both thread `status` down to every node call, and `run_task` additionally reports the definitive outcome of each node right after it returns (`node_state` = that node's actual result, not "running"), plus one final report carrying the overall task `outcome` (`"completed" | "rejected" | "escalated"`) at each of its four return points.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/orchestrator/test_runner_e2e.py
# ADD to the existing file (do not remove existing tests); add this import
# alongside the existing ones at the top of the file:
# from factory.orchestrator.status import FakeStatusReporter


def test_run_task_reports_final_outcome(tmp_path):
    repo = _repo(tmp_path)
    task = Task("T-001", "t", "todo", ["c"], "body", repo / "tasks" / "T-001.md")
    status = FakeStatusReporter()

    run_task(task, FakeAgentBackend(_scripts()), FakeGateRunner(), repo, status=status)

    final_calls = [c for c in status.calls if c["outcome"] is not None]
    assert len(final_calls) == 1
    assert final_calls[0]["outcome"] == "completed"


def test_run_task_reports_node_result_after_each_node(tmp_path):
    repo = _repo(tmp_path)
    task = Task("T-001", "t", "todo", ["c"], "body", repo / "tasks" / "T-001.md")
    status = FakeStatusReporter()

    run_task(task, FakeAgentBackend(_scripts()), FakeGateRunner(), repo, status=status)

    node_states = [(c["node"], c["node_state"]) for c in status.calls]
    # "pass" for context-gather should appear (not just "running"), proving
    # run_task reports the definitive result after the node returns.
    assert ("context-gather", "pass") in node_states
    assert ("review", "pass") in node_states
```

```python
# tests/unit/orchestrator/test_run_next.py
# ADD to the existing file (do not remove existing tests); add this import
# alongside the existing ones at the top of the file:
# from factory.orchestrator.status import FakeStatusReporter


def test_run_next_passes_status_through_to_run_task(tmp_path):
    repo = _repo(tmp_path)
    status = FakeStatusReporter()
    run_next(repo, FakeAgentBackend(_scripts()), FakeGateRunner(),
              session_id="s1", git_info={"branch": "main"}, status=status)
    assert len(status.calls) > 0
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/orchestrator/test_runner_e2e.py tests/unit/orchestrator/test_run_next.py -v`
Expected: FAIL — `TypeError: run_task() got an unexpected keyword argument 'status'` (and similarly for `run_next`).

- [ ] **Step 3: Update `runner.py`**

```python
# src/factory/orchestrator/runner.py
from __future__ import annotations

from pathlib import Path

from factory.kb.retrieval import select_entries
from factory.orchestrator.backends import AgentBackend, GateRunner
from factory.orchestrator.ledger import Task, load_tasks, next_todo, set_status
from factory.orchestrator.nodes import (
    run_context_gatherer,
    run_dev,
    run_review,
    run_validation,
)
from factory.orchestrator.session import build_record, write_session
from factory.orchestrator.status import NullStatusReporter, StatusReporter
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


def _report_node(
    status: StatusReporter, task_id: str, ev: NodeEvent, max_attempts: int, outcome: str | None = None
) -> None:
    status.report(
        task_id=task_id, node=ev.node, node_state=ev.result,
        attempt=ev.attempts, max_attempts=max_attempts, outcome=outcome,
    )


def run_task(
    task: Task,
    backend: AgentBackend,
    gates: GateRunner,
    repo_root: Path,
    *,
    max_dev_iters: int = 3,
    max_review_cycles: int = 3,
    status: StatusReporter = NullStatusReporter(),
) -> TaskResult:
    events: list[NodeEvent] = []

    c_outcome, manifest, c_ev = run_context_gatherer(backend, task, repo_root, status=status)
    events.append(c_ev)
    if c_outcome == NodeOutcome.REJECT or manifest is None:
        _report_node(status, task.id, c_ev, c_ev.attempts, outcome="rejected")
        return TaskResult(task.id, task.title, "rejected", 1, events, False, None)
    _report_node(status, task.id, c_ev, c_ev.attempts)

    kb_ids = select_entries(repo_root / "kb", manifest["context"].get("source_files", []), [])
    kb_entries = _load_kb_entries(repo_root / "kb", kb_ids)

    feedback: str | None = None
    iterations = 0
    for _ in range(max_review_cycles):
        iterations += 1

        d_outcome, d_ev = run_dev(
            backend, gates, task, manifest, kb_entries, max_dev_iters, feedback, status=status
        )
        events.append(d_ev)
        if d_outcome == NodeOutcome.ESCALATE:
            _report_node(status, task.id, d_ev, max_dev_iters, outcome="escalated")
            return TaskResult(task.id, task.title, "escalated", iterations, events, False, manifest)
        _report_node(status, task.id, d_ev, max_dev_iters)

        v_outcome, v_ev = run_validation(gates, task.id, status=status)
        events.append(v_ev)
        _report_node(status, task.id, v_ev, 1)
        if v_outcome == NodeOutcome.FAIL:
            feedback = "functional/sim tests failed"
            continue

        r_outcome, r_ev, findings = run_review(backend, gates, task, status=status)
        events.append(r_ev)
        if r_outcome == NodeOutcome.PASS:
            _report_node(status, task.id, r_ev, 1, outcome="completed")
            return TaskResult(task.id, task.title, "completed", iterations, events, True, manifest)
        _report_node(status, task.id, r_ev, 1)
        feedback = "\n".join(findings) if findings else "review requested changes"

    status.report(
        task_id=task.id, node="review", node_state="changes-requested",
        attempt=iterations, max_attempts=max_review_cycles, outcome="escalated",
    )
    return TaskResult(task.id, task.title, "escalated", iterations, events, False, manifest)


def run_next(
    repo_root: Path,
    backend: AgentBackend,
    gates: GateRunner,
    *,
    # Finding 3 (final review): PiAgentBackend never passes --model to the real
    # `pi` CLI (it runs on Pi's own ambient/default model selection), so naming a
    # specific model here would be a false claim baked into the session record.
    # "pi:unspecified" honestly reflects "ran via Pi's own model selection, not
    # explicitly chosen by the orchestrator" instead of a model that was never
    # actually selected.
    model_backend: str = "pi:unspecified",
    session_id: str | None = None,
    git_info: dict | None = None,
    status: StatusReporter = NullStatusReporter(),
) -> Path | None:
    tasks = load_tasks(repo_root / "tasks")
    task = next_todo(tasks)
    if task is None:
        return None

    result = run_task(task, backend, gates, repo_root, status=status)
    set_status(task, "done" if result.outcome == "completed" else result.outcome)

    sid = session_id or _default_session_id()
    record = build_record(sid, model_backend, [result], git_info or {})
    return write_session(repo_root / "sessions", record)


def _default_session_id() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
```

- [ ] **Step 4: Run to pass**

Run: `uv run pytest tests/unit/orchestrator/test_runner_e2e.py tests/unit/orchestrator/test_run_next.py -v`
Expected: all pass (5 existing + 2 new in `test_runner_e2e.py`; 2 existing + 1 new in `test_run_next.py`). Then `uv run ruff check . && uv run pyright`.

- [ ] **Step 5: Commit**

```bash
git add src/factory/orchestrator/runner.py tests/unit/orchestrator/test_runner_e2e.py tests/unit/orchestrator/test_run_next.py
git commit -m "feat: run_task/run_next report node outcomes and final task outcome"
```

---

### Task 5: `PiAgentBackend` streams output and reports a live snippet

**Files:**
- Modify: `src/factory/orchestrator/pi_backend.py`
- Test: `tests/unit/orchestrator/test_pi_parse.py`

**Interfaces:**
- Consumes: `AgentBackend.run(..., on_snippet=...)` (Task 2).
- Produces: `PiAgentBackend.run` switches from blocking `subprocess.run` to `Popen` + incremental line-by-line stdout read, calling `on_snippet(text[-200:])` for each line that carries a `"text"` field, while still handing the fully-accumulated stdout to the untouched `parse_pi_json`/`_has_json_events_without_text_field` at the end. New pure helper: `_extract_snippet(line: str) -> str`. stderr is merged into the same stream (`stderr=subprocess.STDOUT`) rather than captured on a second, undrained pipe — draining only stdout while a real child process writes enough to stderr to fill its OS pipe buffer (commonly ~64KB) can deadlock the whole call; merging avoids that risk entirely and, as a side benefit, means crash diagnostics that used to go to a discarded `proc.stderr` now show up in `raw` for debugging.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/orchestrator/test_pi_parse.py
# ADD to the existing file (do not remove existing tests); add this import:
# from factory.orchestrator.pi_backend import _extract_snippet


def test_extract_snippet_returns_text_field():
    line = '{"type": "assistant_text", "text": "hello"}'
    assert _extract_snippet(line) == "hello"


def test_extract_snippet_empty_for_non_text_event():
    line = '{"type": "tool_call", "name": "read_file"}'
    assert _extract_snippet(line) == ""


def test_extract_snippet_empty_for_malformed_json():
    assert _extract_snippet("not json at all") == ""


def test_extract_snippet_empty_for_blank_line():
    assert _extract_snippet("   ") == ""
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/orchestrator/test_pi_parse.py -v`
Expected: FAIL — `ImportError: cannot import name '_extract_snippet'`.

- [ ] **Step 3: Update `pi_backend.py`**

```python
# src/factory/orchestrator/pi_backend.py
from __future__ import annotations

import json
import os
import re
import subprocess
from collections.abc import Callable
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


def _extract_snippet(line: str) -> str:
    """Extract the "text" field from a single line of Pi's json event stream,
    for live-snippet reporting as output streams in. Returns "" if the line
    isn't a JSON object with a string "text" field. Kept separate from
    parse_pi_json (which still processes the full accumulated stdout at the
    end, unchanged) so that function's tested behavior stays untouched."""
    line = line.strip()
    if not line:
        return ""
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return ""
    if isinstance(event, dict) and isinstance(event.get("text"), str):
        return event["text"]
    return ""


def _has_json_events_without_text_field(stdout: str) -> bool:
    """Best-effort detector for final-review Finding 1+2: the event stream contains
    valid JSON objects, but none of them carry a string "text" field the way
    parse_pi_json expects. That's a strong signal that a JSON field-name assumption
    (e.g. Pi renamed/never used "text" in this event shape) is wrong, rather than
    the agent having genuinely said nothing.

    Kept separate from parse_pi_json (not folded into it) so parse_pi_json's tested
    signature and behavior stay untouched, per the finding.

    Limits: this is a heuristic over line-delimited JSON, not a full understanding
    of Pi's event protocol. A stream that mixes text-bearing and non-text events in
    some other unexpected way, or non-JSON/binary stdout, is not guaranteed to be
    classified correctly — see the finding's "When You're in Over Your Head" note.
    """
    saw_json_object = False
    saw_text_field = False
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            saw_json_object = True
            if isinstance(event.get("text"), str):
                saw_text_field = True
    return saw_json_object and not saw_text_field


def _build_command(
    prompt: str,
    extension_path: Path,
    provider: str | None,
    model: str | None,
) -> list[str]:
    """Build the `pi` invocation. Pi defaults to the "google" provider when
    --provider/--model are omitted, so an explicit provider/model must be
    passed through to use anything else (e.g. openrouter)."""
    cmd = ["pi", "-p", prompt, "--mode", "json", "--extension", str(extension_path)]
    if provider:
        cmd += ["--provider", provider]
    if model:
        cmd += ["--model", model]
    return cmd


class PiAgentBackend:
    def __init__(
        self,
        repo_root: Path,
        extension_path: Path,
        provider: str | None = None,
        model: str | None = None,
    ) -> None:
        self._repo_root = repo_root
        self._extension_path = extension_path
        self._provider = provider
        self._model = model

    def run(
        self, role: AgentRole, prompt: str, on_snippet: Callable[[str], None] | None = None
    ) -> AgentResult:
        scope = ROLE_SCOPE[role]
        env = {
            **os.environ,
            "PI_SCOPE_ALLOW": ",".join(scope.allow),
            "PI_SCOPE_BASH": scope.bash,
        }
        cmd = _build_command(prompt, self._extension_path, self._provider, self._model)
        proc = subprocess.Popen(
            cmd, cwd=self._repo_root, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        lines: list[str] = []
        assert proc.stdout is not None
        for line in proc.stdout:
            lines.append(line)
            if on_snippet is not None:
                snippet = _extract_snippet(line)
                if snippet:
                    on_snippet(snippet[-200:])
        proc.wait()
        stdout = "".join(lines)

        output = parse_pi_json(stdout)
        ok = proc.returncode == 0
        raw = stdout

        # Finding 1+2 (final review): a zero exit code with non-empty stdout that
        # yields an empty parsed output is normally read as "the agent said
        # nothing". If the stdout actually contains valid JSON events that just
        # never carry a "text" field, that reading is wrong — parse_pi_json's
        # field-name assumption doesn't match this event stream. Force ok=False
        # and attach a distinct, diagnosable raw message instead of silently
        # looking identical to a genuinely empty response.
        if (
            ok
            and stdout.strip()
            and not output
            and _has_json_events_without_text_field(stdout)
        ):
            ok = False
            raw = (
                "pi_backend: possible field-name mismatch — subprocess exited 0 with "
                "non-empty stdout containing valid JSON events, but none had a string "
                '"text" field, so parse_pi_json extracted no output. This looks like an '
                "empty agent response but is more likely parse_pi_json's event-shape "
                "assumption being wrong for this stream. Raw stdout:\n" + stdout
            )

        return AgentResult(ok=ok, output=output, raw=raw)
```

- [ ] **Step 4: Run to pass**

Run: `uv run pytest tests/unit/orchestrator/test_pi_parse.py -v` → all pass (9 existing + 4 new = check your actual count). Then `uv run ruff check . && uv run pyright`.

- [ ] **Step 5: Commit**

```bash
git add src/factory/orchestrator/pi_backend.py tests/unit/orchestrator/test_pi_parse.py
git commit -m "feat: PiAgentBackend streams output for a live status snippet"
```

---

### Task 6: PID lock file + CLI wiring

**Files:**
- Create: `src/factory/orchestrator/lock.py`
- Modify: `src/factory/orchestrator/__main__.py`
- Test: `tests/unit/orchestrator/test_lock.py`

**Interfaces:**
- Consumes: `FileStatusReporter` (Task 1); `run_next(..., status=...)` (Task 4).
- Produces:
  - `lock.py`: `LockInfo(pid: int, started_at: str)`, `read_lock(path) -> LockInfo | None`, `write_lock(path, pid, started_at) -> None`, `remove_lock(path) -> None`, `is_pid_alive(pid: int) -> bool` (cross-platform: `tasklist` on `win32`, `os.kill(pid, 0)` on POSIX), `AlreadyRunningError(RuntimeError)`, `acquire_lock(path, pid, started_at) -> None` (raises `AlreadyRunningError` if a live lock already exists, otherwise writes a fresh one — a stale lock from a dead process is silently overwritten).
  - `__main__.py`: acquires the lock before running, always removes it in a `finally`, refuses to start a second concurrent run, writes a `node_state: "error"` status on any uncaught exception from `run_next` before re-raising, and constructs a `FileStatusReporter` pointed at `sessions/.factory-status.json` using the same `session_id` passed to `run_next` (so the status file and the eventual session record always agree on session id).

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/orchestrator/test_lock.py
import os

import pytest
from factory.orchestrator.lock import (
    AlreadyRunningError,
    acquire_lock,
    is_pid_alive,
    read_lock,
    remove_lock,
    write_lock,
)

pytestmark = pytest.mark.unit


def test_is_pid_alive_true_for_self():
    assert is_pid_alive(os.getpid()) is True


def test_is_pid_alive_false_for_unlikely_pid():
    assert is_pid_alive(999_999_999) is False


def test_write_and_read_lock_round_trip(tmp_path):
    path = tmp_path / "run.lock"
    write_lock(path, pid=12345, started_at="2026-07-20T10:00:00Z")
    info = read_lock(path)
    assert info is not None
    assert info.pid == 12345
    assert info.started_at == "2026-07-20T10:00:00Z"


def test_read_lock_none_when_missing(tmp_path):
    assert read_lock(tmp_path / "missing.lock") is None


def test_remove_lock_is_idempotent(tmp_path):
    path = tmp_path / "run.lock"
    write_lock(path, pid=1, started_at="x")
    remove_lock(path)
    assert not path.exists()
    remove_lock(path)  # must not raise on a second call


def test_acquire_lock_succeeds_when_no_existing_lock(tmp_path):
    path = tmp_path / "run.lock"
    acquire_lock(path, pid=os.getpid(), started_at="2026-07-20T10:00:00Z")
    assert read_lock(path).pid == os.getpid()


def test_acquire_lock_raises_when_live_process_holds_it(tmp_path):
    path = tmp_path / "run.lock"
    write_lock(path, pid=os.getpid(), started_at="2026-07-20T10:00:00Z")
    with pytest.raises(AlreadyRunningError):
        acquire_lock(path, pid=os.getpid() + 1, started_at="2026-07-20T10:05:00Z")


def test_acquire_lock_overwrites_stale_lock(tmp_path):
    path = tmp_path / "run.lock"
    write_lock(path, pid=999_999_999, started_at="2026-07-20T09:00:00Z")
    acquire_lock(path, pid=os.getpid(), started_at="2026-07-20T10:00:00Z")
    assert read_lock(path).pid == os.getpid()
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/orchestrator/test_lock.py -v`
Expected: FAIL — `factory.orchestrator.lock` module missing.

- [ ] **Step 3: Implement `lock.py`**

```python
# src/factory/orchestrator/lock.py
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class LockInfo:
    pid: int
    started_at: str


class AlreadyRunningError(RuntimeError):
    def __init__(self, pid: int) -> None:
        super().__init__(f"factory orchestrator already running (pid {pid})")
        self.pid = pid


def read_lock(path: Path) -> LockInfo | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return LockInfo(pid=int(data["pid"]), started_at=str(data["started_at"]))
    except (json.JSONDecodeError, KeyError, ValueError):
        return None


def write_lock(path: Path, pid: int, started_at: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"pid": pid, "started_at": started_at}), encoding="utf-8")


def remove_lock(path: Path) -> None:
    path.unlink(missing_ok=True)


def is_pid_alive(pid: int) -> bool:
    """Cross-platform liveness check using only the stdlib. POSIX uses the
    standard os.kill(pid, 0) idiom; Windows doesn't support that (os.kill
    there only understands CTRL_C_EVENT/CTRL_BREAK_EVENT), so this shells
    out to `tasklist` there instead -- matching this codebase's existing
    win32/posix branching pattern (e.g. scripts/gates/ext.py's npm.cmd)."""
    if sys.platform == "win32":
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True
        )
        return str(pid) in result.stdout
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, just not owned by us
    return True


def acquire_lock(path: Path, pid: int, started_at: str) -> None:
    """Raise AlreadyRunningError if a live lock already exists; otherwise
    (no lock, or a stale lock left by a dead process) write a fresh lock."""
    existing = read_lock(path)
    if existing is not None and is_pid_alive(existing.pid):
        raise AlreadyRunningError(existing.pid)
    write_lock(path, pid, started_at)
```

- [ ] **Step 4: Run to pass**

Run: `uv run pytest tests/unit/orchestrator/test_lock.py -v` → 8 passed. Then `uv run ruff check . && uv run pyright`.

- [ ] **Step 5: Update `__main__.py`**

```python
# src/factory/orchestrator/__main__.py
from __future__ import annotations

import argparse
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from factory.orchestrator.backends import SubprocessGateRunner
from factory.orchestrator.lock import AlreadyRunningError, acquire_lock, remove_lock
from factory.orchestrator.pi_backend import PiAgentBackend
from factory.orchestrator.runner import run_next
from factory.orchestrator.status import FileStatusReporter


def _git_info(repo_root: Path) -> dict:
    def _cmd(args: list[str]) -> str:
        return subprocess.run(["git", *args], cwd=repo_root, capture_output=True, text=True).stdout.strip()

    return {"branch": _cmd(["rev-parse", "--abbrev-ref", "HEAD"]), "head": _cmd(["rev-parse", "HEAD"])}


def _now_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def main() -> None:
    parser = argparse.ArgumentParser(prog="factory.orchestrator")
    parser.add_argument("command", choices=["run"])
    parser.add_argument("--repo", default=".")
    parser.add_argument("--provider", default=None, help="Pi provider, e.g. openrouter")
    parser.add_argument("--model", default=None, help="Pi model id, e.g. anthropic/claude-opus-4")
    args = parser.parse_args()

    repo_root = Path(args.repo).resolve()
    ext = repo_root / "pi-ext" / "scope-guard" / "src" / "index.ts"
    backend = PiAgentBackend(
        repo_root=repo_root, extension_path=ext, provider=args.provider, model=args.model
    )
    gates = SubprocessGateRunner(repo_root)

    kwargs = {}
    if args.provider and args.model:
        kwargs["model_backend"] = f"{args.provider}:{args.model}"

    session_id = _now_id()
    lock_path = repo_root / "sessions" / ".factory-run.lock"
    status_path = repo_root / "sessions" / ".factory-status.json"

    try:
        acquire_lock(lock_path, os.getpid(), session_id)
    except AlreadyRunningError as exc:
        print(f"factory orchestrator already running (pid {exc.pid}); refusing to start a second run")
        raise SystemExit(1) from exc

    status = FileStatusReporter(path=status_path, session_id=session_id)
    try:
        path = run_next(
            repo_root, backend, gates, git_info=_git_info(repo_root),
            session_id=session_id, status=status, **kwargs,
        )
        print("no todo tasks" if path is None else f"session written: {path}")
    except Exception as exc:
        status.report(
            task_id="", node="orchestrator", node_state="error",
            attempt=0, max_attempts=0, snippet=str(exc),
        )
        raise
    finally:
        remove_lock(lock_path)


if __name__ == "__main__":
    main()
```

There is no dedicated test file for `__main__.py` (consistent with the rest of this plan — it stays thin CLI wiring; all the logic worth testing was extracted into `lock.py` and `status.py`, both already covered).

- [ ] **Step 6: Manual smoke check**

Run: `uv run python -m factory.orchestrator run --repo .` against a repo with no `todo` tasks (e.g. temporarily edit `tasks/T-001-example.md`'s `status` to something other than `todo`, or point `--repo` at an empty scratch directory with a `tasks/` folder). Confirm:
- `sessions/.factory-run.lock` is created during the run and removed afterward.
- `sessions/.factory-status.json` exists and its `node`/`node_state` reflect real progress if you do run it against a real todo task.
- Exit code is 0 and prints `no todo tasks` (or `session written: ...`).

- [ ] **Step 7: Commit**

```bash
git add src/factory/orchestrator/lock.py src/factory/orchestrator/__main__.py tests/unit/orchestrator/test_lock.py
git commit -m "feat: PID lock file and status-reporter wiring in the CLI entrypoint"
```

---

## Self-Review

**Spec coverage** (against `docs/superpowers/specs/2026-07-20-factory-live-visualization-design.md`):
- §3.1 `StatusReporter`/`FileStatusReporter`/`NullStatusReporter` → Task 1 (plus `FakeStatusReporter`, needed by every later task's tests).
- §3.2 `PiAgentBackend` streaming → Task 5.
- §3.3 PID lock file → Task 6 (`lock.py`).
- §4 cancellation groundwork (the orchestrator's own crash/error status) → Task 6 (`except Exception` block in `__main__.py`).
- §5 error handling (stale lock, crash-to-error-status, concurrent-run refusal) → Task 6.
- §6 no schema validation for the status file → honored throughout; nowhere does this plan add one.
- §7 testing strategy (Fake-injection pattern, pure extracted functions, no subprocess mocking) → every task follows this exactly.
- The `/factory`/`/factory-stop` extension itself, and the graceful-then-forceful kill mechanics, are Plan B's job (a separate `pi-ext/factory-watch/` plan), not this one.

**Placeholder scan:** none. Every step ships exact, complete code and exact commands with expected output.

**Type consistency:** `StatusReporter.report(...)`'s keyword signature is identical everywhere it's called (Tasks 1, 3, 4, 6). `AgentBackend.run(role, prompt, on_snippet=...)` (Task 2) matches every call site (Task 3's node executors, Task 5's `PiAgentBackend`, and `FakeAgentBackend`). `run_task`/`run_next`'s new `status` parameter (Task 4) matches how Task 6's `__main__.py` calls `run_next`. `lock.py`'s `LockInfo`/`acquire_lock`/`is_pid_alive` (Task 6) are used consistently by `__main__.py` with no signature drift.

**Known, deliberately deferred risk:** `is_pid_alive`'s Windows branch shells out to `tasklist` per call — fine for the infrequent "is a run already going" check this plan uses it for, not something to poll in a tight loop. Plan B's `/factory-stop` will need its own (Node-side) process-liveness/termination logic; it should not assume this Python helper is reachable from TypeScript and will need an equivalent implementation there, noted explicitly in Plan B.
