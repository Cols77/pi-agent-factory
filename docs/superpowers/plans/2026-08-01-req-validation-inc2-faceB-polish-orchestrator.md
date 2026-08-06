# Increment 2 — Face B: Deterministic Polish Orchestrator (core) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-architect the polish workflow from a skill-owned conversational loop into a deterministic Python orchestrator (factory-run philosophy): Python owns the topology and state transitions; the LLM is invoked only as one bounded `SYNTHESIS` role; a background serial worker has factory-run fix the resulting tickets **in an isolated worktree and fast-forwards each green result into the live branch** while the human keeps play-testing, gated by a lightweight pre-queue glance (Gate 1) and a post-fix acceptance checklist (Gate 2).

**Architecture:** A `PolishOrchestrator` holds all state and exposes deterministic transition methods (`submit_feedback`, `accept_finding`/`edit_finding`/`discard_finding`, `tick`/`comment`) plus a `state()` snapshot. Feedback → `synthesize()` (the one LLM call, via the injected `AgentBackend`) → **Gate 1** pending findings. Accepted findings enter a `FixWorker` queue; the worker runs on a background thread, draining serially and delegating each finding to a `FixExecutor`. The `WorktreeIsolatedExecutor` creates a throwaway git worktree at live HEAD, `route()`s the finding to a `T-###` task there, runs factory-run (`python -m factory.orchestrator run --task T-### --auto`) **inside that worktree**, and — only on green — fast-forwards the finished commit(s) into the live branch the dev-server watches (so the live tree never sees a mid-fix edit; a failed fix touches it not at all). `--auto` is the auto-approve mode (LLM review + validation are the acceptance; no human diff-gate). Each drained item becomes a **Gate 2** landed-change row: `tick` accepts (re-grounds the SR if linked); `comment` spawns a new linked finding, re-queued. The external calls — the LLM, the factory-run subprocess, and the git worktree ops — are **injected/faked** so the state machine is unit-tested headlessly (`WorktreeIsolatedExecutor` gets an integration test against a real temp repo). The factory-watch UI (Plan B2) is a pure consumer of `state()` + the transition methods; this plan defines that contract but builds no UI.

**Tech Stack:** Python 3.12, `pytest`, `ruff`, `pyright`, stdlib `queue`/`threading`. Reuses `factory.polish.{finding,routing,playground}`, `factory.orchestrator.{backends,types}`.

## Global Constraints

- Reuse verbatim, do NOT redefine: `Finding(usecase, description, snapshot:dict, sr:str|None, artifacts:list[str])` (`factory.polish.finding`); `route(finding, tasks_dir) -> Path` (`factory.polish.routing`); `Playground`/`PlaygroundSession` (`factory.polish.playground`); `AgentBackend.run(role, prompt, on_snippet=None, on_session_id=None) -> AgentResult`, `AgentRole`, `AgentResult(ok:bool, output:dict, raw:str, session_id)` (`factory.orchestrator.{backends,types}`); `FakeAgentBackend(scripts: dict[AgentRole, list[AgentResult]])`.
- The orchestrator NEVER blocks the feedback path on a running fix. Fixes run on a background thread; capture/synthesis/gates stay responsive.
- Only ONE LLM call in the whole flow: the `SYNTHESIS` role. Every other transition is deterministic Python.
- factory-run is invoked as a subprocess in **`--auto` mode** for polish tickets (no human review gate). Never pass a `HumanReviewGate` for polish-originated tasks.
- **Fixes are isolated, never run on the live tree.** factory-run runs in a throwaway git worktree; only the green, committed result is fast-forwarded into the live branch the dev-server watches. The live working tree only ever transitions between committed, validated states — never a mid-fix edit. (This also honors the standing "never work in the live checkout" rule.)
- Preserve the trust rule: the executor routes findings into the worktree's `tasks/` and lets factory-run implement; the orchestrator never edits `requirements/**` or app code itself.
- Repo: `C:/coding/pi-agent-factory` (isolated worktree). Tests under `tests/unit/polish/`.
- Thread-safety: all mutations of orchestrator state go through a single `threading.Lock`; `state()` returns a deep-copied snapshot.

---

### Task 1: `SYNTHESIS` role + `synthesize()`

**Files:**
- Modify: `src/factory/orchestrator/types.py:7-12` (add `SYNTHESIS`)
- Create: `src/factory/polish/synthesis.py`
- Test: `tests/unit/polish/test_synthesis.py`

**Interfaces:**
- Consumes: `AgentBackend`, `AgentRole`, `AgentResult`, `Finding`.
- Produces: `synthesize(backend: AgentBackend, feedback: str, usecase: str) -> list[Finding]`. Used by Task 6.

- [ ] **Step 1: Add the role.** In `types.py`, add to `AgentRole`: `SYNTHESIS = "synthesis"`.

- [ ] **Step 2: Write the failing test**

