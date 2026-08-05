# Project-Configurable Validation Gates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let each project declare its own validation gates in `.factory/factory.yaml`, so `factory-run` can go green in a repo that isn't the factory.

**Architecture:** `FactoryConfig`/`load_config` move from `factory.polish.config` to a neutral `factory.config` and gain a `gates` field (`dict[str, list[GateStep]]`); `factory.polish.config` re-exports them so its existing callers are untouched. A new `ConfigGateRunner` implements the existing `GateRunner` protocol (`run(name) -> int`) from those steps, and replaces `SubprocessGateRunner`, which is deleted along with the `scripts/gates/*.py` shims it invoked. Nodes, `runner.py`, the evidence connector and `FakeGateRunner` are all unchanged — only construction changes.

**Tech Stack:** Python 3.12, `pytest`, `ruff`, `pyright`, `pyyaml`, stdlib `subprocess`.

## Global Constraints

- Reuse verbatim, do NOT redefine: the `GateRunner` Protocol `run(self, name: str) -> int` (`factory.orchestrator.backends`); `FakeGateRunner`; `FactoryConfig`, `load_config`, `UnknownTypeError`, `PLAYGROUND_TYPES`, `HARNESS_TYPES` (`factory.polish.config`, moving in Task 1).
- Gate names are the fixed vocabulary the pipeline already calls: `unit`, `sim`, `integration`, `full`. Do NOT add project-defined names.
- `factory/config.py` must NOT import `factory.polish.*` or `factory.validation.*` at module level — the orchestrator imports it, and a module-level import would re-create the layering inversion this move exists to remove. Use function-local imports inside `load_config`.
- `load_config` must NOT raise when `gates:` is absent — `factory/validation/pipeline.py`, `factory/polish/cli.py` and several test fixtures call it with playground-only YAML. Absent `gates:` parses to `{}`; the "must declare gates" error belongs where the gate runner is built (Task 3).
- `{python}` in a `cmd` expands to `sys.executable` and is the ONLY substitution. `_proc.py` used `sys.executable` deliberately so tools resolve from the venv when PATH lacks its `Scripts/` dir.
- Exit code `5` from any step is a PASS ("no tests collected"), recorded in the log.
- An undeclared gate passes and is recorded as skipped.
- Repo: `C:/coding/pi-agent-factory` (work in the existing worktree). Task 5 edits `C:/coding/markdown_pdf_system`.

---

### Task 1: `factory.config` — neutral config module with gates

**Files:**
- Create: `src/factory/config.py`
- Modify: `src/factory/polish/config.py` (becomes a re-export shim)
- Test: `tests/unit/test_config.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `GateStep(cmd: str, cwd: str | None = None)` (frozen dataclass); `FactoryConfig(playgrounds: dict[str, Playground], harnesses: dict[str, Harness], gates: dict[str, list[GateStep]])`; `load_config(project_root: Path) -> FactoryConfig`; `UnknownTypeError`; `GateConfigError(ValueError)`. Used by Tasks 2, 3, 4.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_config.py
from pathlib import Path

import pytest

from factory.config import FactoryConfig, GateConfigError, GateStep, load_config

pytestmark = pytest.mark.unit


def _write(tmp_path: Path, body: str) -> Path:
    (tmp_path / ".factory").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".factory" / "factory.yaml").write_text(body, encoding="utf-8")
    return tmp_path


def test_parses_gate_steps_in_order_with_cwd(tmp_path):
    root = _write(tmp_path, """
gates:
  unit:
    - { cmd: "pytest -q", cwd: backend }
    - { cmd: "npm test", cwd: frontend }
""")
    cfg = load_config(root)
    assert cfg.gates["unit"] == [
        GateStep(cmd="pytest -q", cwd="backend"),
        GateStep(cmd="npm test", cwd="frontend"),
    ]


def test_cwd_is_optional(tmp_path):
    root = _write(tmp_path, 'gates:\n  full:\n    - { cmd: "ruff check ." }\n')
    assert load_config(root).gates["full"] == [GateStep(cmd="ruff check .", cwd=None)]


def test_absent_gates_section_parses_to_empty_not_an_error(tmp_path):
    # validation/pipeline.py and polish/cli.py call load_config on repos that
    # declare only playgrounds; requiring gates here would break them.
    root = _write(tmp_path, "playgrounds: {}\n")
    assert load_config(root).gates == {}


def test_missing_config_file_is_empty_config(tmp_path):
    cfg = load_config(tmp_path)
    assert cfg == FactoryConfig({}, {}, {})


def test_step_without_cmd_names_the_gate(tmp_path):
    root = _write(tmp_path, 'gates:\n  unit:\n    - { cwd: backend }\n')
    with pytest.raises(GateConfigError, match="unit"):
        load_config(root)


def test_gate_that_is_not_a_list_is_rejected(tmp_path):
    root = _write(tmp_path, 'gates:\n  unit: "pytest -q"\n')
    with pytest.raises(GateConfigError, match="unit"):
        load_config(root)


def test_polish_config_still_re_exports(tmp_path):
    # factory.validation.pipeline and factory.polish.cli import from here.
    from factory.polish.config import UnknownTypeError, load_config as polish_load

    assert polish_load(tmp_path) == FactoryConfig({}, {}, {})
    assert UnknownTypeError is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'factory.config'`.

