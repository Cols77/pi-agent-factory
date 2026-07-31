# Polish Workflow — P1 (decoupled spine) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the decoupled spine of the `factory polish` workflow — `Finding`/`Playground` contracts, a finding→ticket router, a thin reference playground, a per-project playground registry, the deterministic session orchestration (setup → open navigator → route findings → teardown), a `factory polish` CLI, and the conversational `polish` skill — so a human can exercise a project's use case, and their feedback becomes fix-tickets in the ledger.

**Architecture:** Pure, independently-testable units plus one LLM-facing skill. A `Playground` owns only environment lifecycle (`setup(usecase) -> PlaygroundSession{entrypoints, describe, teardown}`). The pif session collects feedback and synthesizes `Finding`s; the router turns each `Finding` into a ledger task (`satisfies:` the linked SR when present). A project declares its playgrounds in `.factory/registry.py`. P1 ships against a thin `ScenarioReplayPlayground` reference and does NOT depend on Increment 1B or the (unbuilt) sim-testbench interactive pieces.

**Tech Stack:** Python 3.11–3.12, stdlib (`dataclasses`, `json`, `re`, `importlib`, `subprocess`), `python-frontmatter` (existing dep), `pytest` (`-m unit`).

## Global Constraints

- Python `>=3.11,<3.13`; every new module starts with `from __future__ import annotations`.
- Ruff `line-length = 100`.
- Unit tests: `pytestmark = pytest.mark.unit` at module top; run with `uv run pytest` (default `addopts = -m unit`).
- `@dataclass(frozen=True)` for value types (`Finding`); mutable dataclass only where a method mutates/holds a callback (`PlaygroundSession`).
- **No new dependencies** — stdlib + existing `python-frontmatter` only.
- New source under `src/factory/polish/`; new tests under `tests/unit/polish/`.
- Ledger task files use `python-frontmatter`; a routed task MUST parse via `factory.orchestrator.ledger.load_tasks` (fields `id`, `title`, `status`, `dod`, optional `satisfies`).
- **Work in the isolated worktree** `C:/coding/pi-agent-factory-wt/polish` on branch `design/polish-workflow` (the factory main tree is used by parallel sessions — never commit there). Prefix commands with `cd /c/coding/pi-agent-factory-wt/polish && …`.
- Commit only the files each task creates (never `git add -A`); revert any `uv.lock` churn (`git checkout -- uv.lock`) before committing.

---

### Task 1: Contracts — `Finding`, `PlaygroundSession`, `Playground`

**Files:**
- Create: `src/factory/polish/__init__.py` (empty)
- Create: `src/factory/polish/finding.py`
- Create: `src/factory/polish/playground.py`
- Test: `tests/unit/polish/__init__.py` (empty), `tests/unit/polish/test_contracts.py`

**Interfaces:**
- Produces:
  - `Finding(usecase: str, description: str, snapshot: dict = {}, sr: str | None = None, artifacts: list[str] = [])` (frozen)
  - `PlaygroundSession(entrypoints: list[str] = [], describe: str = "", on_teardown: Callable[[], None] | None = None)` with a `teardown()` method that invokes `on_teardown` if set.
  - `Playground(Protocol)` (runtime_checkable) with `list_usecases() -> list[str]` and `setup(usecase: str) -> PlaygroundSession`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/polish/__init__.py` (empty) and `tests/unit/polish/test_contracts.py`:

```python
import pytest
from factory.polish.finding import Finding
from factory.polish.playground import Playground, PlaygroundSession

pytestmark = pytest.mark.unit


def test_finding_defaults():
    f = Finding(usecase="u", description="d")
    assert f.snapshot == {} and f.sr is None and f.artifacts == []
    full = Finding("u", "d", snapshot={"k": 1}, sr="SR-001", artifacts=["a.png"])
    assert full.snapshot == {"k": 1} and full.sr == "SR-001" and full.artifacts == ["a.png"]


def test_session_teardown_invokes_callback():
    calls = []
    s = PlaygroundSession(entrypoints=["http://x"], describe="d", on_teardown=lambda: calls.append(1))
    s.teardown()
    assert calls == [1]
    # No callback → teardown is a no-op, not an error.
    PlaygroundSession().teardown()