```python
# tests/unit/polish/test_synthesis.py
from factory.orchestrator.backends import FakeAgentBackend
from factory.orchestrator.types import AgentResult, AgentRole
from factory.polish.synthesis import synthesize

def _backend(findings):
    return FakeAgentBackend({AgentRole.SYNTHESIS: [AgentResult(ok=True, output={"findings": findings})]})

def test_synthesize_parses_multiple_findings():
    backend = _backend([
        {"description": "sign-in button does nothing", "sr": "SR-010"},
        {"description": "PDF is blank", "snapshot": {"route": "/tailor"}},
    ])
    out = synthesize(backend, "the sign in is broken and the pdf is blank", "sign-in")
    assert [f.description for f in out] == ["sign-in button does nothing", "PDF is blank"]
    assert out[0].sr == "SR-010"
    assert out[0].usecase == "sign-in"
    assert out[1].snapshot == {"route": "/tailor"}

def test_synthesize_empty_when_backend_not_ok():
    backend = FakeAgentBackend({AgentRole.SYNTHESIS: [AgentResult(ok=False, output={})]})
    assert synthesize(backend, "nothing actionable", "sign-in") == []
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/unit/polish/test_synthesis.py -v`
Expected: FAIL — `ModuleNotFoundError: factory.polish.synthesis`.

- [ ] **Step 4: Implement**

```python
# src/factory/polish/synthesis.py
from __future__ import annotations

from factory.orchestrator.backends import AgentBackend
from factory.orchestrator.types import AgentRole
from factory.polish.finding import Finding

_PROMPT = """\
You are the SYNTHESIS role of a factory polish session on use case "{usecase}".
The human play-tested the app and gave this feedback:

{feedback}

Return JSON: {{"findings": [{{"description": str, "snapshot": object (optional,
repro route/steps/state), "sr": str|null (a violated SR-### if obvious),
"artifacts": [str] (optional)}}]}}. One finding per distinct issue. Do not invent
issues the feedback does not support."""

def synthesize(backend: AgentBackend, feedback: str, usecase: str) -> list[Finding]:
    result = backend.run(AgentRole.SYNTHESIS, _PROMPT.format(usecase=usecase, feedback=feedback))
    if not result.ok:
        return []
    items = result.output.get("findings", []) or []
    return [
        Finding(
            usecase=usecase,
            description=str(it["description"]),
            snapshot=dict(it.get("snapshot") or {}),
            sr=(str(it["sr"]) if it.get("sr") else None),
            artifacts=[str(a) for a in (it.get("artifacts") or [])],
        )
        for it in items
        if it.get("description")
    ]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/unit/polish/test_synthesis.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add src/factory/orchestrator/types.py src/factory/polish/synthesis.py tests/unit/polish/test_synthesis.py
git commit -m "feat(polish): SYNTHESIS role + synthesize() feedback->Finding"
```

---

### Task 2: `FixWorker` — serial queue + background thread (delegates to a `FixExecutor`)

**Files:**
- Create: `src/factory/polish/worker.py`
- Test: `tests/unit/polish/test_worker.py`

**Interfaces:**
- Consumes: `Finding`.
- Produces: `RunOutcome(ok: bool, detail: str = "")`; `LandedChange(finding: Finding, task_path: Path, task_id: str, status: str, detail: str)` (`status` ∈ `{"landed","failed"}`); `FixExecutor` Protocol `execute(self, finding: Finding) -> LandedChange`; `FixWorker(executor: FixExecutor)` with `.submit(finding)`, `.process_next(timeout: float|None=None) -> LandedChange | None`, `.pending_count() -> int`, `.start(on_landed: Callable[[LandedChange], None])`, `.stop()`. The worker is a pure queue/thread — the *isolation strategy* (worktree + fast-forward integrate) lives behind `FixExecutor` (Task 3). Used by Tasks 3, 5, 6.

- [ ] **Step 1: Write the failing test** (fake executor; deterministic)

```python
# tests/unit/polish/test_worker.py
import threading
from pathlib import Path

from factory.polish.finding import Finding
from factory.polish.worker import FixWorker, LandedChange

def _finding(desc="x"): return Finding(usecase="sign-in", description=desc)

def _landed(task_id="T-007", status="landed"):
    return LandedChange(finding=_finding(), task_path=Path(f"tasks/{task_id}.md"), task_id=task_id, status=status)

class _FakeExecutor:
    def __init__(self, results): self.results = results; self.seen = []
    def execute(self, finding):
        self.seen.append(finding.description)
        return self.results.pop(0)

def test_process_next_delegates_to_executor():
    ex = _FakeExecutor([_landed(status="landed")])
    w = FixWorker(ex)
    w.submit(_finding("sign-in broken"))
    landed = w.process_next()
    assert landed.status == "landed"
    assert ex.seen == ["sign-in broken"]

def test_process_next_returns_none_when_empty():
    assert FixWorker(_FakeExecutor([])).process_next(timeout=0.01) is None

def test_start_drains_in_background():
    ex = _FakeExecutor([_landed("T-001"), _landed("T-002")])
    w = FixWorker(ex)
    seen: list[str] = []
    done = threading.Event()
    def on_landed(lc):
        seen.append(lc.task_id)
        if len(seen) == 2: done.set()
    w.submit(_finding("a")); w.submit(_finding("b"))
    w.start(on_landed)
    assert done.wait(timeout=5.0), "worker did not drain both in time"
    w.stop()
    assert len(seen) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/polish/test_worker.py -v`
Expected: FAIL — `ModuleNotFoundError: factory.polish.worker`.

- [ ] **Step 3: Implement**