- [ ] **Step 3: Implement `src/factory/config.py`**

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class UnknownTypeError(ValueError):
    pass


class GateConfigError(ValueError):
    pass


@dataclass(frozen=True)
class GateStep:
    cmd: str
    cwd: str | None = None


@dataclass
class FactoryConfig:
    playgrounds: dict[str, Any]
    harnesses: dict[str, Any]
    gates: dict[str, list[GateStep]]


def _build(types: dict, name: str, spec: dict, project_root: Path):
    spec = dict(spec)
    type_name = spec.pop("type", None)
    ctor = types.get(type_name)
    if ctor is None:
        raise UnknownTypeError(f"{name!r}: unknown type {type_name!r} (have {sorted(types)})")
    return ctor(spec, project_root)


def _parse_gates(data: dict) -> dict[str, list[GateStep]]:
    """Absent 'gates:' is {} -- NOT an error. Callers that require gates say so
    themselves (see require_gates); load_config is used by polish and validation
    on repos that declare only playgrounds."""
    gates: dict[str, list[GateStep]] = {}
    for name, steps in (data.get("gates") or {}).items():
        if not isinstance(steps, list):
            raise GateConfigError(
                f"gate {name!r}: expected a list of steps, got {type(steps).__name__}"
            )
        parsed: list[GateStep] = []
        for i, step in enumerate(steps):
            if not isinstance(step, dict) or "cmd" not in step:
                raise GateConfigError(f"gate {name!r} step {i}: each step needs a 'cmd'")
            parsed.append(GateStep(cmd=str(step["cmd"]), cwd=step.get("cwd")))
        gates[name] = parsed
    return gates


def load_config(project_root: Path) -> FactoryConfig:
    path = project_root / ".factory" / "factory.yaml"
    if not path.exists():
        return FactoryConfig({}, {}, {})
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    # Imported here, not at module level: the orchestrator imports this module,
    # and a module-level import of factory.polish would point the core package
    # back at a consumer -- the inversion this move exists to remove.
    from factory.polish.config import HARNESS_TYPES, PLAYGROUND_TYPES

    playgrounds = {
        n: _build(PLAYGROUND_TYPES, n, s, project_root)
        for n, s in (data.get("playgrounds") or {}).items()
    }
    harnesses = {
        n: _build(HARNESS_TYPES, n, s, project_root)
        for n, s in (data.get("harnesses") or {}).items()
    }
    return FactoryConfig(playgrounds, harnesses, _parse_gates(data))
```

- [ ] **Step 4: Rewrite `src/factory/polish/config.py` as a shim keeping the type registries**

```python
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from factory.config import FactoryConfig, GateStep, UnknownTypeError, load_config
from factory.polish.devserver import DevServerPlayground
from factory.polish.playground import Playground
from factory.polish.reference import ScenarioReplayPlayground
from factory.validation.harness import Harness
from factory.validation.playwright_harness import PlaywrightE2EHarness
from factory.validation.sim_harness import SimTestbenchHarness

