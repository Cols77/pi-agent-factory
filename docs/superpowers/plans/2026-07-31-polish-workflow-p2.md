# Polish Workflow — P2 (config-driven registry + webapp playground) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the polish/validation registration **declarative config** (`.factory/factory.yaml`) instead of executed code, add a generic config-driven **`DevServerPlayground`** that launches a project's services + opens a browser with **interrupt-safe teardown**, and wire the `markdown_pdf_system` webapp as the first real playground.

**Architecture:** A project declares `playgrounds:` and `harnesses:` in `.factory/factory.yaml`, each an entry naming a built-in factory **type** + params. A single `load_config(project_root) -> FactoryConfig{playgrounds, harnesses}` builds them from type registries (`PLAYGROUND_TYPES`, `HARNESS_TYPES`), where each type has a `from_config(params, project_root)` constructor. This replaces P1's `registry.py` code-exec (removing the arbitrary-code trust boundary) and supersedes 1A's `default_harness_for`. `DevServerPlayground` is one built-in type; nothing in the factory is tied to project-specific names.

**Tech Stack:** Python 3.11–3.12, stdlib (`subprocess`, `signal`, `atexit`, `urllib`, `socket`, `time`), `pyyaml` (existing dep), `pytest` (`-m unit`).

## Global Constraints

- Python `>=3.11,<3.13`; every new module starts with `from __future__ import annotations`.
- Ruff `line-length = 100`; run `uv run ruff format <files>` before committing so format-check passes.
- Unit tests: `pytestmark = pytest.mark.unit`; run with `uv run pytest` (default `-m unit`).
- `@dataclass(frozen=True)` for value types (`Service`); mutable only where needed.
- **No new dependencies** — stdlib + existing `pyyaml`/`python-frontmatter`.
- **Config, not code:** the per-project registry is `.factory/factory.yaml`. Do NOT reintroduce executing a project's Python. Nothing in `src/factory/` may hardcode a project name, port, or command — those live only in a project's YAML or a test fixture.
- New source under `src/factory/polish/`; tests under `tests/unit/polish/`.
- **Work in the isolated worktree** `C:/coding/pi-agent-factory-wt/p2` on branch `feat/polish-p2`. Prefix commands with `cd /c/coding/pi-agent-factory-wt/p2 && …`. Commit only each task's files; revert `uv.lock` churn (`git checkout -- uv.lock`) before committing.
- Base already contains P1 (`src/factory/polish/{finding,playground,reference,routing,registry,session,cli,__main__}.py`) and 1A (`src/factory/validation/{harness,sim_harness,report,...}.py`).

---

### Task 1: Interrupt-safe teardown in `run_polish_session`

**Files:**
- Modify: `src/factory/polish/session.py`
- Test: `tests/unit/polish/test_session.py` (extend)

**Interfaces:**
- `run_polish_session(playground, usecase, findings, tasks_dir, *, open_nav=None) -> list[Path]` — unchanged signature. Teardown is now idempotent and additionally guarded so it runs on interpreter exit (`atexit`) and on `SIGTERM` (installs a handler that tears down then exits), not only on the normal/in-band-exception path. `SIGKILL` remains uncatchable (documented). Signal install is best-effort (skipped off the main thread).

**Why:** the P1 `try/finally` covers normal completion and in-body exceptions (incl. `KeyboardInterrupt`/SIGINT), but a bare `SIGTERM` or interpreter shutdown would skip it and leak a real playground's dev servers. This is the prerequisite for Task 3's `DevServerPlayground`.

- [ ] **Step 1: Write the failing test** (append to `tests/unit/polish/test_session.py`)