```python
# src/factory/polish/worker.py
from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from factory.polish.finding import Finding


@dataclass
class RunOutcome:
    ok: bool
    detail: str = ""


@dataclass
class LandedChange:
    finding: Finding
    task_path: Path
    task_id: str
    status: str  # "landed" | "failed"
    detail: str = ""


class FixExecutor(Protocol):
    """Applies one finding as a fix and reports what landed. The isolation
    strategy (worktree + fast-forward integrate) lives behind this seam so the
    worker stays a pure queue/thread."""

    def execute(self, finding: Finding) -> LandedChange: ...


class FixWorker:
    """Serial worker: drains findings one at a time on a background thread and
    delegates each to the injected FixExecutor. Never blocks the feedback path."""

    def __init__(self, executor: FixExecutor) -> None:
        self._executor = executor
        self._q: queue.Queue[Finding] = queue.Queue()
        self._stop: threading.Event | None = None
        self._thread: threading.Thread | None = None

    def submit(self, finding: Finding) -> None:
        self._q.put(finding)

    def pending_count(self) -> int:
        return self._q.qsize()

    def process_next(self, timeout: float | None = None) -> LandedChange | None:
        try:
            finding = self._q.get(timeout=timeout) if timeout is not None else self._q.get_nowait()
        except queue.Empty:
            return None
        try:
            return self._executor.execute(finding)
        finally:
            self._q.task_done()

    def start(self, on_landed: Callable[[LandedChange], None]) -> None:
        self._stop = threading.Event()

        def _loop() -> None:
            while self._stop is not None and not self._stop.is_set():
                landed = self.process_next(timeout=0.1)
                if landed is not None:
                    on_landed(landed)

        self._thread = threading.Thread(target=_loop, name="polish-fix-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._stop is not None:
            self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/polish/test_worker.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/factory/polish/worker.py tests/unit/polish/test_worker.py
git commit -m "feat(polish): FixWorker — serial queue + bg thread delegating to FixExecutor"
```

---

### Task 3: `WorktreeIsolatedExecutor` — worktree → factory-run `--auto` → fast-forward integrate

**Why isolated (not on the live branch):** the dev-server watches the live working tree. Running factory-run directly there would hot-reload broken mid-fix edits. Instead each fix runs in a throwaway git **worktree**; only the finished, green, committed result is **fast-forwarded** into the live branch — so the live tree only ever jumps between committed, validated states, and a failed fix never touches it. Because the worker is serial and the human never commits to the live branch, live HEAD is stable during a fix, so the FF always succeeds.

**Files:**
- Create: `src/factory/polish/executor.py`
- Test: `tests/integration/polish/test_executor.py` (uses a real temp git repo; the factory-run call is faked)

**Interfaces:**
- Consumes: `Finding`, `route`, `RunOutcome`/`LandedChange`/`FixExecutor` (Task 2).
- Produces: `SubprocessFactoryRunner(provider=None, model=None).run(task_id: str, repo_root: Path) -> RunOutcome` (runs `python -m factory.orchestrator run --repo <root> --task <id> --auto` in `repo_root`); `WorktreeIsolatedExecutor(live_root: Path, *, factory_run: Callable[[str, Path], RunOutcome], tasks_subdir="tasks", worktrees_root: Path|None=None)` implementing `FixExecutor`. Used by Tasks 6 / 7 and Plan B2.

- [ ] **Step 1: Write the failing integration test** (real git; fake `factory_run` so no real LLM/subprocess)

```python
# tests/integration/polish/test_executor.py
import subprocess
from pathlib import Path

from factory.polish.executor import WorktreeIsolatedExecutor
from factory.polish.finding import Finding
from factory.polish.worker import RunOutcome

def _git(root, *a): subprocess.run(["git", "-C", str(root), *a], check=True, capture_output=True)

def _repo(tmp_path) -> Path:
    root = tmp_path / "live"; root.mkdir()
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "t@t"); _git(root, "config", "user.name", "t")
    (root / "app.txt").write_text("v0", encoding="utf-8")
    _git(root, "add", "-A"); _git(root, "commit", "-m", "init")
    return root

def test_green_fix_fast_forwards_into_live(tmp_path):
    live = _repo(tmp_path)
    def fake_run(task_id, wt: Path) -> RunOutcome:
        (wt / "app.txt").write_text("v1-fixed", encoding="utf-8")  # dev agent edits in the worktree
        subprocess.run(["git", "-C", str(wt), "commit", "-am", f"fix {task_id}"], check=True, capture_output=True)
        return RunOutcome(ok=True)
    ex = WorktreeIsolatedExecutor(live, factory_run=fake_run)
    landed = ex.execute(Finding(usecase="sign-in", description="broken"))
    assert landed.status == "landed"
    assert (live / "app.txt").read_text(encoding="utf-8") == "v1-fixed"      # FF'd into the LIVE tree
    assert (live / "tasks" / f"{landed.task_id}.md").exists()               # task rode in with the fix
    leftover = list((live / ".worktrees").glob("*")) if (live / ".worktrees").exists() else []
    assert leftover == []                                                    # worktree cleaned up

def test_red_fix_leaves_live_untouched(tmp_path):
    live = _repo(tmp_path)
    def fake_run(task_id, wt: Path) -> RunOutcome:
        (wt / "app.txt").write_text("broken-half-edit", encoding="utf-8")   # uncommitted; factory-run failed
        return RunOutcome(ok=False, detail="validation red")
    ex = WorktreeIsolatedExecutor(live, factory_run=fake_run)
    landed = ex.execute(Finding(usecase="sign-in", description="broken"))
    assert landed.status == "failed"
    assert (live / "app.txt").read_text(encoding="utf-8") == "v0"           # live tree untouched
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/integration/polish/test_executor.py -v`
Expected: FAIL — `ModuleNotFoundError: factory.polish.executor`.