PLAYGROUND_TYPES: dict[str, Callable[[dict, Path], Playground]] = {
    "dev-server": DevServerPlayground.from_config,
    "scenario-replay": ScenarioReplayPlayground.from_config,
}
HARNESS_TYPES: dict[str, Callable[[dict, Path], Harness]] = {
    "sim-testbench": SimTestbenchHarness.from_config,
    "playwright-e2e": PlaywrightE2EHarness.from_config,
}

# Re-exported so existing importers (factory.validation.pipeline,
# factory.polish.cli, tests) keep working unchanged.
__all__ = ["FactoryConfig", "GateStep", "PLAYGROUND_TYPES", "HARNESS_TYPES",
           "UnknownTypeError", "load_config"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_config.py tests/unit/polish/test_config.py -v`
Expected: PASS (7 new + the existing polish config tests, unchanged).

- [ ] **Step 6: Commit**

```bash
git add src/factory/config.py src/factory/polish/config.py tests/unit/test_config.py
git commit -m "refactor(config): move FactoryConfig to factory.config and add gates"
```

---

### Task 2: `ConfigGateRunner`

**Files:**
- Modify: `src/factory/orchestrator/backends.py` (add the class; leave `SubprocessGateRunner` in place for now — Task 4 deletes it)
- Test: `tests/unit/orchestrator/test_config_gate_runner.py`

**Interfaces:**
- Consumes: `GateStep` (Task 1).
- Produces: `ConfigGateRunner(repo_root: Path, gates: dict[str, list[GateStep]], log_dir: Path | None = None)` implementing the `GateRunner` protocol, with `.run(name) -> int` and `.skipped: list[str]`. Used by Tasks 3 and 4.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/orchestrator/test_config_gate_runner.py
import sys
from pathlib import Path

import pytest

from factory.config import GateStep
from factory.orchestrator.backends import ConfigGateRunner

pytestmark = pytest.mark.unit


def _ok(text: str = "ok") -> GateStep:
    return GateStep(cmd=f'{sys.executable} -c "print(\'{text}\')"')


def _fail(code: int) -> GateStep:
    return GateStep(cmd=f'{sys.executable} -c "import sys; sys.exit({code})"')


def test_runs_steps_in_order_and_passes(tmp_path):
    runner = ConfigGateRunner(tmp_path, {"unit": [_ok("one"), _ok("two")]}, log_dir=tmp_path / "logs")
    assert runner.run("unit") == 0
    log = (tmp_path / "logs" / "unit-gate.log").read_text(encoding="utf-8")
    assert log.index("one") < log.index("two")


def test_first_failure_short_circuits_and_returns_its_code(tmp_path):
    steps = [_fail(3), _ok("never runs")]
    runner = ConfigGateRunner(tmp_path, {"unit": steps}, log_dir=tmp_path / "logs")
    assert runner.run("unit") == 3
    assert "never runs" not in (tmp_path / "logs" / "unit-gate.log").read_text(encoding="utf-8")


def test_undeclared_gate_passes_and_is_recorded_as_skipped(tmp_path):
    runner = ConfigGateRunner(tmp_path, {"unit": [_ok()]}, log_dir=tmp_path / "logs")
    assert runner.run("sim") == 0
    assert runner.skipped == ["sim"]
    assert "not declared" in (tmp_path / "logs" / "sim-gate.log").read_text(encoding="utf-8")


def test_exit_five_is_a_pass_and_is_noted(tmp_path):
    # pytest returns 5 for "no tests collected" -- a declared gate that matches
    # nothing must not be a false red.
    runner = ConfigGateRunner(tmp_path, {"sim": [_fail(5), _ok("still runs")]}, log_dir=tmp_path / "logs")
    assert runner.run("sim") == 0
    log = (tmp_path / "logs" / "sim-gate.log").read_text(encoding="utf-8")
    assert "matched nothing" in log
    assert "still runs" in log


def test_python_placeholder_expands_to_this_interpreter(tmp_path):
    runner = ConfigGateRunner(
        tmp_path, {"unit": [GateStep(cmd='{python} -c "print(1)"')]}, log_dir=tmp_path / "logs"
    )
    assert runner.run("unit") == 0


def test_cwd_is_relative_to_the_repo_root(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "marker.txt").write_text("here", encoding="utf-8")
    step = GateStep(cmd=f'{sys.executable} -c "open(\'marker.txt\')"', cwd="sub")
    runner = ConfigGateRunner(tmp_path, {"unit": [step]}, log_dir=tmp_path / "logs")
    assert runner.run("unit") == 0


def test_without_log_dir_nothing_is_written(tmp_path):
    runner = ConfigGateRunner(tmp_path, {"unit": [_ok()]})
    assert runner.run("unit") == 0
    assert not (tmp_path / "unit-gate.log").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/orchestrator/test_config_gate_runner.py -v`
Expected: FAIL — `ImportError: cannot import name 'ConfigGateRunner'`.

- [ ] **Step 3: Implement — append to `src/factory/orchestrator/backends.py`**

Add `from factory.config import GateStep` to the imports, then:

```python
class ConfigGateRunner:
    """Runs the gate steps a project declares in .factory/factory.yaml.

    An undeclared gate passes and is recorded in .skipped: a webapp has no
    'sim', and forcing it to invent one invites `exit 0` stubs, which are worse
    than an honest skip. Skipped gates are logged so a typo'd key reads as
    'not declared' rather than vanishing.
    """

    # pytest's "no tests collected". A declared gate that matches nothing is a
    # false red -- and it fires the moment a repo split moves tests out.
    _NO_TESTS_COLLECTED = 5

    def __init__(self, repo_root: Path, gates: dict[str, list[GateStep]],
                 log_dir: Path | None = None) -> None:
        self._repo_root = repo_root
        self._gates = gates
        self._log_dir = log_dir
        self.skipped: list[str] = []

    def run(self, name: str) -> int:
        steps = self._gates.get(name)
        if not steps:
            if name not in self.skipped:
                self.skipped.append(name)
            self._write_log(name, f"gate {name!r} is not declared in .factory/factory.yaml; skipped\n")
            return 0

        chunks: list[str] = []
        for step in steps:
            cmd = step.cmd.replace("{python}", sys.executable)
            cwd = self._repo_root / step.cwd if step.cwd else self._repo_root
            if self._log_dir is None:
                rc = subprocess.run(cmd, shell=True, cwd=str(cwd), check=False).returncode
            else:
                proc = subprocess.run(
                    cmd, shell=True, cwd=str(cwd), check=False,
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                )
                chunks.append(f"$ {cmd}\n{proc.stdout or ''}{proc.stderr or ''}")
                rc = proc.returncode
            if rc == self._NO_TESTS_COLLECTED:
                chunks.append(f"[gate] step matched nothing (exit 5), treated as pass: {cmd}\n")
                continue
            if rc != 0:
                self._write_log(name, "".join(chunks))
                return rc
        self._write_log(name, "".join(chunks))
        return 0

    def _write_log(self, name: str, text: str) -> None:
        if self._log_dir is None:
            return
        self._log_dir.mkdir(parents=True, exist_ok=True)
        (self._log_dir / f"{name}-gate.log").write_text(text, encoding="utf-8")
```

- [ ] **Step 4: Run tests + lint/type**

Run: `python -m pytest tests/unit/orchestrator/test_config_gate_runner.py -v && ruff check src/factory/orchestrator/backends.py && pyright src/factory/orchestrator/backends.py`
Expected: PASS (7 tests); clean.

- [ ] **Step 5: Commit**

```bash
git add src/factory/orchestrator/backends.py tests/unit/orchestrator/test_config_gate_runner.py
git commit -m "feat(gates): ConfigGateRunner - run a project's declared gate steps"
```

---

### Task 3: The factory declares its own gates

**Files:**
- Create: `.factory/factory.yaml` (the factory repo has no `.factory/` today)
- Test: `tests/unit/test_factory_own_gates.py`

**Interfaces:**
- Consumes: `load_config` (Task 1).
- Produces: the factory's own gate declaration, and `require_gates(cfg, project_root)` in `src/factory/config.py` raising `GateConfigError` when a project declares no gates at all. Used by Task 4.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_factory_own_gates.py
from pathlib import Path

import pytest

from factory.config import GateConfigError, load_config, require_gates
from factory.paths import factory_root

pytestmark = pytest.mark.unit


def test_the_factory_declares_its_own_gates():
    # The hard-coded scripts/gates map is gone, so the factory eats its own
    # cooking. If this file disappears, the factory silently validates nothing.
    cfg = load_config(factory_root())
    assert "unit" in cfg.gates
    assert "full" in cfg.gates
    assert cfg.gates["unit"], "unit gate must have at least one step"


def test_the_unit_gate_still_ignores_the_all_gate_test():
    # Without --ignore the unit gate recurses into the test that runs the full gate.
    cmds = " ".join(s.cmd for s in load_config(factory_root()).gates["unit"])
    assert "tests/gates/test_all_gate.py" in cmds or "test_all_gate" in cmds


def test_require_gates_rejects_a_project_that_declares_none(tmp_path):
    cfg = load_config(tmp_path)  # no .factory at all
    with pytest.raises(GateConfigError, match="no gates"):
        require_gates(cfg, tmp_path)


def test_require_gates_accepts_a_project_with_gates():
    cfg = load_config(factory_root())
    assert require_gates(cfg, factory_root()) is cfg.gates
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_factory_own_gates.py -v`
Expected: FAIL — `ImportError: cannot import name 'require_gates'` (and, once that exists, the factory has no `.factory/factory.yaml`).

- [ ] **Step 3: Add `require_gates` to `src/factory/config.py`**

```python
def require_gates(cfg: FactoryConfig, project_root: Path) -> dict[str, list[GateStep]]:
    """Gates for a project that must have them, else raise.

    'This project has no sim' and 'this project never said what to check' are
    different statements. An individual gate may be omitted -- it skips -- but a
    project with no gates at all would validate nothing while reporting green.
    """
    if not cfg.gates:
        raise GateConfigError(
            f"{project_root / '.factory' / 'factory.yaml'} declares no gates. "
            "Add a 'gates:' section naming what to run for unit/sim/integration/full; "
            "an individual gate may be omitted and will be skipped."
        )
    return cfg.gates
```

- [ ] **Step 4: Create the factory's `.factory/factory.yaml`**

Commands copied verbatim from `scripts/gates/_proc.py` (`LINT_CMD`, `TYPECHECK_CMD`, `UNIT_CMD`, `AGENT_CMD`) and `sim_smoke.py`:

```yaml
# The factory's own gates. It uses the same mechanism it offers other projects.
gates:
  unit:
    - { cmd: "{python} -m pytest -m unit -q --ignore=tests/gates/test_all_gate.py" }
  sim:
    - { cmd: "{python} -m pytest -m sim -q" }
  integration:
    - { cmd: "{python} -m pytest tests/integration/ -q -m integration" }
  full:
    - { cmd: "{python} -m ruff check ." }
    - { cmd: "{python} -m pyright" }
    - { cmd: "{python} -m pytest -m unit -q --ignore=tests/gates/test_all_gate.py" }
    - { cmd: "{python} -m pytest -m agent -q" }
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_factory_own_gates.py -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add .factory/factory.yaml src/factory/config.py tests/unit/test_factory_own_gates.py
git commit -m "feat(gates): the factory declares its own gates in .factory/factory.yaml"
```

---

### Task 4: Wire it up and retire the hard-coded gate scripts

**Files:**
- Modify: `src/factory/orchestrator/__main__.py:11` (import) and `:83` (construction)
- Modify: `src/factory/orchestrator/backends.py` (delete `SubprocessGateRunner`)
- Modify: `tests/unit/orchestrator/test_backends.py` (drop its `SubprocessGateRunner` tests)
- Modify: `tests/e2e/test_pipeline_transitions_e2e.py:94-98,175` (`_write_gates` writes config, not scripts)
- Modify: `scripts/gates/_proc.py` (trim to `run_and_propagate` only — KEEP the file)
- Modify: `README.md:20`, `.pi/skills/coding-principles/SKILL.md:30`
- Delete: `scripts/gates/{all,unit,sim_smoke,lint,typecheck}.py`
- Delete: `tests/gates/test_all_gate.py`

**Interfaces:**
- Consumes: `ConfigGateRunner` (Task 2), `load_config`/`require_gates` (Tasks 1/3).
- Produces: nothing new — `factory-run` now builds its gate runner from config.

- [ ] **Step 1: Update the e2e workspace helper to write config instead of scripts**

Replace `_write_gates` (currently writes trivial `scripts/gates/*.py` into the temp workspace):

```python
def _write_gates(ws: Path) -> None:
    # Trivial gates that always pass, so the pipeline flows through every stage.
    (ws / ".factory").mkdir(parents=True, exist_ok=True)
    (ws / ".factory" / "factory.yaml").write_text(
        'gates:\n'
        '  unit:\n'
        '    - { cmd: "{python} -c \\"pass\\"" }\n'
        '  sim:\n'
        '    - { cmd: "{python} -c \\"pass\\"" }\n'
        '  integration:\n'
        '    - { cmd: "{python} -c \\"pass\\"" }\n'
        '  full:\n'
        '    - { cmd: "{python} -c \\"pass\\"" }\n',
        encoding="utf-8",
    )
```

and its construction at line ~175:

```python
    gates = ConfigGateRunner(ws, load_config(ws).gates, log_dir=transcript_dir)
```

with imports `from factory.config import load_config` and
`from factory.orchestrator.backends import ConfigGateRunner` replacing the
`SubprocessGateRunner` import.

- [ ] **Step 2: Remove the `SubprocessGateRunner` tests from `tests/unit/orchestrator/test_backends.py`**

Delete the two tests that construct it (around lines 46 and 58) and drop it from the import on line 5, leaving `FakeAgentBackend, FakeGateRunner`. `ConfigGateRunner` is covered by Task 2's file.

- [ ] **Step 3: Wire `__main__.py`**

Replace the import on line 11 and the construction on line 83:

```python
from factory.config import load_config, require_gates
from factory.orchestrator.backends import ConfigGateRunner
```

```python
    gates = ConfigGateRunner(
        repo_root, require_gates(load_config(repo_root), repo_root), log_dir=transcript_dir
    )
```

- [ ] **Step 4: Delete `SubprocessGateRunner` from `src/factory/orchestrator/backends.py`**

Remove the whole class and its `_SCRIPTS` map. Leave `GateRunner`, `FakeGateRunner`, `ConfigGateRunner`, and the agent backends untouched.

- [ ] **Step 5: Delete the retired scripts and their test**

```bash
git rm scripts/gates/all.py scripts/gates/unit.py scripts/gates/sim_smoke.py \
       scripts/gates/lint.py scripts/gates/typecheck.py \
       tests/gates/test_all_gate.py
```

`scripts/gates/{ext,watch_ext,validate_kb,validate_manifest,validate_session}.py` are standalone checks, NOT part of the gate map — leave them.

- [ ] **Step 6: Trim `scripts/gates/_proc.py` — do NOT delete it**

`ext.py:3` and `watch_ext.py:3` both do `from _proc import run_and_propagate`, and `tests/gates/test_proc.py` tests exactly that function. Deleting the file would break two currently-passing gate tests. Delete only the command constants, which now live in `.factory/factory.yaml`:

```python
from __future__ import annotations

import subprocess

# Shared by the standalone gate scripts (ext.py, watch_ext.py). The per-gate
# command lines that used to live here are now declared in .factory/factory.yaml.


def run_and_propagate(cmd: list[str]) -> int:
    """Run cmd, stream its output, return its exit code. No parsing of stdout."""
    return subprocess.run(cmd, check=False).returncode
```

Leave `tests/gates/test_proc.py` unchanged — it only exercises `run_and_propagate`.

- [ ] **Step 7: Update the two docs that name the deleted script**

`README.md:20` — the `full` gate is now declared in config, and there is no CLI subcommand that runs a gate by name (`factory.orchestrator` accepts only `run` and `list`). So document the config as the source of truth and give the direct equivalents:

```
# gate commands are declared in .factory/factory.yaml; run them directly:
uv run ruff check . && uv run pyright && uv run pytest -m unit -q
```

Leave the three `validate_*.py` lines beneath it untouched — those scripts survive.

`.pi/skills/coding-principles/SKILL.md:30` — the REVIEW role reads this at runtime, so it must not describe a deleted file. Replace the parenthetical `(scripts/gates/all.py)` with `(the project's `full` gate, declared in .factory/factory.yaml)`. Leave the rest of that sentence and the surrounding severity-tier text exactly as it is.

- [ ] **Step 6: Run the full suite + lint/type**

Run: `python -m pytest -q && ruff check src scripts tests && pyright src scripts`
Expected: PASS. The previously failing `tests/gates/test_all_gate.py` is gone with the broken `from _proc import` shim it exercised.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat(gates): build the gate runner from config; retire scripts/gates shims"
```

---

### Task 5: Declare CareerOS's gates

**Files:**
- Modify: `C:/coding/markdown_pdf_system/.factory/factory.yaml` (append a `gates:` section beside the existing `playgrounds:` and `harnesses:`)

**Interfaces:**
- Consumes: the config shape from Task 1.
- Produces: the first non-factory project able to reach a green validation.

- [ ] **Step 1: Append the gates section**

```yaml
gates:
  unit:
    - { cmd: "{python} -m pytest -q", cwd: backend }
    - { cmd: "npm test", cwd: frontend }
  integration:
    - { cmd: "npx playwright test", cwd: frontend }
  full:
    - { cmd: "npx tsc --noEmit", cwd: frontend }
    - { cmd: "{python} -m pytest -q", cwd: backend }
```

`sim` is deliberately absent — CareerOS has no simulation, so that gate skips.

- [ ] **Step 2: Verify each gate resolves and runs**

Run from the factory worktree:

```bash
python -c "from pathlib import Path; from factory.config import load_config; \
from factory.orchestrator.backends import ConfigGateRunner; \
r = ConfigGateRunner(Path('C:/coding/markdown_pdf_system'), load_config(Path('C:/coding/markdown_pdf_system')).gates); \
print('unit', r.run('unit')); print('sim', r.run('sim')); print('skipped', r.skipped)"
```

Expected: `sim 0` with `skipped ['sim']`. `unit` runs the real suites — record its exit code; a non-zero here is CareerOS's own test state, not a gate-wiring failure, and must be read before assuming the gate is broken.

- [ ] **Step 3: Commit (in the CareerOS repo)**

```bash
cd /c/coding/markdown_pdf_system
git add .factory/factory.yaml
git commit -m "chore(factory): declare unit/integration/full gates for factory-run"
```

---

## Self-Review

**Spec coverage:**
- §3 config shape (`gates:`, steps, `cwd`, `{python}`) — Task 1 parses it, Task 3 and 5 write it. ✅
- §4 execution semantics (order, short-circuit, shell, cwd, logs, exit 5, skip visibility, `log_dir=None`) — Task 2, one test each. ✅
- §5 components (`factory.config`, `ConfigGateRunner`, `__main__` wiring, `SubprocessGateRunner` deleted, protocol/`FakeGateRunner` untouched) — Tasks 1, 2, 4. ✅
- §4/§6 "no gates section is a hard error" — `require_gates`, Task 3. Deliberately NOT in `load_config`; see Global Constraints. ✅
- §6 migration (factory config, script deletions, `ext`/`validate_*` untouched) — Tasks 3, 4. ✅
- §8 testing (runner behaviours, config parsing, migration guard) — Tasks 1, 2, 3. ✅
- §7 repo split — no task needed; the exit-5 rule (Task 2) is what makes it a non-event, and it is tested.

**Placeholder scan:** no TBD/TODO; every code step is complete and runnable. The one judgement call left to the implementer is Task 5 Step 2's `unit` exit code, which is explicitly explained rather than left vague. ✅

**Type consistency:** `GateStep(cmd, cwd)` identical in Tasks 1, 2, 4, 5; `ConfigGateRunner(repo_root, gates, log_dir)` identical in Tasks 2, 4, 5; `load_config -> FactoryConfig(playgrounds, harnesses, gates)` used consistently; `require_gates(cfg, project_root) -> dict[str, list[GateStep]]` defined in Task 3 and called in Task 4; `.skipped` used in Tasks 2 and 5. `GateConfigError` defined Task 1, raised in Tasks 1 and 3. ✅

**Discovered during planning, folded in:**
- `factory/config.py` must use function-local imports of the type registries, or the orchestrator drags in `factory.polish` and the move achieves nothing.
- `load_config` must not raise on absent `gates:` — `factory/validation/pipeline.py:5`, `factory/polish/cli.py:14` and existing fixtures call it with playground-only YAML.
- `SubprocessGateRunner` has two test-side consumers (`tests/unit/orchestrator/test_backends.py`, `tests/e2e/test_pipeline_transitions_e2e.py`), both handled in Task 4 rather than left to fail.