def test_playground_is_structural():
    class Ref:
        def list_usecases(self):
            return ["a"]

        def setup(self, usecase):
            return PlaygroundSession()

    assert isinstance(Ref(), Playground)
    assert not isinstance(object(), Playground)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /c/coding/pi-agent-factory-wt/polish && uv run pytest tests/unit/polish/test_contracts.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'factory.polish'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/factory/polish/__init__.py` (empty). Create `src/factory/polish/finding.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Finding:
    usecase: str
    description: str
    snapshot: dict = field(default_factory=dict)
    sr: str | None = None
    artifacts: list[str] = field(default_factory=list)
```

Create `src/factory/polish/playground.py`:

```python
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class PlaygroundSession:
    entrypoints: list[str] = field(default_factory=list)
    describe: str = ""
    on_teardown: Callable[[], None] | None = None

    def teardown(self) -> None:
        if self.on_teardown is not None:
            self.on_teardown()


@runtime_checkable
class Playground(Protocol):
    def list_usecases(self) -> list[str]: ...
    def setup(self, usecase: str) -> PlaygroundSession: ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /c/coding/pi-agent-factory-wt/polish && uv run pytest tests/unit/polish/test_contracts.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
cd /c/coding/pi-agent-factory-wt/polish
git add src/factory/polish/__init__.py src/factory/polish/finding.py src/factory/polish/playground.py tests/unit/polish/
git commit -m "feat(polish): Finding + Playground/PlaygroundSession contracts"
```

---

### Task 2: Router — `Finding` → ledger task

**Files:**
- Create: `src/factory/polish/routing.py`
- Test: `tests/unit/polish/test_routing.py`

**Interfaces:**
- Consumes: `Finding` (Task 1); `factory.orchestrator.ledger.load_tasks` (for the test).
- Produces: `route(finding: Finding, tasks_dir: Path) -> Path` — allocates the next `T-###` id (max existing + 1, zero-padded to 3, starting `T-001`), writes a task file with `status: todo`, `dod: ["the <usecase> use case no longer exhibits: <description>"]`, `satisfies: [finding.sr]` when `sr` is set, and a body containing the description + a fenced JSON `snapshot` + artifacts. The file MUST parse via `load_tasks`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/polish/test_routing.py`:

```python
import pytest
from factory.orchestrator.ledger import load_tasks
from factory.polish.finding import Finding
from factory.polish.routing import route

pytestmark = pytest.mark.unit


def test_route_creates_parseable_task_with_sr(tmp_path):
    tasks = tmp_path / "tasks"
    f = Finding(usecase="shark_warning", description="drone ignored out-of-zone swimmer",
                snapshot={"t": 20.0}, sr="SR-001", artifacts=["shot.png"])
    path = route(f, tasks)
    assert path.name == "T-001.md"
    t = load_tasks(tasks)[0]
    assert t.id == "T-001"
    assert "shark_warning" in t.title
    assert t.status == "todo"
    assert t.satisfies == ["SR-001"]
    assert any("no longer exhibits" in d for d in t.dod)
    assert "drone ignored out-of-zone swimmer" in t.body
    assert '"t": 20.0' in t.body  # snapshot embedded


def test_route_without_sr_has_empty_satisfies(tmp_path):
    tasks = tmp_path / "tasks"
    route(Finding("uc", "first"), tasks)
    p2 = route(Finding("uc", "second"), tasks)
    assert p2.name == "T-002.md"           # sequential ids
    assert load_tasks(tasks)[0].satisfies == []


def test_route_coexists_with_existing_task_ids(tmp_path):
    tasks = tmp_path / "tasks"
    tasks.mkdir()
    (tasks / "T-041.md").write_text(
        "---\nid: T-041\ntitle: t\nstatus: todo\ndod:\n  - x\n---\nbody\n", encoding="utf-8"
    )
    path = route(Finding("uc", "d"), tasks)
    assert path.name == "T-042.md"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /c/coding/pi-agent-factory-wt/polish && uv run pytest tests/unit/polish/test_routing.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'factory.polish.routing'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/factory/polish/routing.py`:

```python
from __future__ import annotations

import json
import re
from pathlib import Path

import frontmatter

from factory.polish.finding import Finding

_ID_RE = re.compile(r"T-(\d+)")


def _next_task_id(tasks_dir: Path) -> str:
    nums = [
        int(m.group(1))
        for p in tasks_dir.glob("T-*.md")
        if (m := _ID_RE.search(p.name))
    ]
    return f"T-{(max(nums) + 1) if nums else 1:03d}"


def route(finding: Finding, tasks_dir: Path) -> Path:
    tasks_dir.mkdir(parents=True, exist_ok=True)
    task_id = _next_task_id(tasks_dir)
    title = f"polish[{finding.usecase}]: {finding.description[:60]}"
    dod = [f"the {finding.usecase} use case no longer exhibits: {finding.description}"]

    lines = [
        f"From a `factory polish` session on use case **{finding.usecase}**.",
        "",
        finding.description,
    ]
    if finding.snapshot:
        lines += ["", "## Reproduction snapshot", "```json", json.dumps(finding.snapshot, indent=2), "```"]
    if finding.artifacts:
        lines += ["", "## Artifacts", *[f"- {a}" for a in finding.artifacts]]

    post = frontmatter.Post("\n".join(lines), id=task_id, title=title, status="todo", dod=dod)
    if finding.sr:
        post["satisfies"] = [finding.sr]

    path = tasks_dir / f"{task_id}.md"
    path.write_text(frontmatter.dumps(post), encoding="utf-8")
    return path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /c/coding/pi-agent-factory-wt/polish && uv run pytest tests/unit/polish/test_routing.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
cd /c/coding/pi-agent-factory-wt/polish
git add src/factory/polish/routing.py tests/unit/polish/test_routing.py
git commit -m "feat(polish): finding -> ledger-task router"
```

---

### Task 3: Reference playground — `ScenarioReplayPlayground`

**Files:**
- Create: `src/factory/polish/reference.py`
- Test: `tests/unit/polish/test_reference.py`

**Interfaces:**
- Consumes: `PlaygroundSession`, `Playground` (Task 1).
- Produces: `ScenarioReplayPlayground(usecases_dir: Path)` implementing the `Playground` protocol. Each `*.json` file in `usecases_dir` is a use case (its stem is the name). `setup(usecase)` returns a `PlaygroundSession` whose single entrypoint is that file's path and whose `describe` names it; a missing use case raises `FileNotFoundError`. `teardown` is a no-op (no live process).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/polish/test_reference.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /c/coding/pi-agent-factory-wt/polish && uv run pytest tests/unit/polish/test_reference.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'factory.polish.reference'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/factory/polish/reference.py`:

```python
from __future__ import annotations

from pathlib import Path

from factory.polish.playground import PlaygroundSession


class ScenarioReplayPlayground:
    """Thin reference Playground: every ``*.json`` in ``usecases_dir`` is a use
    case. ``setup`` points the human at that file to inspect and describe issues;
    there is no live process, so ``teardown`` is a no-op. Decoupled from any
    project — good enough to prove the contract and the routing spine."""

    def __init__(self, usecases_dir: Path) -> None:
        self._dir = usecases_dir

    def list_usecases(self) -> list[str]:
        return sorted(p.stem for p in self._dir.glob("*.json"))

    def setup(self, usecase: str) -> PlaygroundSession:
        path = self._dir / f"{usecase}.json"
        if not path.exists():
            raise FileNotFoundError(f"no such use case: {usecase}")
        return PlaygroundSession(
            entrypoints=[str(path)],
            describe=f"Reference replay of '{usecase}'. Inspect {path.name} and describe any issue.",
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /c/coding/pi-agent-factory-wt/polish && uv run pytest tests/unit/polish/test_reference.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
cd /c/coding/pi-agent-factory-wt/polish
git add src/factory/polish/reference.py tests/unit/polish/test_reference.py
git commit -m "feat(polish): thin reference ScenarioReplayPlayground"
```

---

### Task 4: Per-project playground registry loader

**Files:**
- Create: `src/factory/polish/registry.py`
- Test: `tests/unit/polish/test_registry.py`

**Interfaces:**
- Consumes: `Playground` (Task 1).
- Produces: `load_playgrounds(project_root: Path) -> dict[str, Playground]` — imports `project_root/.factory/registry.py` and returns its `PLAYGROUNDS` dict (`{}` if the file or attribute is absent).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/polish/test_registry.py`:

```python
import pytest
from factory.polish.registry import load_playgrounds

pytestmark = pytest.mark.unit

_REGISTRY = """
from pathlib import Path
from factory.polish.reference import ScenarioReplayPlayground

PLAYGROUNDS = {"ref": ScenarioReplayPlayground(Path(__file__).parent / "usecases")}
"""