- [ ] **Step 3: Implement**

```python
# src/factory/polish/executor.py
from __future__ import annotations

import re
import subprocess
import sys
import uuid
from collections.abc import Callable
from pathlib import Path

from factory.polish.finding import Finding
from factory.polish.routing import route
from factory.polish.worker import LandedChange, RunOutcome

_ID_RE = re.compile(r"T-(\d+)")


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)


class SubprocessFactoryRunner:
    """Runs factory-run in --auto mode (no human gate) inside a given repo dir.
    In --auto mode factory-run's own VALIDATION (the task's SR gate + standing
    regression) and LLM review ARE the acceptance; commit-on-green happens inside
    factory-run. This runner just reports ok/failed."""

    def __init__(self, provider: str | None = None, model: str | None = None) -> None:
        self._provider = provider
        self._model = model

    def run(self, task_id: str, repo_root: Path) -> RunOutcome:
        argv = [sys.executable, "-m", "factory.orchestrator", "run",
                "--repo", str(repo_root), "--task", task_id, "--auto"]
        if self._provider:
            argv += ["--provider", self._provider]
        if self._model:
            argv += ["--model", self._model]
        proc = subprocess.run(argv, cwd=str(repo_root))
        return RunOutcome(ok=proc.returncode == 0,
                          detail="" if proc.returncode == 0 else f"factory-run exit {proc.returncode}")


class WorktreeIsolatedExecutor:
    """Apply a fix in an isolated worktree, then fast-forward the finished green
    result into the live branch. The dev-server's tree only ever sees committed,
    validated states."""

    def __init__(self, live_root: Path, *, factory_run: Callable[[str, Path], RunOutcome],
                 tasks_subdir: str = "tasks", worktrees_root: Path | None = None) -> None:
        self._live = live_root
        self._factory_run = factory_run
        self._tasks_subdir = tasks_subdir
        self._worktrees_root = worktrees_root or (live_root / ".worktrees")

    def execute(self, finding: Finding) -> LandedChange:
        branch = f"polish-fix/{uuid.uuid4().hex[:8]}"
        self._worktrees_root.mkdir(parents=True, exist_ok=True)
        wt = self._worktrees_root / branch.replace("/", "-")
        _git(self._live, "worktree", "add", "-b", branch, str(wt), "HEAD")
        task_path = wt / self._tasks_subdir / "pending.md"  # replaced below; keeps type-checkers happy
        try:
            task_path = route(finding, wt / self._tasks_subdir)
            m = _ID_RE.search(task_path.name)
            task_id = m.group(0) if m else task_path.stem
            _git(wt, "add", "-A")
            _git(wt, "commit", "-m", f"chore(polish): queue {task_id}")
            outcome = self._factory_run(task_id, wt)
            status, detail, live_task_path = "failed", outcome.detail, task_path
            if outcome.ok:
                ff = _git(self._live, "merge", "--ff-only", branch)
                if ff.returncode == 0:
                    status, detail = "landed", ""
                    live_task_path = self._live / self._tasks_subdir / task_path.name
                else:
                    detail = f"fast-forward into live failed: {ff.stderr.strip()}"
            return LandedChange(finding=finding, task_path=live_task_path,
                                task_id=task_id, status=status, detail=detail)
        finally:
            _git(self._live, "worktree", "remove", "--force", str(wt))
            _git(self._live, "branch", "-D", branch)  # best-effort; ignored if already gone
```

- [ ] **Step 4: Run tests + lint/type**

Run: `python -m pytest tests/integration/polish/test_executor.py -v && ruff check src/factory/polish/executor.py && pyright src/factory/polish/executor.py`
Expected: PASS (2 tests); clean.

- [ ] **Step 5: Commit**

```bash
git add src/factory/polish/executor.py tests/integration/polish/test_executor.py
git commit -m "feat(polish): WorktreeIsolatedExecutor — worktree fix + fast-forward integrate"
```

---

### Task 4: Gate 1 — pre-queue glance (accept / edit / discard)

**Files:**
- Create: `src/factory/polish/gates.py`
- Test: `tests/unit/polish/test_gates.py`

**Interfaces:**
- Consumes: `Finding`.
- Produces: `Gate1(next_id: Callable[[], str] = ...)` with `.add(finding) -> str` (returns a gate id), `.pending() -> dict[str, Finding]`, `.accept(gid) -> Finding`, `.edit(gid, **changes) -> Finding`, `.discard(gid) -> None`. `accept`/`edit` return the finding to enqueue and remove it from pending; `discard` drops it. Used by Task 6.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/polish/test_gates.py
import pytest
from factory.polish.finding import Finding
from factory.polish.gates import Gate1

def _f(desc="x"): return Finding(usecase="sign-in", description=desc)