```python
def test_sigterm_handler_tears_down(monkeypatch, tmp_path):
    import signal as signal_mod

    from factory.polish import session as sm

    installed = {}

    def _fake_signal(sig, handler):
        installed[sig] = handler
        return signal_mod.SIG_DFL

    monkeypatch.setattr(sm.signal, "signal", _fake_signal)

    torn = []

    class _PG:
        def list_usecases(self):
            return ["uc"]

        def setup(self, usecase):
            return PlaygroundSession(on_teardown=lambda: torn.append(1))

    # Run a normal session; capture the SIGTERM handler that was installed during it.
    captured = {}

    class _PGCapture(_PG):
        def setup(self, usecase):
            s = super().setup(usecase)
            captured["term"] = installed.get(signal_mod.SIGTERM)
            return s

    sm.run_polish_session(_PGCapture(), "uc", [], tmp_path / "tasks")
    assert torn == [1]                      # normal teardown ran exactly once
    assert callable(captured["term"])       # a SIGTERM handler was installed during the session

    # Invoking that handler must tear down and raise SystemExit.
    torn.clear()
    with pytest.raises(SystemExit):
        captured["term"](signal_mod.SIGTERM, None)
    assert torn == [1]


def test_teardown_registered_and_unregistered_with_atexit(monkeypatch, tmp_path):
    from factory.polish import session as sm

    reg, unreg = [], []
    monkeypatch.setattr(sm.atexit, "register", lambda fn: reg.append(fn) or fn)
    monkeypatch.setattr(sm.atexit, "unregister", lambda fn: unreg.append(fn))

    class _PG:
        def setup(self, usecase):
            return PlaygroundSession(on_teardown=lambda: None)

    sm.run_polish_session(_PG(), "uc", [], tmp_path / "tasks")
    assert reg and unreg and reg[0] is unreg[0]   # registered then cleaned up
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /c/coding/pi-agent-factory-wt/p2 && uv run pytest tests/unit/polish/test_session.py -q`
Expected: FAIL — `run_polish_session` has no `atexit`/`signal` behavior yet (`AttributeError: module ... has no attribute 'atexit'` / SIGTERM handler not installed).

- [ ] **Step 3: Rewrite `src/factory/polish/session.py`**

```python
from __future__ import annotations

import atexit
import signal
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


def _install_sigterm(tear: Callable[[], None]):
    """Install a SIGTERM handler that tears down then exits. Returns the previous
    handler, or None if signals aren't settable here (e.g. not the main thread).
    SIGINT/KeyboardInterrupt is already covered by the caller's finally; SIGKILL
    is uncatchable."""
    def _handler(signum, frame):
        tear()
        raise SystemExit(1)

    try:
        return signal.signal(signal.SIGTERM, _handler)
    except (ValueError, OSError):
        return None


def run_polish_session(
    playground: Playground,
    usecase: str,
    findings: list[Finding],
    tasks_dir: Path,
    *,
    open_nav: Callable[[list[str]], None] | None = None,
) -> list[Path]:
    session = playground.setup(usecase)
    torn = False

    def _tear() -> None:
        nonlocal torn
        if not torn:
            torn = True
            session.teardown()

    atexit.register(_tear)
    prev_term = _install_sigterm(_tear)
    try:
        if open_nav is not None:
            open_nav(session.entrypoints)
        return [route(f, tasks_dir) for f in findings]
    finally:
        _tear()
        if prev_term is not None:
            try:
                signal.signal(signal.SIGTERM, prev_term)
            except (ValueError, OSError):
                pass
        atexit.unregister(_tear)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /c/coding/pi-agent-factory-wt/p2 && uv run pytest tests/unit/polish/test_session.py -q`
Expected: PASS (the 3 original session tests + the 2 new ones).

- [ ] **Step 5: Format + commit**

```bash
cd /c/coding/pi-agent-factory-wt/p2
uv run ruff format src/factory/polish/session.py tests/unit/polish/test_session.py
git checkout -- uv.lock 2>/dev/null || true
git add src/factory/polish/session.py tests/unit/polish/test_session.py
git commit -m "feat(polish): interrupt-safe teardown (atexit + SIGTERM guard)"
```

---

### Task 2: Config-driven registry — `.factory/factory.yaml` (replaces `registry.py` + `default_harness_for`)