def test_missing_registry_returns_empty(tmp_path):
    assert load_playgrounds(tmp_path) == {}


def test_loads_playgrounds(tmp_path):
    fac = tmp_path / ".factory"
    fac.mkdir()
    (fac / "registry.py").write_text(_REGISTRY, encoding="utf-8")
    (fac / "usecases").mkdir()
    (fac / "usecases" / "demo.json").write_text("{}", encoding="utf-8")
    pgs = load_playgrounds(tmp_path)
    assert set(pgs) == {"ref"}
    assert pgs["ref"].list_usecases() == ["demo"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /c/coding/pi-agent-factory-wt/polish && uv run pytest tests/unit/polish/test_registry.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'factory.polish.registry'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/factory/polish/registry.py`:

```python
from __future__ import annotations

import importlib.util
from pathlib import Path

from factory.polish.playground import Playground


def load_playgrounds(project_root: Path) -> dict[str, Playground]:
    reg = project_root / ".factory" / "registry.py"
    if not reg.exists():
        return {}
    spec = importlib.util.spec_from_file_location("_factory_project_registry", reg)
    if spec is None or spec.loader is None:
        return {}
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return dict(getattr(module, "PLAYGROUNDS", {}))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /c/coding/pi-agent-factory-wt/polish && uv run pytest tests/unit/polish/test_registry.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
cd /c/coding/pi-agent-factory-wt/polish
git add src/factory/polish/registry.py tests/unit/polish/test_registry.py
git commit -m "feat(polish): per-project playground registry loader"
```

---

### Task 5: Session orchestration — setup → navigator → route → teardown

**Files:**
- Create: `src/factory/polish/session.py`
- Test: `tests/unit/polish/test_session.py`

**Interfaces:**
- Consumes: `Finding` (Task 1), `Playground`/`PlaygroundSession` (Task 1), `route` (Task 2).
- Produces:
  - `open_navigator(entrypoints: list[str]) -> None` — best-effort spawn of the platform opener per entrypoint (`start` on win32, `open` on darwin, else `xdg-open`); swallows `OSError`.
  - `run_polish_session(playground, usecase, findings, tasks_dir, *, open_nav=None) -> list[Path]` — calls `playground.setup(usecase)`; if `open_nav` is given, calls it with the session entrypoints; routes each finding to a task; and **always** calls `session.teardown()` (in a `finally`). Returns the created task paths.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/polish/test_session.py`:

```python
import pytest
from factory.orchestrator.ledger import load_tasks
from factory.polish import session as session_mod
from factory.polish.finding import Finding
from factory.polish.playground import PlaygroundSession
from factory.polish.session import open_navigator, run_polish_session

pytestmark = pytest.mark.unit


class _FakePlayground:
    def __init__(self, torn):
        self._torn = torn

    def list_usecases(self):
        return ["uc"]

    def setup(self, usecase):
        return PlaygroundSession(
            entrypoints=["http://localhost:3000"],
            describe="d",
            on_teardown=lambda: self._torn.append(usecase),
        )


def test_run_routes_findings_and_tears_down(tmp_path):
    torn, opened = [], []
    pg = _FakePlayground(torn)
    findings = [Finding("uc", "a", sr="SR-001"), Finding("uc", "b")]
    paths = run_polish_session(pg, "uc", findings, tmp_path / "tasks",
                               open_nav=lambda eps: opened.extend(eps))
    assert len(paths) == 2
    assert opened == ["http://localhost:3000"]      # navigator opened with entrypoints
    assert torn == ["uc"]                            # teardown ran
    tasks = load_tasks(tmp_path / "tasks")
    assert [t.satisfies for t in tasks] == [["SR-001"], []]


def test_teardown_runs_even_if_routing_raises(tmp_path):
    torn = []
    pg = _FakePlayground(torn)

    class Boom(Finding):
        pass

    # A tasks_dir that is actually a file makes route() fail on mkdir.
    bad = tmp_path / "afile"
    bad.write_text("x", encoding="utf-8")
    with pytest.raises(OSError):
        run_polish_session(pg, "uc", [Finding("uc", "a")], bad)
    assert torn == ["uc"]                            # teardown still ran


def test_open_navigator_swallows_errors(monkeypatch):
    calls = []
    monkeypatch.setattr(session_mod.subprocess, "Popen",
                        lambda *a, **k: calls.append(a) or (_ for _ in ()).throw(OSError()))
    open_navigator(["http://x"])                     # must not raise
    assert calls  # attempted
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /c/coding/pi-agent-factory-wt/polish && uv run pytest tests/unit/polish/test_session.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'factory.polish.session'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/factory/polish/session.py`:

```python
from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from factory.polish.finding import Finding
from factory.polish.playground import Playground
from factory.polish.routing import route


def open_navigator(entrypoints: list[str]) -> None:
    for ep in entrypoints:
        try:
            if sys.platform == "win32":
                subprocess.Popen(["cmd", "/c", "start", "", ep])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", ep])
            else:
                subprocess.Popen(["xdg-open", ep])
        except OSError:
            pass  # best-effort: opening the navigator must never break the session


def run_polish_session(
    playground: Playground,
    usecase: str,
    findings: list[Finding],
    tasks_dir: Path,
    *,
    open_nav: Callable[[list[str]], None] | None = None,
) -> list[Path]:
    session = playground.setup(usecase)
    try:
        if open_nav is not None:
            open_nav(session.entrypoints)
        return [route(f, tasks_dir) for f in findings]
    finally:
        session.teardown()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /c/coding/pi-agent-factory-wt/polish && uv run pytest tests/unit/polish/test_session.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
cd /c/coding/pi-agent-factory-wt/polish
git add src/factory/polish/session.py tests/unit/polish/test_session.py
git commit -m "feat(polish): session orchestration (setup -> navigator -> route -> teardown)"
```

---

### Task 6: `factory polish` CLI

**Files:**
- Create: `src/factory/polish/cli.py`
- Create: `src/factory/polish/__main__.py`
- Test: `tests/unit/polish/test_cli.py`

**Interfaces:**
- Consumes: `load_playgrounds` (Task 4), `Finding` (Task 1), `run_polish_session`/`open_navigator` (Task 5).
- Produces:
  - `cmd_list(project_root: Path) -> str` — one `"<playground>:<usecase>"` per line across all registered playgrounds (or `"no playgrounds/usecases"`).
  - `cmd_run(project_root, playground_name, usecase, findings_json, tasks_dir, *, open_nav=open_navigator) -> list[Path]` — loads a findings JSON array (`[{"description", "snapshot"?, "sr"?, "artifacts"?}, …]`), builds `Finding`s (each with `usecase`), and runs `run_polish_session`.
  - `main(argv: list[str] | None = None) -> int` — argparse with subcommands `list` and `run`; shared `--project-root` (default `.`) and `--tasks-dir` (default `<project-root>/tasks`) via a parent parser so they are accepted AFTER the subcommand.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/polish/test_cli.py`:

```python
import json
from pathlib import Path

import pytest
from factory.orchestrator.ledger import load_tasks
from factory.polish.cli import cmd_list, cmd_run, main

pytestmark = pytest.mark.unit

_REGISTRY = """
from pathlib import Path
from factory.polish.reference import ScenarioReplayPlayground

PLAYGROUNDS = {"ref": ScenarioReplayPlayground(Path(__file__).parent / "usecases")}
"""


def _project(tmp_path):
    fac = tmp_path / ".factory"
    (fac / "usecases").mkdir(parents=True)
    (fac / "registry.py").write_text(_REGISTRY, encoding="utf-8")
    (fac / "usecases" / "shark_warning.json").write_text("{}", encoding="utf-8")
    return tmp_path


def test_cmd_list(tmp_path):
    _project(tmp_path)
    assert cmd_list(tmp_path) == "ref:shark_warning"


def test_cmd_run_creates_tickets(tmp_path):
    _project(tmp_path)
    findings = tmp_path / "f.json"
    findings.write_text(json.dumps([
        {"description": "ignored swimmer", "snapshot": {"t": 20}, "sr": "SR-001"},
        {"description": "slow response"},
    ]), encoding="utf-8")
    tasks_dir = tmp_path / "tasks"
    paths = cmd_run(tmp_path, "ref", "shark_warning", findings, tasks_dir,
                    open_nav=lambda eps: None)
    assert len(paths) == 2
    tasks = load_tasks(tasks_dir)
    assert [t.satisfies for t in tasks] == [["SR-001"], []]


def test_main_list_exit_code(tmp_path, capsys):
    _project(tmp_path)
    rc = main(["list", "--project-root", str(tmp_path)])
    assert rc == 0
    assert "ref:shark_warning" in capsys.readouterr().out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /c/coding/pi-agent-factory-wt/polish && uv run pytest tests/unit/polish/test_cli.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'factory.polish.cli'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/factory/polish/cli.py`:

```python
from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path

from factory.polish.finding import Finding
from factory.polish.registry import load_playgrounds
from factory.polish.session import open_navigator, run_polish_session


def cmd_list(project_root: Path) -> str:
    lines: list[str] = []
    for name, pg in load_playgrounds(project_root).items():
        lines.extend(f"{name}:{uc}" for uc in pg.list_usecases())
    return "\n".join(lines) if lines else "no playgrounds/usecases"


def cmd_run(
    project_root: Path,
    playground_name: str,
    usecase: str,
    findings_json: Path,
    tasks_dir: Path,
    *,
    open_nav: Callable[[list[str]], None] = open_navigator,
) -> list[Path]:
    playground = load_playgrounds(project_root)[playground_name]
    raw = json.loads(Path(findings_json).read_text(encoding="utf-8"))
    findings = [
        Finding(
            usecase=usecase,
            description=r["description"],
            snapshot=r.get("snapshot", {}),
            sr=r.get("sr"),
            artifacts=r.get("artifacts", []),
        )
        for r in raw
    ]
    return run_polish_session(playground, usecase, findings, tasks_dir, open_nav=open_nav)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="factory-polish")
    sub = parser.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--project-root", default=Path("."), type=Path)
    common.add_argument("--tasks-dir", default=None, type=Path)

    sub.add_parser("list", parents=[common])
    p_run = sub.add_parser("run", parents=[common])
    p_run.add_argument("--playground", required=True)
    p_run.add_argument("--usecase", required=True)
    p_run.add_argument("--from-json", required=True, type=Path)
    args = parser.parse_args(argv)

    tasks_dir = args.tasks_dir or (args.project_root / "tasks")
    if args.cmd == "list":
        print(cmd_list(args.project_root))
    elif args.cmd == "run":
        paths = cmd_run(args.project_root, args.playground, args.usecase, args.from_json, tasks_dir)
        print("\n".join(str(p) for p in paths))
    return 0