def test_gate1_accept_returns_and_clears():
    g = Gate1()
    gid = g.add(_f("broken"))
    assert list(g.pending()) == [gid]
    f = g.accept(gid)
    assert f.description == "broken"
    assert g.pending() == {}

def test_gate1_edit_applies_changes_then_returns():
    g = Gate1()
    gid = g.add(_f("typo desc"))
    f = g.edit(gid, description="clearer desc", sr="SR-010")
    assert f.description == "clearer desc" and f.sr == "SR-010"
    assert g.pending() == {}

def test_gate1_discard_drops():
    g = Gate1()
    gid = g.add(_f())
    g.discard(gid)
    assert g.pending() == {}
    with pytest.raises(KeyError):
        g.accept(gid)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/polish/test_gates.py -v`
Expected: FAIL — `ModuleNotFoundError: factory.polish.gates`.

- [ ] **Step 3: Implement**

```python
# src/factory/polish/gates.py
from __future__ import annotations

import dataclasses
import itertools
from collections.abc import Callable

from factory.polish.finding import Finding


def _seq_ids(prefix: str) -> Callable[[], str]:
    counter = itertools.count(1)
    return lambda: f"{prefix}{next(counter)}"


class Gate1:
    """Pre-queue glance: a synthesized finding waits here for accept/edit/discard
    before it enters the fix queue. Nothing is enqueued without passing Gate 1."""

    def __init__(self, next_id: Callable[[], str] | None = None) -> None:
        self._next_id = next_id or _seq_ids("g1-")
        self._pending: dict[str, Finding] = {}

    def add(self, finding: Finding) -> str:
        gid = self._next_id()
        self._pending[gid] = finding
        return gid

    def pending(self) -> dict[str, Finding]:
        return dict(self._pending)

    def accept(self, gid: str) -> Finding:
        return self._pending.pop(gid)

    def edit(self, gid: str, **changes) -> Finding:
        finding = dataclasses.replace(self._pending.pop(gid), **changes)
        return finding

    def discard(self, gid: str) -> None:
        self._pending.pop(gid, None)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/polish/test_gates.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/factory/polish/gates.py tests/unit/polish/test_gates.py
git commit -m "feat(polish): Gate1 pre-queue glance (accept/edit/discard)"
```

---

### Task 5: Gate 2 — acceptance checklist + rework loop

**Files:**
- Modify: `src/factory/polish/gates.py`
- Test: `tests/unit/polish/test_gates.py`

**Interfaces:**
- Consumes: `Finding`, `LandedChange` (Task 2).
- Produces: `Gate2Row(gid: str, change: LandedChange, verdict: str)` (`verdict` ∈ `{"pending","accepted","wrong"}`); `Gate2(next_id=...)` with `.add(change: LandedChange) -> str`, `.rows() -> list[Gate2Row]`, `.tick(gid) -> Finding | None` (accept; returns the SR-linked finding if the change should re-ground an SR, else None), `.comment(gid, text: str) -> Finding` (mark wrong, return a NEW linked rework finding to re-queue). Used by Task 6.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/unit/polish/test_gates.py
from pathlib import Path
from factory.polish.gates import Gate2
from factory.polish.worker import LandedChange

def _landed(desc="x", sr=None, status="landed"):
    f = Finding(usecase="sign-in", description=desc, sr=sr)
    return LandedChange(finding=f, task_path=Path("tasks/T-007.md"), task_id="T-007", status=status)

def test_gate2_tick_accepts_and_returns_sr_finding():
    g = Gate2()
    gid = g.add(_landed(sr="SR-010"))
    reground = g.tick(gid)
    assert reground is not None and reground.sr == "SR-010"
    assert g.rows()[0].verdict == "accepted"

def test_gate2_tick_without_sr_returns_none():
    g = Gate2()
    gid = g.add(_landed(sr=None))
    assert g.tick(gid) is None
    assert g.rows()[0].verdict == "accepted"

def test_gate2_comment_spawns_linked_rework_finding():
    g = Gate2()
    gid = g.add(_landed(desc="sign-in fix", sr="SR-010"))
    rework = g.comment(gid, "still fails on Safari")
    assert "still fails on Safari" in rework.description
    assert rework.sr == "SR-010"
    assert rework.snapshot.get("rework_of") == "T-007"
    assert g.rows()[0].verdict == "wrong"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/polish/test_gates.py -k gate2 -v`
Expected: FAIL — `cannot import name 'Gate2'`.

- [ ] **Step 3: Implement**

```python
# add to src/factory/polish/gates.py
import dataclasses as _dc

from factory.polish.worker import LandedChange


@_dc.dataclass
class Gate2Row:
    gid: str
    change: LandedChange
    verdict: str = "pending"  # pending | accepted | wrong


class Gate2:
    """Post-fix acceptance checklist against the reloaded app. tick = accept
    (re-ground the SR if linked); comment = wrong -> a new linked rework finding."""

    def __init__(self, next_id: Callable[[], str] | None = None) -> None:
        self._next_id = next_id or _seq_ids("g2-")
        self._rows: dict[str, Gate2Row] = {}

    def add(self, change: LandedChange) -> str:
        gid = self._next_id()
        self._rows[gid] = Gate2Row(gid=gid, change=change)
        return gid

    def rows(self) -> list[Gate2Row]:
        return list(self._rows.values())

    def tick(self, gid: str) -> Finding | None:
        row = self._rows[gid]
        row.verdict = "accepted"
        return row.change.finding if row.change.finding.sr else None

    def comment(self, gid: str, text: str) -> Finding:
        row = self._rows[gid]
        row.verdict = "wrong"
        orig = row.change.finding
        return Finding(
            usecase=orig.usecase,
            description=f"[rework of {row.change.task_id}] {text}",
            snapshot={**orig.snapshot, "rework_of": row.change.task_id},
            sr=orig.sr,
            artifacts=list(orig.artifacts),
        )
```