**Files:**
- Create: `src/factory/polish/config.py`
- Modify: `src/factory/polish/reference.py` (add `from_config`)
- Modify: `src/factory/validation/sim_harness.py` (add `from_config`)
- Modify: `src/factory/polish/cli.py` (use `load_config(...).playgrounds`)
- Delete: `src/factory/polish/registry.py`
- Create: `tests/unit/polish/test_config.py`
- Delete: `tests/unit/polish/test_registry.py`
- Modify: `tests/unit/polish/test_cli.py` (config fixture instead of `registry.py`)

**Interfaces:**
- `FactoryConfig(playgrounds: dict[str, Playground], harnesses: dict[str, Harness])`
- `load_config(project_root: Path) -> FactoryConfig` — parses `<project_root>/.factory/factory.yaml`; `{}`/`{}` when absent. Builds each entry from `PLAYGROUND_TYPES` / `HARNESS_TYPES` by its `type` key.
- `PLAYGROUND_TYPES: dict[str, Callable[[dict, Path], Playground]]` — starts `{"scenario-replay": ScenarioReplayPlayground.from_config}` (Task 3 adds `"dev-server"`).
- `HARNESS_TYPES: dict[str, Callable[[dict, Path], Harness]]` — `{"sim-testbench": SimTestbenchHarness.from_config}`.
- `UnknownTypeError(ValueError)`.
- `ScenarioReplayPlayground.from_config(params, project_root) -> ScenarioReplayPlayground` (uses `params["usecases_dir"]` relative to `project_root`).
- `SimTestbenchHarness.from_config(params, project_root) -> SimTestbenchHarness` (uses `params["traces_dir"]`).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/polish/test_config.py`:

```python
import pytest
from factory.polish.config import UnknownTypeError, load_config
from factory.polish.reference import ScenarioReplayPlayground
from factory.validation.sim_harness import SimTestbenchHarness

pytestmark = pytest.mark.unit

_YAML = """
playgrounds:
  ref:
    type: scenario-replay
    usecases_dir: validation/traces
harnesses:
  nav:
    type: sim-testbench
    traces_dir: validation/traces
"""


def _project(tmp_path, yaml_text=_YAML):
    fac = tmp_path / ".factory"
    fac.mkdir()
    (fac / "factory.yaml").write_text(yaml_text, encoding="utf-8")
    traces = tmp_path / "validation" / "traces"
    traces.mkdir(parents=True)
    (traces / "demo.json").write_text("{}", encoding="utf-8")
    return tmp_path


def test_missing_config_is_empty(tmp_path):
    cfg = load_config(tmp_path)
    assert cfg.playgrounds == {} and cfg.harnesses == {}


def test_builds_playgrounds_and_harnesses(tmp_path):
    cfg = load_config(_project(tmp_path))
    assert set(cfg.playgrounds) == {"ref"}
    assert isinstance(cfg.playgrounds["ref"], ScenarioReplayPlayground)
    assert cfg.playgrounds["ref"].list_usecases() == ["demo"]
    assert set(cfg.harnesses) == {"nav"}
    assert isinstance(cfg.harnesses["nav"], SimTestbenchHarness)


def test_unknown_type_raises(tmp_path):
    bad = "playgrounds:\n  x:\n    type: nope\n"
    with pytest.raises(UnknownTypeError):
        load_config(_project(tmp_path, bad))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /c/coding/pi-agent-factory-wt/p2 && uv run pytest tests/unit/polish/test_config.py -q`
Expected: FAIL — `No module named 'factory.polish.config'`.

- [ ] **Step 3: Implement**

Add to `src/factory/polish/reference.py` (a classmethod on `ScenarioReplayPlayground`):

```python
    @classmethod
    def from_config(cls, params: dict, project_root: Path) -> "ScenarioReplayPlayground":
        return cls(project_root / params["usecases_dir"])