```

Create `src/factory/polish/__main__.py`:

```python
from __future__ import annotations

import sys

from factory.polish.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /c/coding/pi-agent-factory-wt/polish && uv run pytest tests/unit/polish/test_cli.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
cd /c/coding/pi-agent-factory-wt/polish
git add src/factory/polish/cli.py src/factory/polish/__main__.py tests/unit/polish/test_cli.py
git commit -m "feat(polish): factory polish CLI (list/run) over the project registry"
```

---

### Task 7: The `polish` conversational skill

**Files:**
- Create: `.pi/skills/polish/SKILL.md`
- Modify: `README.md` (add a short "Polish workflow" note pointing at the skill + CLI)

**Interfaces:**
- No code interface. This task wires the deterministic spine (Tasks 1–6) into a conversational pif session. **Verification is a manual smoke** (below), not a unit test — the skill drives an LLM+human loop.

- [ ] **Step 1: Write the skill**

Create `.pi/skills/polish/SKILL.md`:

```markdown
---
name: polish
description: Run a factory polish session — set up a project use case's playground, gather the human's natural-language feedback, synthesize it into fix-tickets, confirm, and route them to the task ledger.
---

# Polish session

Use this when the human wants to exercise a real use case and turn what they find
into fix-work, without leaving the pi session.