- [ ] **Step 4: Run tests + lint/type**

Run: `python -m pytest tests/unit/polish/test_gates.py -v && ruff check src/factory/polish/gates.py && pyright src/factory/polish/gates.py`
Expected: PASS (6 tests); clean.

- [ ] **Step 5: Commit**

```bash
git add src/factory/polish/gates.py tests/unit/polish/test_gates.py
git commit -m "feat(polish): Gate2 acceptance checklist + comment->rework finding"
```

---

### Task 6: `PolishOrchestrator` — wire the deterministic loop + `state()` contract

**Files:**
- Create: `src/factory/polish/orchestrator.py`
- Test: `tests/unit/polish/test_orchestrator.py`

**Interfaces:**
- Consumes: `Playground`/`PlaygroundSession`, `AgentBackend`, `synthesize` (T1), `FixWorker`/`LandedChange` (T2/3), `Gate1` (T4), `Gate2` (T5).
- Produces: `PolishOrchestrator(playground, backend, worker, *, open_nav=None)` with `.setup(usecase)`, `.submit_feedback(text) -> list[str]` (returns Gate-1 ids), `.accept_finding(gid)`, `.edit_finding(gid, **changes)`, `.discard_finding(gid)`, `.tick(gid)`, `.comment(gid, text) -> str` (returns the new Gate-1 id for the rework), `.state() -> dict`, `.teardown()`. This `state()` dict + these methods are the exact contract Plan B2 (factory-watch UI) consumes.

- [ ] **Step 1: Write the failing test** (headless: fake backend, fake runner, stub playground)

```python
# tests/unit/polish/test_orchestrator.py
import threading
from pathlib import Path

from factory.orchestrator.backends import FakeAgentBackend
from factory.orchestrator.types import AgentResult, AgentRole
from factory.polish.playground import Playground, PlaygroundSession
from factory.polish.worker import FixWorker, LandedChange
from factory.polish.orchestrator import PolishOrchestrator

class _StubPlayground:
    def list_usecases(self): return ["sign-in"]
    def setup(self, usecase): return PlaygroundSession(entrypoints=["http://localhost:3000"], describe="up")

class _FakeExecutor:
    """Stands in for WorktreeIsolatedExecutor: returns a LandedChange per finding."""
    def __init__(self, statuses): self.statuses = statuses; self.n = 0
    def execute(self, finding):
        self.n += 1
        st = self.statuses.pop(0)
        return LandedChange(finding=finding, task_path=Path(f"tasks/T-{self.n:03d}.md"),
                            task_id=f"T-{self.n:03d}", status=st)

def _backend(findings):
    return FakeAgentBackend({AgentRole.SYNTHESIS: [AgentResult(ok=True, output={"findings": findings})]})

import time

def _wait_gate2(orch, n=1, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if len(orch.state()["gate2"]) >= n:
            return orch.state()["gate2"]
        time.sleep(0.02)
    raise AssertionError(f"gate2 did not reach {n} row(s) in time")

def test_feedback_to_gate1_to_worker_to_gate2(tmp_path):
    backend = _backend([{"description": "sign-in broken", "sr": "SR-010"}])
    worker = FixWorker(_FakeExecutor(["landed"]))
    orch = PolishOrchestrator(_StubPlayground(), backend, worker, open_nav=lambda eps: None)
    orch.setup("sign-in")  # starts the background worker thread
    gids = orch.submit_feedback("the sign in is broken")
    assert len(gids) == 1
    assert orch.state()["gate1"][0]["description"] == "sign-in broken"
    # accept -> the background worker drains it and calls record_landed itself
    orch.accept_finding(gids[0])
    row = _wait_gate2(orch)[0]
    assert row["status"] == "landed" and row["verdict"] == "pending"
    orch.teardown()

def test_comment_requeues_rework(tmp_path):
    backend = _backend([{"description": "pdf blank"}])
    worker = FixWorker(_FakeExecutor(["landed"]))
    orch = PolishOrchestrator(_StubPlayground(), backend, worker, open_nav=lambda eps: None)
    orch.setup("sign-in")
    (gid,) = orch.submit_feedback("pdf is blank")
    orch.accept_finding(gid)
    g2 = _wait_gate2(orch)[0]["gid"]
    new_g1 = orch.comment(g2, "still blank")
    assert new_g1 in orch.state()["gate1_ids"]
    orch.teardown()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/polish/test_orchestrator.py -v`
Expected: FAIL — `ModuleNotFoundError: factory.polish.orchestrator`.

- [ ] **Step 3: Implement**