```

Add to `src/factory/validation/sim_harness.py` (a classmethod on `SimTestbenchHarness`):

```python
    @classmethod
    def from_config(cls, params: dict, project_root: Path) -> "SimTestbenchHarness":
        return cls(project_root / params["traces_dir"])
```

Create `src/factory/polish/config.py`:

```python
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import yaml

from factory.polish.playground import Playground
from factory.polish.reference import ScenarioReplayPlayground
from factory.validation.harness import Harness
from factory.validation.sim_harness import SimTestbenchHarness

PLAYGROUND_TYPES: dict[str, Callable[[dict, Path], Playground]] = {
    "scenario-replay": ScenarioReplayPlayground.from_config,
}
HARNESS_TYPES: dict[str, Callable[[dict, Path], Harness]] = {
    "sim-testbench": SimTestbenchHarness.from_config,
}


class UnknownTypeError(ValueError):
    pass


@dataclass
class FactoryConfig:
    playgrounds: dict[str, Playground]
    harnesses: dict[str, Harness]


def _build(types: dict, name: str, spec: dict, project_root: Path):
    spec = dict(spec)
    type_name = spec.pop("type", None)
    ctor = types.get(type_name)
    if ctor is None:
        raise UnknownTypeError(f"{name!r}: unknown type {type_name!r} (have {sorted(types)})")
    return ctor(spec, project_root)


def load_config(project_root: Path) -> FactoryConfig:
    path = project_root / ".factory" / "factory.yaml"
    if not path.exists():
        return FactoryConfig({}, {})
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    playgrounds = {
        n: _build(PLAYGROUND_TYPES, n, s, project_root)
        for n, s in (data.get("playgrounds") or {}).items()
    }
    harnesses = {
        n: _build(HARNESS_TYPES, n, s, project_root)
        for n, s in (data.get("harnesses") or {}).items()
    }
    return FactoryConfig(playgrounds, harnesses)
```

Update `src/factory/polish/cli.py` — replace the `load_playgrounds` import and its two uses:

```python
from factory.polish.config import load_config
```
In `cmd_list`: `for name, pg in load_config(project_root).playgrounds.items():`
In `cmd_run`: `playground = load_config(project_root).playgrounds[playground_name]`

Delete `src/factory/polish/registry.py` and `tests/unit/polish/test_registry.py`:

```bash
cd /c/coding/pi-agent-factory-wt/p2
git rm src/factory/polish/registry.py tests/unit/polish/test_registry.py
```

Update `tests/unit/polish/test_cli.py` — replace the `_REGISTRY`/`_project` fixture with a YAML one:

```python
_YAML = """
playgrounds:
  ref:
    type: scenario-replay
    usecases_dir: usecases
"""


def _project(tmp_path):
    fac = tmp_path / ".factory"
    (fac / "usecases").mkdir(parents=True)
    (fac / "factory.yaml").write_text(_YAML, encoding="utf-8")
    (fac / "usecases" / "shark_warning.json").write_text("{}", encoding="utf-8")
    return tmp_path
```
(The rest of `test_cli.py` is unchanged — `cmd_list` still returns `"ref:shark_warning"`, `cmd_run` still creates tickets.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /c/coding/pi-agent-factory-wt/p2 && uv run pytest tests/unit/polish -q`
Expected: PASS (config tests green; cli tests green against YAML; no registry tests remain).

- [ ] **Step 5: Format + commit**

```bash
cd /c/coding/pi-agent-factory-wt/p2
uv run ruff format src/factory/polish/config.py src/factory/polish/reference.py src/factory/polish/cli.py src/factory/validation/sim_harness.py tests/unit/polish/test_config.py tests/unit/polish/test_cli.py
git checkout -- uv.lock 2>/dev/null || true
git add -A src/factory/polish src/factory/validation/sim_harness.py tests/unit/polish
git commit -m "feat(polish): config-driven .factory/factory.yaml registry (replaces registry.py code-exec; harnesses too)"
```

---

### Task 3: `DevServerPlayground` + `wait_healthy`