## Steps

1. **Discover.** Run `python -m factory.polish list --project-root <repo>` to list
   `<playground>:<usecase>` options. Help the human pick one (respect an explicit
   `--usecase`).
2. **Set up + open.** The playground's `setup(usecase)` spins up the environment
   and returns `entrypoints`; open the navigator to them (the CLI's `run` path
   calls `open_navigator`, or open them yourself). Tell the human what is running
   and where.
3. **Gather feedback conversationally.** Invite the human to play around and say,
   in their own words, what went wrong. Accumulate every distinct issue. Ask
   clarifying questions; capture reproducible detail (route/steps/state) as a
   `snapshot`, and any screenshots as `artifacts`. If an issue clearly violates a
   known requirement, note its `SR-###`.
4. **Synthesize + confirm.** When the human is done, present a numbered list of
   proposed tickets (title + one-line description + linked `SR-###` if any) and a
   short summary of the actions you will take. Do NOT create anything yet.
5. **Route on confirmation.** Only after the human confirms, write the findings to
   a JSON array and run
   `python -m factory.polish run --project-root <repo> --playground <name> --usecase <uc> --from-json <file>`.
   Report the created `T-###` task paths.
6. **Teardown.** The session tears the environment down automatically; confirm it
   is down before ending.

## Rules