```python
# src/factory/polish/orchestrator.py
from __future__ import annotations

import threading
from collections.abc import Callable

from factory.orchestrator.backends import AgentBackend
from factory.polish.finding import Finding
from factory.polish.gates import Gate1, Gate2
from factory.polish.playground import Playground, PlaygroundSession
from factory.polish.synthesis import synthesize
from factory.polish.worker import FixWorker, LandedChange


class PolishOrchestrator:
    """Deterministic polish loop. Python owns the topology; the LLM is invoked
    only inside submit_feedback (SYNTHESIS). Fixes run on the worker's background
    thread, so the feedback path never blocks."""

    def __init__(self, playground: Playground, backend: AgentBackend, worker: FixWorker,
                 *, open_nav: Callable[[list[str]], None] | None = None) -> None:
        self._pg = playground
        self._backend = backend
        self._worker = worker
        self._open_nav = open_nav
        self._lock = threading.Lock()
        self._gate1 = Gate1()
        self._gate2 = Gate2()
        self._session: PlaygroundSession | None = None
        self._usecase = ""

    # --- lifecycle ---
    def setup(self, usecase: str) -> None:
        with self._lock:
            self._usecase = usecase
            self._session = self._pg.setup(usecase)
        if self._open_nav is not None:
            self._open_nav(self._session.entrypoints)
        self._worker.start(self.record_landed)

    def teardown(self) -> None:
        self._worker.stop()
        with self._lock:
            if self._session is not None:
                self._session.teardown()
                self._session = None

    # --- feedback -> synthesis -> Gate 1 ---
    def submit_feedback(self, text: str) -> list[str]:
        findings = synthesize(self._backend, text, self._usecase)
        with self._lock:
            return [self._gate1.add(f) for f in findings]

    def accept_finding(self, gid: str) -> None:
        with self._lock:
            finding = self._gate1.accept(gid)
        self._worker.submit(finding)

    def edit_finding(self, gid: str, **changes) -> None:
        with self._lock:
            finding = self._gate1.edit(gid, **changes)
        self._worker.submit(finding)

    def discard_finding(self, gid: str) -> None:
        with self._lock:
            self._gate1.discard(gid)

    # --- worker landing -> Gate 2 ---
    def record_landed(self, change: LandedChange) -> None:
        with self._lock:
            self._gate2.add(change)

    def tick(self, gid: str) -> None:
        with self._lock:
            self._gate2.tick(gid)  # re-ground handled by caller/telemetry; no re-queue

    def comment(self, gid: str, text: str) -> str:
        with self._lock:
            rework = self._gate2.comment(gid, text)
            new_gid = self._gate1.add(rework)
        return new_gid

    # --- UI contract ---
    def state(self) -> dict:
        with self._lock:
            g1 = self._gate1.pending()
            return {
                "usecase": self._usecase,
                "entrypoints": list(self._session.entrypoints) if self._session else [],
                "queue_size": self._worker.pending_count(),
                "gate1_ids": list(g1),
                "gate1": [{"gid": k, "description": v.description, "sr": v.sr} for k, v in g1.items()],
                "gate2": [
                    {"gid": r.gid, "task_id": r.change.task_id, "description": r.change.finding.description,
                     "sr": r.change.finding.sr, "status": r.change.status, "verdict": r.verdict}
                    for r in self._gate2.rows()
                ],
            }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/polish/test_orchestrator.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Run the whole polish + validation suite, lint, type**

Run: `python -m pytest tests/unit/polish tests/unit/validation -v && ruff check src/factory/polish && pyright src/factory/polish`
Expected: PASS; clean.

- [ ] **Step 6: Commit**

```bash
git add src/factory/polish/orchestrator.py tests/unit/polish/test_orchestrator.py
git commit -m "feat(polish): PolishOrchestrator — deterministic loop + state() UI contract"
```

---

### Task 7: Route `factory polish` through the orchestrator; retire the skill-owned loop

**Files:**
- Modify: `src/factory/polish/cli.py` (build the orchestrator; keep discovery/list)
- Modify: `src/factory/polish/session.py` (deprecate the old `run_polish_session(findings=...)` path or delegate)
- Modify: `.pi/skills/polish/SKILL.md` (shrink to: how to converse for the SYNTHESIS node only; the loop/gates/routing now live in Python)
- Test: `tests/unit/polish/test_cli.py` (confirm existing path with `git ls-files | grep polish/test_cli`)

**Interfaces:**
- Consumes: `PolishOrchestrator` (T6), `FixWorker` (T2), `WorktreeIsolatedExecutor`/`SubprocessFactoryRunner` (T3), `load_config` (existing).
- Produces: a `factory polish` entry that constructs and drives the orchestrator headlessly (a text feedback loop) — the fallback driver when the factory-watch UI (Plan B2) is not attached.

- [ ] **Step 1: Write the failing test** (a headless driver that reads scripted feedback lines, using fakes — assert it produces a Gate-2 row without invoking a real LLM or subprocess)

```python
# tests/unit/polish/test_cli.py  (add)
from factory.polish.cli import build_orchestrator