**Files:**
- Create: `src/factory/polish/devserver.py`
- Modify: `src/factory/polish/config.py` (register `"dev-server"` in `PLAYGROUND_TYPES`)
- Test: `tests/unit/polish/test_devserver.py`

**Interfaces:**
- `Service(name: str, cmd: str, cwd: str | None = None, health_url: str | None = None, ready_timeout: float = 30.0)` (frozen).
- `wait_healthy(url: str, timeout: float = 30.0, interval: float = 0.25) -> bool` — polls `url`; any HTTP response (even 4xx) counts as up; `False` on timeout.
- `DevServerPlayground(services, usecases, browse_url, project_root)` implementing `Playground`. `setup(usecase)` spawns each service (`shell=True`, `cwd` relative to `project_root`), waits for its `health_url`, and returns a `PlaygroundSession(entrypoints=[browse_url], on_teardown=<kill all, reverse order>)`; a service that never becomes healthy tears down partial state and raises `RuntimeError`. Kill is terminate→(5s)→kill, best-effort.
- `DevServerPlayground.from_config(params, project_root)` — `services` from `params["services"]` (list of dicts → `Service(**d)`), `usecases` from `params.get("usecases", [])`, `browse_url` from `params["browse_url"]`.
- Registered as `PLAYGROUND_TYPES["dev-server"]`.
- **Note:** process-tree kill (a shell that spawns `node`/`npm` children) is best-effort in P1/P2; full process-group teardown is a documented refinement.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/polish/test_devserver.py`:

```python
import socket
import sys
import time

import pytest
from factory.polish.devserver import DevServerPlayground, Service, wait_healthy
from factory.polish.playground import Playground

pytestmark = pytest.mark.unit


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_is_a_playground(tmp_path):
    pg = DevServerPlayground([], ["u"], "http://x", project_root=tmp_path)
    assert isinstance(pg, Playground)
    assert pg.list_usecases() == ["u"]


def test_setup_starts_service_then_teardown_stops_it(tmp_path):
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    svc = Service(name="web", cmd=f"{sys.executable} -m http.server {port}", health_url=url,
                  ready_timeout=15.0)
    pg = DevServerPlayground([svc], usecases=["u"], browse_url=url, project_root=tmp_path)
    session = pg.setup("u")
    try:
        assert session.entrypoints == [url]
        assert wait_healthy(url, timeout=5)          # server is up
    finally:
        session.teardown()
    # After teardown the port should stop answering within a moment.
    time.sleep(0.5)
    assert wait_healthy(url, timeout=2) is False


def test_setup_raises_and_cleans_up_on_unhealthy(tmp_path):
    dead = f"http://127.0.0.1:{_free_port()}"     # nothing listening
    svc = Service(name="web", cmd=f"{sys.executable} -c \"import time;time.sleep(30)\"",
                  health_url=dead, ready_timeout=1.0)
    pg = DevServerPlayground([svc], usecases=["u"], browse_url=dead, project_root=tmp_path)
    with pytest.raises(RuntimeError):
        pg.setup("u")