- Nothing is written to the ledger until the human confirms the summarized actions.
- One ticket per distinct issue; if two findings look like duplicates, surface that
  in the confirm step and let the human merge.
- A finding may target the *validation itself* (a requirement's check is hollow),
  not only the implementation — capture that faithfully in the ticket.
```

- [ ] **Step 2: Add the README note**

In `README.md`, add a short section (place it after the existing usage/commands content):

```markdown
## Polish workflow

`factory polish` lets a human exercise a project use case and turn feedback into
fix-tickets. A project declares its playgrounds in `.factory/registry.py`
(`PLAYGROUNDS = {name: Playground}`). Drive it conversationally with the `polish`
skill, or directly:

- `python -m factory.polish list` — list `<playground>:<usecase>` options
- `python -m factory.polish run --playground <name> --usecase <uc> --from-json <findings.json>`
  — route findings to `T-###` tasks
```

- [ ] **Step 3: Manual smoke verification**

Create a throwaway project registry + use case and confirm the round trip:

```bash
cd /c/coding/pi-agent-factory-wt/polish
mkdir -p /tmp/polish_demo/.factory/usecases /tmp/polish_demo/tasks
printf '%s\n' 'from pathlib import Path' \
  'from factory.polish.reference import ScenarioReplayPlayground' \
  'PLAYGROUNDS = {"ref": ScenarioReplayPlayground(Path(__file__).parent / "usecases")}' \
  > /tmp/polish_demo/.factory/registry.py
echo '{}' > /tmp/polish_demo/.factory/usecases/demo.json
echo '[{"description":"button misaligned","sr":"SR-001"}]' > /tmp/polish_demo/f.json
uv run python -m factory.polish list --project-root /tmp/polish_demo
uv run python -m factory.polish run --project-root /tmp/polish_demo --playground ref --usecase demo --from-json /tmp/polish_demo/f.json
```

Expected: `list` prints `ref:demo`; `run` prints a `…/tasks/T-001.md` path; that file parses as a task with `satisfies: [SR-001]`.

- [ ] **Step 4: Commit**

```bash
cd /c/coding/pi-agent-factory-wt/polish
git checkout -- uv.lock 2>/dev/null || true
git add .pi/skills/polish/SKILL.md README.md
git commit -m "feat(polish): conversational polish skill + README note"
```

---

## Final verification

- [ ] Run the polish suite: `cd /c/coding/pi-agent-factory-wt/polish && uv run pytest tests/unit/polish -q` — expected: all green.
- [ ] Full unit suite unaffected: `uv run pytest -q --ignore=tests/gates` — expected: previous total + the new polish tests, all green.
- [ ] Lint + types: `uv run ruff check src/factory/polish tests/unit/polish` and `uv run pyright src/factory/polish` — expected: clean.

## Self-review notes (coverage vs. spec §5–§6, P1 slice)

- `Playground`/`PlaygroundSession` lifecycle contract (spec §5.1) → Task 1.
- `Finding` (spec §5.1) → Task 1.
- finding → bug → fix-task router, `satisfies:` link (spec §6) → Task 2.
- thin reference playground, decoupled (spec §10 P1) → Task 3.
- per-project registry (spec §3) → Task 4.
- session loop setup → navigator → route → teardown (spec §5.2) → Task 5.
- `factory polish` CLI (spec §5.2) → Task 6.
- conversational synthesis + confirm-before-create (spec §5.2, §5.3) → Task 7 (skill; manual).
- **Out of P1 by design:** the automated harness registry + standing regression (spec §8 → Increment 1B); real webapp/drone playgrounds (spec §10 P2/P3); duplicate-finding de-dup (spec §12 open item — the skill surfaces duplicates for the human to merge rather than auto-dedup).