def test_build_orchestrator_wires_from_config(tmp_path, monkeypatch):
    # minimal .factory/factory.yaml with a dev-server playground
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory" / "factory.yaml").write_text(
        "playgrounds:\n  web:\n    type: dev-server\n    browse_url: http://x\n"
        "    usecases: [sign-in]\n    services: []\n", encoding="utf-8")
    orch = build_orchestrator(tmp_path, playground="web", provider=None, model=None)
    assert orch is not None
    assert hasattr(orch, "submit_feedback") and hasattr(orch, "state")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/polish/test_cli.py -k build_orchestrator -v`
Expected: FAIL — `cannot import name 'build_orchestrator'`.

- [ ] **Step 3: Implement `build_orchestrator` + wire the CLI**

```python
# src/factory/polish/cli.py  (add; keep the existing list/discover commands)
from pathlib import Path

from factory.polish.config import load_config
from factory.polish.executor import SubprocessFactoryRunner, WorktreeIsolatedExecutor
from factory.polish.orchestrator import PolishOrchestrator
from factory.polish.session import open_navigator
from factory.polish.worker import FixWorker
from factory.orchestrator.pi_backend import PiBackend  # the real AgentBackend impl


def build_orchestrator(project_root: Path, playground: str, *, provider, model) -> PolishOrchestrator:
    cfg = load_config(project_root)
    pg = cfg.playgrounds[playground]
    # Fixes run in an isolated worktree, then fast-forward into the live branch
    # the dev-server watches (Task 3) — never edit the live tree mid-fix.
    executor = WorktreeIsolatedExecutor(
        project_root,
        factory_run=SubprocessFactoryRunner(provider=provider, model=model).run,
    )
    worker = FixWorker(executor)
    backend = PiBackend(project_root, provider=provider, model=model)  # match PiBackend's real ctor
    return PolishOrchestrator(pg, backend, worker, open_nav=open_navigator)
```

(Confirm `PiBackend`'s real constructor signature in `src/factory/orchestrator/pi_backend.py` and adjust the call; the test uses `build_orchestrator` only for wiring and does not run synthesis, so a real backend is constructed but never invoked.)

- [ ] **Step 4: Shrink the skill.** Replace `.pi/skills/polish/SKILL.md`'s Steps/Rules with a short note: the polish **loop, gates, routing, and worker are the deterministic `PolishOrchestrator`** (`python -m factory.polish ...`); the model's only job is, when asked by the orchestrator's `SYNTHESIS` node, to convert the human's natural-language feedback into the findings JSON (schema in `synthesis.py`). Keep the "nothing lands without the human's Gate-1 accept and Gate-2 tick" trust note.

- [ ] **Step 5: Run the full suite + lint/type**

Run: `python -m pytest tests/unit/polish tests/unit/validation -v && ruff check src/factory/polish && pyright src/factory/polish`
Expected: PASS; clean.

- [ ] **Step 6: Commit**

```bash
git add src/factory/polish/cli.py src/factory/polish/session.py .pi/skills/polish/SKILL.md tests/unit/polish/test_cli.py
git commit -m "feat(polish): drive factory-polish through PolishOrchestrator; shrink skill to SYNTHESIS-only"
```

---

## Self-Review

**Spec coverage (Inc 2 design §4–§7):**
- §4.1 node flow (setup → capture → SYNTHESIS → Gate1 → worker → Gate2 → teardown) — Tasks 1,4,5,6. ✅
- §4.2 loop/gates/worker move out of the skill into Python — Task 7. ✅
- §5 serial worker, factory-run `--auto`, commit-on-green, red→failed-to-fix, **worktree-isolated + fast-forward integrate** — Tasks 2,3. ✅ (commit-on-green + validation/regression are factory-run's own behavior via `--auto`; the executor FF-merges only green results into the live branch, so the dev-server never hot-reloads a mid-fix edit; the worker/orchestrator record landed/failed.)
- §6.1 Gate 1 lightweight pre-queue accept/edit/discard — Task 4. ✅
- §6.2 Gate 2 acceptance checklist, tick=accept/re-ground, comment=wrong→new linked finding re-queued — Task 5, wired in Task 6. ✅
- §7 UI surface — NOT built here by design; the `state()` dict + transition methods (Task 6) are the exact contract Plan B2 consumes. Flagged, not silently dropped.
- Async/never-blocks (locked decision #3) — background worker thread, Task 3/6. ✅
- Serial-on-live (locked decision #4) — single `queue.Queue`, one `process_next` at a time, Task 2. ✅

**Placeholder scan:** no TBD/TODO; every code step is complete. Two "confirm the real signature" notes (PiBackend ctor in Task 7; `sys.executable` vs `python` in Task 3) point at genuine environment facts the executor must read, not unwritten logic. ✅

**Type consistency:** `Finding`/`route`/`LandedChange`/`RunOutcome`/`Gate1`/`Gate2` names and signatures are identical across Tasks 2–6; `AgentRole.SYNTHESIS` added in T1 and used in T1's `synthesize`; `record_landed` is the `on_landed` callback shape `Callable[[LandedChange], None]` from Task 3 and is passed to `worker.start` in Task 6. ✅

**Follow-up:** Plan B2 (factory-watch UI) consumes `PolishOrchestrator.state()` + methods. Isolation note (Task 3): factory-run runs in a throwaway worktree and only the green result is fast-forwarded into the live branch, so the dev-server hot-reloads exactly once per fix, to a consistent validated state — never a broken mid-fix edit. The FF is always clean because the worker is serial and the human never commits to the live branch (edge case: if live HEAD ever moved, rebase-then-FF; noted, not the norm).