def test_from_config(tmp_path):
    port = _free_port()
    params = {
        "browse_url": f"http://127.0.0.1:{port}",
        "usecases": ["a", "b"],
        "services": [{"name": "web", "cmd": "echo hi", "cwd": "sub"}],
    }
    pg = DevServerPlayground.from_config(params, tmp_path)
    assert pg.list_usecases() == ["a", "b"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /c/coding/pi-agent-factory-wt/p2 && uv run pytest tests/unit/polish/test_devserver.py -q`
Expected: FAIL — `No module named 'factory.polish.devserver'`.

- [ ] **Step 3: Implement**

Create `src/factory/polish/devserver.py`:

```python
from __future__ import annotations

import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from factory.polish.playground import PlaygroundSession


@dataclass(frozen=True)
class Service:
    name: str
    cmd: str
    cwd: str | None = None
    health_url: str | None = None
    ready_timeout: float = 30.0


def wait_healthy(url: str, timeout: float = 30.0, interval: float = 0.25) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:  # noqa: S310 (local dev URL)
                if resp.status < 500:
                    return True
        except urllib.error.HTTPError as exc:
            if exc.code < 500:
                return True  # server answered (even 4xx) ⇒ up
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(interval)
    return False


def _kill(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    except OSError:
        pass


class DevServerPlayground:
    """Config-driven playground: launch a project's dev services, wait for each to
    be healthy, open the browser at ``browse_url``, and stop everything on teardown.
    Nothing here is project-specific — services/ports/commands come from config."""

    def __init__(
        self,
        services: list[Service],
        usecases: list[str],
        browse_url: str,
        *,
        project_root: Path,
    ) -> None:
        self._services = services
        self._usecases = usecases
        self._browse_url = browse_url
        self._root = project_root

    @classmethod
    def from_config(cls, params: dict, project_root: Path) -> "DevServerPlayground":
        services = [Service(**s) for s in params.get("services", [])]
        return cls(
            services,
            params.get("usecases", []),
            params["browse_url"],
            project_root=project_root,
        )

    def list_usecases(self) -> list[str]:
        return list(self._usecases)

    def setup(self, usecase: str) -> PlaygroundSession:
        procs: list[subprocess.Popen] = []

        def _teardown() -> None:
            for p in reversed(procs):
                _kill(p)

        try:
            for svc in self._services:
                cwd = self._root / svc.cwd if svc.cwd else self._root
                procs.append(subprocess.Popen(svc.cmd, shell=True, cwd=str(cwd)))
                if svc.health_url and not wait_healthy(svc.health_url, svc.ready_timeout):
                    raise RuntimeError(f"service {svc.name!r} never became healthy at {svc.health_url}")
            return PlaygroundSession(
                entrypoints=[self._browse_url],
                describe=f"Use case '{usecase}': {len(self._services)} service(s) up; browse {self._browse_url}.",
                on_teardown=_teardown,
            )
        except BaseException:
            _teardown()  # clean up partially-started services on any failure/interrupt
            raise
```

Register the type in `src/factory/polish/config.py`:

```python
from factory.polish.devserver import DevServerPlayground
```
and add to `PLAYGROUND_TYPES`:
```python
    "dev-server": DevServerPlayground.from_config,
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /c/coding/pi-agent-factory-wt/p2 && uv run pytest tests/unit/polish/test_devserver.py tests/unit/polish/test_config.py -q`
Expected: PASS (devserver tests spawn a real `http.server` and confirm start/stop; config still builds).

- [ ] **Step 5: Format + commit**

```bash
cd /c/coding/pi-agent-factory-wt/p2
uv run ruff format src/factory/polish/devserver.py src/factory/polish/config.py tests/unit/polish/test_devserver.py
git checkout -- uv.lock 2>/dev/null || true
git add src/factory/polish/devserver.py src/factory/polish/config.py tests/unit/polish/test_devserver.py
git commit -m "feat(polish): generic config-driven DevServerPlayground + wait_healthy"
```

---

### Task 4: Wire `markdown_pdf_system` + update docs + smoke

**Files (in the webapp repo `C:/coding/markdown_pdf_system`, NOT the factory repo):**
- Create: `.factory/factory.yaml`

**Files (factory repo):**
- Modify: `.pi/skills/polish/SKILL.md` (config, not `registry.py`)
- Modify: `README.md` (config, not `registry.py`)

**Interfaces:** none. Verification is a **manual smoke** (launches the real webapp) — not a unit test.

- [ ] **Step 1: Author the webapp config**

In the **webapp repo**, create `.factory/factory.yaml`:

```yaml
playgrounds:
  web:
    type: dev-server
    browse_url: http://localhost:3000
    usecases: [sign-in, tailor-cv, convert-markdown, job-search, chat, profile]
    services:
      - { name: api, cmd: "python -m uvicorn main:app --port 8000", cwd: backend,  health_url: "http://localhost:8000/docs" }
      - { name: ui,  cmd: "npm run dev",                            cwd: frontend, health_url: "http://localhost:3000" }
```

- [ ] **Step 2: Update the factory docs**

In `.pi/skills/polish/SKILL.md`, change the "Discover" step and any `registry.py` references to point at `.factory/factory.yaml`. Replace the discover line with:

```markdown
1. **Discover.** A project declares its playgrounds in `.factory/factory.yaml`.
   Run `python -m factory.polish list --project-root <repo>` to list
   `<playground>:<usecase>` options. Help the human pick one.
```

In `README.md`, update the Polish workflow section's registry sentence:

```markdown
A project declares its playgrounds (and validation harnesses) declaratively in
`.factory/factory.yaml` — each entry names a built-in factory type (`dev-server`,
`scenario-replay`, …) plus params. No project code is executed.
```

- [ ] **Step 3: Manual smoke (real webapp)**

Requires the webapp's toolchain (Node + Python deps installed in `C:/coding/markdown_pdf_system`). Run from the factory worktree so `factory` resolves:

```bash
cd /c/coding/pi-agent-factory-wt/p2
uv run python -m factory.polish list --project-root /c/coding/markdown_pdf_system
# expect: web:sign-in, web:tailor-cv, ... (six lines)

echo '[{"description":"tailor-cv preview is blank on first load","sr":null}]' > /tmp/f.json
uv run python -m factory.polish run --project-root /c/coding/markdown_pdf_system \
  --playground web --usecase tailor-cv --from-json /tmp/f.json \
  --tasks-dir /c/coding/markdown_pdf_system/tasks
```

Expected: both dev servers come up (uvicorn :8000, next :3000), the browser opens to `:3000`, and after the run a `T-###.md` ticket is written under the webapp's `tasks/`. Confirm both server processes are gone afterward (teardown). If a server leaks (npm child processes), note it against the documented process-tree-kill refinement — do not block the task on it, but record it.

- [ ] **Step 4: Commit (factory docs; the webapp config is committed in that repo separately)**

```bash
cd /c/coding/pi-agent-factory-wt/p2
git checkout -- uv.lock 2>/dev/null || true
git add .pi/skills/polish/SKILL.md README.md
git commit -m "docs(polish): config-driven .factory/factory.yaml (skill + README)"
```

Then, in the webapp repo (branch first — do not commit to its default branch):

```bash
cd /c/coding/markdown_pdf_system
git checkout -b feat/factory-polish-playground
git add .factory/factory.yaml
git commit -m "chore: declare factory polish dev-server playground (.factory/factory.yaml)"
```

---

## Final verification

- [ ] Polish suite: `cd /c/coding/pi-agent-factory-wt/p2 && uv run pytest tests/unit/polish -q` — all green.
- [ ] Full unit suite unaffected: `uv run pytest -q --ignore=tests/gates`.
- [ ] Lint + types: `uv run ruff check src/factory/polish` , `uv run ruff format --check src/factory/polish`, `uv run pyright src/factory/polish`.

## Self-review notes (coverage vs. refined design, P2 slice)

- Config file replaces `registry.py` code-exec; one loader builds playgrounds + harnesses from built-in types (design: "config not code", generic) → Task 2.
- Generic `DevServerPlayground`, no project-specific names → Task 3.
- Interrupt-safe teardown (review's P2 blocker) → Task 1.
- `markdown_pdf_system` wired via config only → Task 4.
- Harnesses declarable in config (`sim-testbench` type) → Task 2 (loader builds `cfg.harnesses`); **wiring harnesses into `factory-run` stays Increment 1B** (out of P2).
- **Deferred (unchanged):** P3 drone sim-testbench playground (blocked on sim-testbench T-045/046/047/050); full process-tree kill for `DevServerPlayground` teardown; migrating the drone repo's `validate_requirements.py` off `default_harness_for` onto `.factory/factory.yaml`; `cli.py` friendlier errors (P1 review minor).
