# Agent Dev Factory — Deterministic Core & Product Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the deterministic substrate of the dev factory — the product interfaces, a `gym-pybullet-drones` flight adapter with a takeoff/hover/land slice, the JSON schemas, their validators, deterministic KB retrieval, and exit-code gate scripts — so a later orchestrator can drive it.

**Architecture:** Pure-Python foundation. Product code lives behind Protocol interfaces (`FlightController`, `Planner`, `Perception`) so a deterministic `Fake` and a real `PyBullet` adapter are interchangeable. Factory machinery is deterministic: JSON-Schema-validated artifacts (context manifest, KB entry, session record), glob/substring KB retrieval with no inference, and gate scripts that return exit codes only. Nothing here calls an LLM.

**Tech Stack:** Python 3.11, `uv` (env/deps), `ruff` (lint/format), `pyright` (types), `pytest` (tests, markers `unit`/`sim`), `jsonschema` (draft 2020-12), `pyyaml` + `python-frontmatter` (KB parsing), `gym-pybullet-drones` (pinned GitHub commit; brings `pybullet`) for sim.

## Global Constraints

- Python **>= 3.11, < 3.13** (floor for 3.11 syntax like `X | None`; capped below 3.13 so the heavy binary deps — pybullet/torch via gym-pybullet-drones — have Windows wheels).
- The sim dependency **`gym-pybullet-drones` is installed from a pinned GitHub commit** (`e712698`), not PyPI (it is unpublished). `uv sync` will pull heavy transitive deps (torch via stable-baselines3); allow a long timeout. If the git dependency genuinely fails to build/install, that is a BLOCKED report, not something to hack around.
- Platform is **Windows 10** + PowerShell; a POSIX `bash` is also available. All gate entrypoints are **Python scripts** (`python scripts/gates/<name>.py`) for cross-platform parity — no `.sh`-only gates.
- **Gates return exit codes only** (0 = pass, non-zero = fail). No gate prints a verdict that a caller must parse; routing is the exit code.
- **KB is append-first.** Retrieval is deterministic (fnmatch globs + substring), never semantic. No hard deletes in this plan.
- **Schemas are JSON Schema draft 2020-12**, stored as `.schema.json` files so both Python (now) and a future TS orchestrator can validate against the same files.
- **Interfaces are `typing.Protocol`**, `@runtime_checkable`, so adapters are structurally typed and `isinstance`-checkable in tests.
- Every task ends green (`ruff`, `pyright`, and its tests) and is committed.

---

## File Structure

```
pyproject.toml                              # deps, ruff/pyright/pytest config
.gitignore
src/factory/
  __init__.py
  stores.py                                 # canonical store paths + helpers
  schemas/
    context_manifest.schema.json
    kb_entry.schema.json
    session_record.schema.json
  validation/
    __init__.py
    schema_validator.py                     # validate(obj, schema_path) -> list[str]
    manifest_validator.py                   # schema + path referential integrity
    session_validator.py
    kb_validator.py
  kb/
    __init__.py
    retrieval.py                            # select_entries(touched, signatures) -> list[str]
    index.py                                # build_index() -> writes kb/index.json
src/drone/
  __init__.py
  interfaces.py                             # Pose, Detection, Command, 3 Protocols
  fake_flight_controller.py                 # deterministic kinematic fake
  pybullet_flight_controller.py             # gym-pybullet-drones adapter
  scenarios/
    __init__.py
    takeoff_hover_land.py                   # ScenarioResult + runner
scripts/gates/
  _proc.py                                  # run_and_propagate(cmd) helper
  lint.py  types.py  unit.py  sim_smoke.py  # thin tool wrappers
  validate_manifest.py  validate_session.py  validate_kb.py   # CLI validators
tests/unit/ ...                             # one test module per unit above
tests/sim/test_takeoff_hover_land.py        # marker: sim
tests/gates/test_validator_cli.py           # fixtures -> exit codes
kb/kb-0001-pybullet-arming.md               # seeded entry
tasks/.gitkeep  context-manifests/.gitkeep  sessions/.gitkeep
```

---

### Task 1: Project scaffolding & tooling

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `src/factory/__init__.py`, `src/drone/__init__.py`
- Create: `tasks/.gitkeep`, `context-manifests/.gitkeep`, `sessions/.gitkeep`
- Test: `tests/unit/test_smoke.py`

**Interfaces:**
- Consumes: nothing.
- Produces: a working `uv` env; `ruff`, `pyright`, `pytest` all runnable; package import path `factory` / `drone`.

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "cool-physical-ai-project"
version = "0.0.1"
requires-python = ">=3.11,<3.13"
dependencies = [
  "jsonschema>=4.21",
  "pyyaml>=6.0",
  "python-frontmatter>=1.1",
  "numpy>=2.2",
  "gym-pybullet-drones @ git+https://github.com/utiasDSL/gym-pybullet-drones.git@e712698a05a80728b06572819dcf044596707754",
]

[dependency-groups]
dev = ["ruff>=0.6", "pyright>=1.1.380", "pytest>=8.0"]

[tool.setuptools.packages.find]
where = ["src"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = ["unit: fast deterministic tests", "sim: pybullet simulation tests"]
addopts = "-m unit"

[tool.ruff]
line-length = 100
src = ["src", "tests", "scripts"]

[tool.pyright]
include = ["src", "scripts"]
pythonVersion = "3.11"
typeCheckingMode = "standard"
```

- [ ] **Step 2: Write `.gitignore`**

```gitignore
__pycache__/
*.pyc
.venv/
.pytest_cache/
.ruff_cache/
```

- [ ] **Step 3: Create empty package files and store placeholders**

Create empty `src/factory/__init__.py`, `src/drone/__init__.py`, and empty `.gitkeep` files in `tasks/`, `context-manifests/`, `sessions/`.

- [ ] **Step 4: Write the smoke test**

```python
# tests/unit/test_smoke.py
import pytest

pytestmark = pytest.mark.unit


def test_packages_import():
    import factory  # noqa: F401
    import drone  # noqa: F401
```

- [ ] **Step 5: Create env and run everything**

```bash
uv sync
uv run ruff check .
uv run pyright
uv run pytest
```
Expected: `ruff` clean, `pyright` 0 errors, pytest `1 passed`.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .gitignore src tests tasks context-manifests sessions
git commit -m "chore: scaffold factory core project and tooling"
```

---

### Task 2: Product interfaces + deterministic FakeFlightController

**Files:**
- Create: `src/drone/interfaces.py`, `src/drone/fake_flight_controller.py`
- Test: `tests/unit/test_fake_flight_controller.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `Pose(x: float, y: float, z: float, yaw: float)` — frozen dataclass.
  - `Detection(bearing_deg: float, range_m: float, confidence: float, label: str)` — frozen dataclass.
  - `Command(kind: str, args: dict[str, float])` — frozen dataclass.
  - `FlightController` Protocol: `arm() -> None`, `takeoff(altitude_m: float) -> None`, `goto(x: float, y: float, z: float) -> None`, `land() -> None`, `step(dt: float) -> None`, `get_pose() -> Pose`, `get_battery() -> float`, `close() -> None`.
  - `Perception` Protocol: `get_detections() -> list[Detection]`.
  - `Planner` Protocol: `decide(pose: Pose, detections: list[Detection]) -> Command`.
  - `FakeFlightController` implementing `FlightController` deterministically.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_fake_flight_controller.py
import pytest
from drone.interfaces import FlightController, Pose
from drone.fake_flight_controller import FakeFlightController

pytestmark = pytest.mark.unit


def test_fake_is_flight_controller():
    fc = FakeFlightController()
    assert isinstance(fc, FlightController)


def test_takeoff_then_step_climbs_toward_target():
    fc = FakeFlightController(climb_rate=1.0, battery_drain=0.01)
    fc.arm()
    fc.takeoff(2.0)
    for _ in range(3):
        fc.step(1.0)
    pose = fc.get_pose()
    assert pose.z == pytest.approx(2.0)  # clamped at target
    assert fc.get_battery() == pytest.approx(1.0 - 0.03)


def test_land_returns_to_ground():
    fc = FakeFlightController(climb_rate=1.0)
    fc.arm()
    fc.takeoff(2.0)
    fc.step(5.0)
    fc.land()
    fc.step(5.0)
    assert fc.get_pose().z == pytest.approx(0.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_fake_flight_controller.py -v`
Expected: FAIL — `ModuleNotFoundError: drone.interfaces`.

- [ ] **Step 3: Write `src/drone/interfaces.py`**

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Pose:
    x: float
    y: float
    z: float
    yaw: float


@dataclass(frozen=True)
class Detection:
    bearing_deg: float
    range_m: float
    confidence: float
    label: str


@dataclass(frozen=True)
class Command:
    kind: str
    args: dict[str, float] = field(default_factory=dict)


@runtime_checkable
class FlightController(Protocol):
    def arm(self) -> None: ...
    def takeoff(self, altitude_m: float) -> None: ...
    def goto(self, x: float, y: float, z: float) -> None: ...
    def land(self) -> None: ...
    def step(self, dt: float) -> None: ...
    def get_pose(self) -> Pose: ...
    def get_battery(self) -> float: ...
    def close(self) -> None: ...


@runtime_checkable
class Perception(Protocol):
    def get_detections(self) -> list[Detection]: ...


@runtime_checkable
class Planner(Protocol):
    def decide(self, pose: Pose, detections: list[Detection]) -> Command: ...
```

- [ ] **Step 4: Write `src/drone/fake_flight_controller.py`**

```python
from __future__ import annotations

from drone.interfaces import Pose


class FakeFlightController:
    """Deterministic kinematic stand-in for a FlightController.

    Position moves toward the active target at a fixed rate per simulated
    second; battery drains linearly. No randomness — same inputs, same output.
    """

    def __init__(self, climb_rate: float = 1.0, battery_drain: float = 0.01) -> None:
        self._climb_rate = climb_rate
        self._battery_drain = battery_drain
        self._pose = Pose(0.0, 0.0, 0.0, 0.0)
        self._target_z = 0.0
        self._battery = 1.0
        self._armed = False

    def arm(self) -> None:
        self._armed = True

    def takeoff(self, altitude_m: float) -> None:
        self._target_z = altitude_m

    def goto(self, x: float, y: float, z: float) -> None:
        self._pose = Pose(x, y, self._pose.z, self._pose.yaw)
        self._target_z = z

    def land(self) -> None:
        self._target_z = 0.0

    def step(self, dt: float) -> None:
        dz = self._target_z - self._pose.z
        max_step = self._climb_rate * dt
        move = max(-max_step, min(max_step, dz))
        self._pose = Pose(self._pose.x, self._pose.y, self._pose.z + move, self._pose.yaw)
        self._battery = max(0.0, self._battery - self._battery_drain * dt)

    def get_pose(self) -> Pose:
        return self._pose

    def get_battery(self) -> float:
        return self._battery

    def close(self) -> None:
        pass
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_fake_flight_controller.py -v`
Expected: 3 passed. Then `uv run ruff check . && uv run pyright`.

- [ ] **Step 6: Commit**

```bash
git add src/drone/interfaces.py src/drone/fake_flight_controller.py tests/unit/test_fake_flight_controller.py
git commit -m "feat: add drone interfaces and deterministic fake flight controller"
```

---

### Task 3: Takeoff/hover/land scenario + PyBullet adapter (sim slice)

**Files:**
- Create: `src/drone/scenarios/__init__.py`, `src/drone/scenarios/takeoff_hover_land.py`
- Create: `src/drone/pybullet_flight_controller.py`
- Test: `tests/unit/test_takeoff_hover_land_fake.py`, `tests/sim/test_takeoff_hover_land.py`

**Interfaces:**
- Consumes: `FlightController`, `Pose` (Task 2).
- Produces:
  - `ScenarioResult(max_altitude: float, final_altitude: float, battery_start: float, battery_end: float)` — frozen dataclass.
  - `run_takeoff_hover_land(fc: FlightController, *, target_alt: float = 1.0, hover_steps: int = 20, dt: float = 0.05) -> ScenarioResult`.
  - `PyBulletFlightController` implementing `FlightController`.

- [ ] **Step 1: Write the failing deterministic (fake) test**

```python
# tests/unit/test_takeoff_hover_land_fake.py
import pytest
from drone.fake_flight_controller import FakeFlightController
from drone.scenarios.takeoff_hover_land import run_takeoff_hover_land, ScenarioResult

pytestmark = pytest.mark.unit


def test_scenario_against_fake_is_deterministic():
    fc = FakeFlightController(climb_rate=10.0, battery_drain=0.001)
    result = run_takeoff_hover_land(fc, target_alt=1.0, hover_steps=10, dt=0.1)
    assert isinstance(result, ScenarioResult)
    assert result.max_altitude == pytest.approx(1.0)
    assert result.final_altitude == pytest.approx(0.0)
    assert result.battery_end < result.battery_start
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_takeoff_hover_land_fake.py -v`
Expected: FAIL — module `drone.scenarios.takeoff_hover_land` missing.

- [ ] **Step 3: Implement the scenario**

```python
# src/drone/scenarios/takeoff_hover_land.py
from __future__ import annotations

from dataclasses import dataclass

from drone.interfaces import FlightController


@dataclass(frozen=True)
class ScenarioResult:
    max_altitude: float
    final_altitude: float
    battery_start: float
    battery_end: float


def run_takeoff_hover_land(
    fc: FlightController,
    *,
    target_alt: float = 1.0,
    hover_steps: int = 20,
    dt: float = 0.05,
) -> ScenarioResult:
    """Arm, climb to target_alt, hover, land. Records altitude envelope."""
    battery_start = fc.get_battery()
    fc.arm()
    fc.takeoff(target_alt)
    max_alt = 0.0

    # climb + hover
    for _ in range(hover_steps):
        fc.step(dt)
        max_alt = max(max_alt, fc.get_pose().z)

    # land
    fc.land()
    for _ in range(hover_steps):
        fc.step(dt)
        max_alt = max(max_alt, fc.get_pose().z)

    return ScenarioResult(
        max_altitude=max_alt,
        final_altitude=fc.get_pose().z,
        battery_start=battery_start,
        battery_end=fc.get_battery(),
    )
```
Create empty `src/drone/scenarios/__init__.py`.

- [ ] **Step 4: Run the fake test to pass**

Run: `uv run pytest tests/unit/test_takeoff_hover_land_fake.py -v`
Expected: 1 passed.

- [ ] **Step 5: Implement the PyBullet adapter**

```python
# src/drone/pybullet_flight_controller.py
from __future__ import annotations

import numpy as np
from gym_pybullet_drones.envs.CtrlAviary import CtrlAviary
from gym_pybullet_drones.control.DSLPIDControl import DSLPIDControl
from gym_pybullet_drones.utils.enums import DroneModel, Physics

from drone.interfaces import Pose


class PyBulletFlightController:
    """FlightController backed by gym-pybullet-drones (headless, single drone)."""

    def __init__(self, *, gui: bool = False, battery_drain: float = 0.0005) -> None:
        self._env = CtrlAviary(
            drone_model=DroneModel.CF2X,
            num_drones=1,
            physics=Physics.PYB,
            pyb_freq=240,
            ctrl_freq=48,
            gui=gui,
        )
        self._ctrl = DSLPIDControl(drone_model=DroneModel.CF2X)
        self._obs, _ = self._env.reset()
        self._target = np.array([0.0, 0.0, 0.0])
        self._battery = 1.0
        self._battery_drain = battery_drain

    def _state(self) -> np.ndarray:
        return self._obs[0]

    def arm(self) -> None:
        pass  # gym-pybullet-drones has no arm gate; kept for interface parity

    def takeoff(self, altitude_m: float) -> None:
        s = self._state()
        self._target = np.array([s[0], s[1], altitude_m])

    def goto(self, x: float, y: float, z: float) -> None:
        self._target = np.array([x, y, z])

    def land(self) -> None:
        s = self._state()
        self._target = np.array([s[0], s[1], 0.0])

    def step(self, dt: float) -> None:
        state = self._state()
        action, _, _ = self._ctrl.computeControlFromState(
            control_timestep=self._env.CTRL_TIMESTEP,
            state=state,
            target_pos=self._target,
        )
        self._obs, _, _, _, _ = self._env.step(action.reshape(1, 4))
        self._battery = max(0.0, self._battery - self._battery_drain)

    def get_pose(self) -> Pose:
        s = self._state()
        return Pose(x=float(s[0]), y=float(s[1]), z=float(s[2]), yaw=float(s[9]))

    def get_battery(self) -> float:
        return self._battery

    def close(self) -> None:
        self._env.close()
```

> Note: gym-pybullet-drones' exact `computeControlFromState` return arity can vary by version. If the unpack fails, run `uv run python -c "from gym_pybullet_drones.control.DSLPIDControl import DSLPIDControl; help(DSLPIDControl.computeControlFromState)"` and adjust the unpack to match — the action array is the first element.

- [ ] **Step 6: Write the sim test (tolerant bounds, marked `sim`)**

```python
# tests/sim/test_takeoff_hover_land.py
import pytest
from drone.pybullet_flight_controller import PyBulletFlightController
from drone.scenarios.takeoff_hover_land import run_takeoff_hover_land

pytestmark = pytest.mark.sim


def test_pybullet_takeoff_hover_land():
    fc = PyBulletFlightController(gui=False)
    try:
        result = run_takeoff_hover_land(fc, target_alt=1.0, hover_steps=120, dt=1 / 48)
    finally:
        fc.close()
    # Tolerant: real controller overshoots/settles. Assert it climbed then came down.
    assert result.max_altitude > 0.6
    assert result.final_altitude < 0.3
    assert result.battery_end < result.battery_start
```

- [ ] **Step 7: Run both suites**

Run: `uv run pytest tests/unit/test_takeoff_hover_land_fake.py -v` → passed.
Run: `uv run pytest -m sim tests/sim/test_takeoff_hover_land.py -v` → passed (first run downloads no assets; headless).
Then `uv run ruff check . && uv run pyright`.

- [ ] **Step 8: Commit**

```bash
git add src/drone/scenarios src/drone/pybullet_flight_controller.py tests/unit/test_takeoff_hover_land_fake.py tests/sim/test_takeoff_hover_land.py
git commit -m "feat: takeoff/hover/land scenario with fake and pybullet flight controllers"
```

---

### Task 4: JSON schemas + generic schema validator

**Files:**
- Create: `src/factory/schemas/context_manifest.schema.json`, `src/factory/schemas/kb_entry.schema.json`, `src/factory/schemas/session_record.schema.json`
- Create: `src/factory/validation/__init__.py`, `src/factory/validation/schema_validator.py`
- Test: `tests/unit/test_schema_validator.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `validate(instance: dict, schema_path: Path | str) -> list[str]` — returns a list of human-readable error strings (empty = valid). `SCHEMA_DIR: Path` constant pointing at `src/factory/schemas`.

- [ ] **Step 1: Write the three schema files**

`src/factory/schemas/context_manifest.schema.json`:
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["task_id", "generated_by", "generated_at", "coherence", "context"],
  "properties": {
    "task_id": {"type": "string", "pattern": "^T-[0-9]+$"},
    "generated_by": {"const": "context-gatherer"},
    "generated_at": {"type": "string", "format": "date-time"},
    "coherence": {
      "type": "object",
      "required": ["proven", "checks"],
      "properties": {
        "proven": {"type": "boolean"},
        "checks": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["name", "pass"],
            "properties": {
              "name": {"type": "string"},
              "pass": {"type": "boolean"},
              "evidence": {"type": "string"}
            }
          }
        }
      }
    },
    "context": {
      "type": "object",
      "required": ["task", "source_files", "skills"],
      "properties": {
        "spec": {"type": "array", "items": {"type": "string"}},
        "plan": {"type": "array", "items": {"type": "string"}},
        "task": {"type": "string"},
        "prior_session": {"type": ["string", "null"]},
        "source_files": {"type": "array", "items": {"type": "string"}},
        "kb_entries": {"type": "array", "items": {"type": "string"}},
        "skills": {"type": "array", "items": {"type": "string"}}
      }
    },
    "reject": {"type": ["object", "null"]}
  }
}
```

`src/factory/schemas/kb_entry.schema.json`:
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["id", "title", "status", "severity", "tags", "scope"],
  "properties": {
    "id": {"type": "string", "pattern": "^kb-[0-9]{4}$"},
    "title": {"type": "string", "minLength": 1},
    "status": {"enum": ["active", "superseded", "archived"]},
    "severity": {"enum": ["high", "medium", "low"]},
    "created": {"type": "string"},
    "last_seen": {"type": "string"},
    "occurrences": {"type": "integer", "minimum": 1},
    "tags": {"type": "array", "items": {"type": "string"}},
    "scope": {
      "type": "object",
      "required": ["files"],
      "properties": {
        "files": {"type": "array", "items": {"type": "string"}},
        "error_signatures": {"type": "array", "items": {"type": "string"}}
      }
    },
    "detection": {"type": "string"}
  }
}
```

`src/factory/schemas/session_record.schema.json`:
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["session_id", "started_at", "model_backend", "tasks"],
  "properties": {
    "session_id": {"type": "string"},
    "started_at": {"type": "string", "format": "date-time"},
    "ended_at": {"type": ["string", "null"]},
    "model_backend": {"type": "string"},
    "git": {"type": "object"},
    "tasks": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["task_id", "outcome", "nodes"],
        "properties": {
          "task_id": {"type": "string", "pattern": "^T-[0-9]+$"},
          "title": {"type": "string"},
          "outcome": {"enum": ["completed", "rejected", "escalated"]},
          "iterations": {"type": "integer", "minimum": 0},
          "nodes": {"type": "array", "items": {"type": "object", "required": ["node", "result"]}},
          "commits": {"type": "array", "items": {"type": "string"}},
          "dod": {"type": "object"}
        }
      }
    },
    "kb_changes": {"type": "object"},
    "escalations": {"type": "array"},
    "resume": {"type": "object"}
  }
}
```

- [ ] **Step 2: Write the failing test**

```python
# tests/unit/test_schema_validator.py
import pytest
from factory.validation.schema_validator import validate, SCHEMA_DIR

pytestmark = pytest.mark.unit

MANIFEST = SCHEMA_DIR / "context_manifest.schema.json"


def test_valid_manifest_passes():
    obj = {
        "task_id": "T-001",
        "generated_by": "context-gatherer",
        "generated_at": "2026-07-16T14:32:10Z",
        "coherence": {"proven": True, "checks": [{"name": "x", "pass": True}]},
        "context": {"task": "tasks/T-001.md", "source_files": [], "skills": []},
        "reject": None,
    }
    assert validate(obj, MANIFEST) == []


def test_missing_required_field_reports_error():
    obj = {"task_id": "T-001"}
    errors = validate(obj, MANIFEST)
    assert errors  # non-empty


def test_bad_task_id_pattern_reports_error():
    obj = {
        "task_id": "001",
        "generated_by": "context-gatherer",
        "generated_at": "2026-07-16T14:32:10Z",
        "coherence": {"proven": True, "checks": []},
        "context": {"task": "t", "source_files": [], "skills": []},
    }
    assert any("task_id" in e for e in validate(obj, MANIFEST))
```

- [ ] **Step 3: Run to verify it fails**

Run: `uv run pytest tests/unit/test_schema_validator.py -v`
Expected: FAIL — `factory.validation.schema_validator` missing.

- [ ] **Step 4: Implement the validator**

```python
# src/factory/validation/schema_validator.py
from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schemas"


def validate(instance: dict, schema_path: Path | str) -> list[str]:
    """Validate `instance` against the JSON schema at `schema_path`.

    Returns a list of human-readable error strings; empty means valid.
    """
    schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.path))
    return [f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}" for e in errors]
```
Create empty `src/factory/validation/__init__.py`.

- [ ] **Step 5: Run tests to pass**

Run: `uv run pytest tests/unit/test_schema_validator.py -v` → 3 passed.
Then `uv run ruff check . && uv run pyright`.

- [ ] **Step 6: Commit**

```bash
git add src/factory/schemas src/factory/validation tests/unit/test_schema_validator.py
git commit -m "feat: add JSON schemas and generic schema validator"
```

---

### Task 5: Manifest validator with referential integrity

**Files:**
- Create: `src/factory/validation/manifest_validator.py`
- Test: `tests/unit/test_manifest_validator.py`

**Interfaces:**
- Consumes: `validate`, `SCHEMA_DIR` (Task 4).
- Produces: `validate_manifest(manifest: dict, repo_root: Path) -> list[str]` — schema errors PLUS, when `coherence.proven` is true, an error for every path in `context.task`, `context.source_files`, `context.spec`, `context.plan`, `context.prior_session` that does not exist under `repo_root` (path portion before any `#` anchor).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_manifest_validator.py
import pytest
from factory.validation.manifest_validator import validate_manifest

pytestmark = pytest.mark.unit


def _manifest(tmp_path, **ctx):
    (tmp_path / "tasks").mkdir()
    (tmp_path / "tasks" / "T-001.md").write_text("dod", encoding="utf-8")
    base = {
        "task_id": "T-001",
        "generated_by": "context-gatherer",
        "generated_at": "2026-07-16T14:32:10Z",
        "coherence": {"proven": True, "checks": [{"name": "x", "pass": True}]},
        "context": {"task": "tasks/T-001.md", "source_files": [], "skills": []},
        "reject": None,
    }
    base["context"].update(ctx)
    return base


def test_valid_manifest_with_existing_paths(tmp_path):
    assert validate_manifest(_manifest(tmp_path), tmp_path) == []


def test_missing_source_file_reports_error(tmp_path):
    m = _manifest(tmp_path, source_files=["src/does_not_exist.py"])
    errors = validate_manifest(m, tmp_path)
    assert any("does_not_exist" in e for e in errors)


def test_anchor_is_stripped_before_existence_check(tmp_path):
    (tmp_path / "spec.md").write_text("x", encoding="utf-8")
    m = _manifest(tmp_path, spec=["spec.md#section"])
    assert validate_manifest(m, tmp_path) == []


def test_unproven_manifest_skips_path_checks(tmp_path):
    m = _manifest(tmp_path, source_files=["nope.py"])
    m["coherence"]["proven"] = False
    # schema still ok; path checks skipped when not proven
    assert validate_manifest(m, tmp_path) == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_manifest_validator.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

```python
# src/factory/validation/manifest_validator.py
from __future__ import annotations

from pathlib import Path

from factory.validation.schema_validator import SCHEMA_DIR, validate

_SCHEMA = SCHEMA_DIR / "context_manifest.schema.json"


def _strip_anchor(ref: str) -> str:
    return ref.split("#", 1)[0]


def validate_manifest(manifest: dict, repo_root: Path) -> list[str]:
    errors = validate(manifest, _SCHEMA)
    if errors:
        return errors

    coherence = manifest.get("coherence", {})
    if not coherence.get("proven"):
        return []

    ctx = manifest.get("context", {})
    refs: list[str] = []
    if ctx.get("task"):
        refs.append(ctx["task"])
    if ctx.get("prior_session"):
        refs.append(ctx["prior_session"])
    for key in ("source_files", "spec", "plan"):
        refs.extend(ctx.get(key, []))

    missing: list[str] = []
    for ref in refs:
        rel = _strip_anchor(ref)
        if not (repo_root / rel).exists():
            missing.append(f"context path missing: {rel}")
    return missing
```

- [ ] **Step 4: Run to pass**

Run: `uv run pytest tests/unit/test_manifest_validator.py -v` → 4 passed. Then `ruff` + `pyright`.

- [ ] **Step 5: Commit**

```bash
git add src/factory/validation/manifest_validator.py tests/unit/test_manifest_validator.py
git commit -m "feat: manifest validator with path referential integrity"
```

---

### Task 6: Session record validator

**Files:**
- Create: `src/factory/validation/session_validator.py`
- Test: `tests/unit/test_session_validator.py`

**Interfaces:**
- Consumes: `validate`, `SCHEMA_DIR` (Task 4).
- Produces: `validate_session(record: dict) -> list[str]` — schema errors PLUS a semantic check: every task with `outcome == "completed"` must have a `dod` object whose `met` is `true`; otherwise an error `task <id>: completed but dod.met is not true`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_session_validator.py
import pytest
from factory.validation.session_validator import validate_session

pytestmark = pytest.mark.unit


def _record(**task_over):
    task = {"task_id": "T-001", "outcome": "completed",
            "nodes": [{"node": "dev", "result": "pass"}],
            "dod": {"met": True}}
    task.update(task_over)
    return {"session_id": "s1", "started_at": "2026-07-16T14:30:00Z",
            "model_backend": "anthropic:claude-opus-4-8", "tasks": [task]}


def test_valid_session_passes():
    assert validate_session(_record()) == []


def test_completed_without_dod_met_fails():
    errors = validate_session(_record(dod={"met": False}))
    assert any("dod.met" in e for e in errors)


def test_escalated_task_needs_no_dod():
    assert validate_session(_record(outcome="escalated", dod={})) == []


def test_schema_violation_reported():
    bad = _record()
    bad["tasks"][0]["outcome"] = "banana"
    assert validate_session(bad)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_session_validator.py -v` → FAIL (module missing).

- [ ] **Step 3: Implement**

```python
# src/factory/validation/session_validator.py
from __future__ import annotations

from factory.validation.schema_validator import SCHEMA_DIR, validate

_SCHEMA = SCHEMA_DIR / "session_record.schema.json"


def validate_session(record: dict) -> list[str]:
    errors = validate(record, _SCHEMA)
    if errors:
        return errors

    semantic: list[str] = []
    for task in record.get("tasks", []):
        if task.get("outcome") == "completed":
            dod = task.get("dod") or {}
            if dod.get("met") is not True:
                semantic.append(f"task {task.get('task_id')}: completed but dod.met is not true")
    return semantic
```

- [ ] **Step 4: Run to pass**

Run: `uv run pytest tests/unit/test_session_validator.py -v` → 4 passed. Then `ruff` + `pyright`.

- [ ] **Step 5: Commit**

```bash
git add src/factory/validation/session_validator.py tests/unit/test_session_validator.py
git commit -m "feat: session record validator with dod semantic check"
```

---

### Task 7: KB entry validator + seeded entry

**Files:**
- Create: `src/factory/validation/kb_validator.py`, `kb/kb-0001-pybullet-arming.md`
- Test: `tests/unit/test_kb_validator.py`

**Interfaces:**
- Consumes: `validate`, `SCHEMA_DIR` (Task 4).
- Produces:
  - `parse_entry(path: Path) -> dict` — reads a Markdown file, returns its YAML frontmatter as a dict (via `python-frontmatter`).
  - `validate_entry_file(path: Path) -> list[str]` — schema errors for the frontmatter PLUS an error if the filename stem does not start with the `id`.

- [ ] **Step 1: Write the seeded KB entry**

`kb/kb-0001-pybullet-arming.md`:
```markdown
---
id: kb-0001
title: "PyBullet drone: goto before settle reads stale pose"
status: active
severity: medium
created: 2026-07-16
last_seen: 2026-07-16
occurrences: 1
tags: [pybullet, flight-controller, sim]
scope:
  files: ["src/drone/pybullet_flight_controller.py", "src/drone/scenarios/**"]
  error_signatures:
    - "max_altitude"
    - "final_altitude"
detection: ""
---

## Symptom
Sim assertions on altitude flake when hover_steps is too small to let the PID settle.

## Root cause
`computeControlFromState` needs enough control steps to converge on target_pos.

## Rule / fix
Give takeoff/hover at least ~120 control steps at ctrl_freq=48 before asserting.
```

- [ ] **Step 2: Write the failing test**

```python
# tests/unit/test_kb_validator.py
import pytest
from pathlib import Path
from factory.validation.kb_validator import parse_entry, validate_entry_file

pytestmark = pytest.mark.unit

KB_DIR = Path(__file__).resolve().parents[2] / "kb"


def test_seeded_entry_parses_and_validates():
    path = KB_DIR / "kb-0001-pybullet-arming.md"
    data = parse_entry(path)
    assert data["id"] == "kb-0001"
    assert validate_entry_file(path) == []


def test_filename_id_mismatch_reported(tmp_path):
    p = tmp_path / "kb-9999-wrong.md"
    p.write_text(
        "---\nid: kb-0002\ntitle: t\nstatus: active\nseverity: low\n"
        "tags: []\nscope:\n  files: []\n---\nbody\n",
        encoding="utf-8",
    )
    assert any("filename" in e for e in validate_entry_file(p))


def test_bad_status_enum_reported(tmp_path):
    p = tmp_path / "kb-0003-x.md"
    p.write_text(
        "---\nid: kb-0003\ntitle: t\nstatus: nope\nseverity: low\n"
        "tags: []\nscope:\n  files: []\n---\nbody\n",
        encoding="utf-8",
    )
    assert validate_entry_file(p)
```

- [ ] **Step 3: Run to verify it fails**

Run: `uv run pytest tests/unit/test_kb_validator.py -v` → FAIL (module missing).

- [ ] **Step 4: Implement**

```python
# src/factory/validation/kb_validator.py
from __future__ import annotations

from pathlib import Path

import frontmatter

from factory.validation.schema_validator import SCHEMA_DIR, validate

_SCHEMA = SCHEMA_DIR / "kb_entry.schema.json"


def parse_entry(path: Path) -> dict:
    post = frontmatter.load(str(path))
    return dict(post.metadata)


def validate_entry_file(path: Path) -> list[str]:
    data = parse_entry(path)
    errors = validate(data, _SCHEMA)
    entry_id = data.get("id")
    if isinstance(entry_id, str) and not Path(path).stem.startswith(entry_id):
        errors.append(f"filename {Path(path).name} does not start with id {entry_id}")
    return errors
```

- [ ] **Step 5: Run to pass**

Run: `uv run pytest tests/unit/test_kb_validator.py -v` → 3 passed. Then `ruff` + `pyright`.

- [ ] **Step 6: Commit**

```bash
git add src/factory/validation/kb_validator.py kb/kb-0001-pybullet-arming.md tests/unit/test_kb_validator.py
git commit -m "feat: kb entry validator and seeded knowledge base entry"
```

---

### Task 8: Deterministic KB retrieval + index generator

**Files:**
- Create: `src/factory/kb/__init__.py`, `src/factory/kb/retrieval.py`, `src/factory/kb/index.py`
- Test: `tests/unit/test_kb_retrieval.py`, `tests/unit/test_kb_index.py`

**Interfaces:**
- Consumes: `parse_entry` (Task 7).
- Produces:
  - `select_entries(kb_dir: Path, touched_files: list[str], signatures: list[str]) -> list[str]` — returns sorted `id`s of **active** entries where any `scope.files` glob (fnmatch) matches any touched file, OR any `scope.error_signatures` substring appears in any provided signature. Deterministic; no inference.
  - `build_index(kb_dir: Path) -> dict` — returns `{id: {files, error_signatures, tags, status}}` and writes it to `kb_dir / "index.json"`.

- [ ] **Step 1: Write failing retrieval test**

```python
# tests/unit/test_kb_retrieval.py
import pytest
from pathlib import Path
from factory.kb.retrieval import select_entries

pytestmark = pytest.mark.unit

KB_DIR = Path(__file__).resolve().parents[2] / "kb"


def test_matches_by_file_glob():
    ids = select_entries(KB_DIR, ["src/drone/pybullet_flight_controller.py"], [])
    assert "kb-0001" in ids


def test_matches_by_signature_substring():
    ids = select_entries(KB_DIR, [], ["AssertionError: max_altitude > 0.6"])
    assert "kb-0001" in ids


def test_no_match_returns_empty():
    assert select_entries(KB_DIR, ["src/unrelated/thing.py"], ["totally other"]) == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_kb_retrieval.py -v` → FAIL (module missing).

- [ ] **Step 3: Implement retrieval**

```python
# src/factory/kb/retrieval.py
from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path

from factory.validation.kb_validator import parse_entry


def _iter_entries(kb_dir: Path):
    for path in sorted(kb_dir.glob("kb-*.md")):
        yield parse_entry(path)


def select_entries(kb_dir: Path, touched_files: list[str], signatures: list[str]) -> list[str]:
    hits: set[str] = set()
    for entry in _iter_entries(kb_dir):
        if entry.get("status") != "active":
            continue
        scope = entry.get("scope", {})
        globs = scope.get("files", [])
        sigs = scope.get("error_signatures", [])

        file_hit = any(fnmatch(tf, g) for tf in touched_files for g in globs)
        sig_hit = any(s in provided for s in sigs for provided in signatures)

        if file_hit or sig_hit:
            hits.add(str(entry["id"]))
    return sorted(hits)
```
Create empty `src/factory/kb/__init__.py`.

- [ ] **Step 4: Run retrieval test to pass**

Run: `uv run pytest tests/unit/test_kb_retrieval.py -v` → 3 passed.

- [ ] **Step 5: Write failing index test**

```python
# tests/unit/test_kb_index.py
import json
import shutil
import pytest
from pathlib import Path
from factory.kb.index import build_index

pytestmark = pytest.mark.unit

SRC_KB = Path(__file__).resolve().parents[2] / "kb"


def test_build_index_writes_file(tmp_path):
    shutil.copy(SRC_KB / "kb-0001-pybullet-arming.md", tmp_path / "kb-0001-pybullet-arming.md")
    idx = build_index(tmp_path)
    assert "kb-0001" in idx
    assert idx["kb-0001"]["status"] == "active"
    written = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    assert written == idx
```

- [ ] **Step 6: Run to verify it fails**

Run: `uv run pytest tests/unit/test_kb_index.py -v` → FAIL (module missing).

- [ ] **Step 7: Implement index**

```python
# src/factory/kb/index.py
from __future__ import annotations

import json
from pathlib import Path

from factory.validation.kb_validator import parse_entry


def build_index(kb_dir: Path) -> dict:
    index: dict[str, dict] = {}
    for path in sorted(kb_dir.glob("kb-*.md")):
        e = parse_entry(path)
        scope = e.get("scope", {})
        index[str(e["id"])] = {
            "files": scope.get("files", []),
            "error_signatures": scope.get("error_signatures", []),
            "tags": e.get("tags", []),
            "status": e.get("status"),
        }
    (kb_dir / "index.json").write_text(
        json.dumps(index, indent=2, sort_keys=True), encoding="utf-8"
    )
    return index
```

- [ ] **Step 8: Run to pass, then regenerate the real index**

Run: `uv run pytest tests/unit/test_kb_index.py -v` → 1 passed.
Run: `uv run python -c "from pathlib import Path; from factory.kb.index import build_index; build_index(Path('kb'))"`
Then `uv run ruff check . && uv run pyright`.

- [ ] **Step 9: Commit**

```bash
git add src/factory/kb tests/unit/test_kb_retrieval.py tests/unit/test_kb_index.py kb/index.json
git commit -m "feat: deterministic kb retrieval and index generator"
```

---

### Task 9: Tool gate scripts (lint/types/unit/sim) + exit-code helper

**Files:**
- Create: `scripts/gates/_proc.py`, `scripts/gates/lint.py`, `scripts/gates/types.py`, `scripts/gates/unit.py`, `scripts/gates/sim_smoke.py`
- Test: `tests/gates/test_proc.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `run_and_propagate(cmd: list[str]) -> int` in `_proc.py` — runs `cmd` via `subprocess.run`, returns its return code. Each gate script's `if __name__ == "__main__":` calls `sys.exit(run_and_propagate([...]))`.

- [ ] **Step 1: Write the failing test**

```python
# tests/gates/test_proc.py
import sys
import pytest

sys.path.insert(0, "scripts/gates")
from _proc import run_and_propagate  # noqa: E402

pytestmark = pytest.mark.unit


def test_zero_exit_propagates():
    assert run_and_propagate([sys.executable, "-c", "raise SystemExit(0)"]) == 0


def test_nonzero_exit_propagates():
    assert run_and_propagate([sys.executable, "-c", "raise SystemExit(3)"]) == 3
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/gates/test_proc.py -v` → FAIL (`_proc` missing).

- [ ] **Step 3: Implement `_proc.py`**

```python
# scripts/gates/_proc.py
from __future__ import annotations

import subprocess


def run_and_propagate(cmd: list[str]) -> int:
    """Run cmd, stream its output, return its exit code. No parsing of stdout."""
    return subprocess.run(cmd, check=False).returncode
```

- [ ] **Step 4: Write the four gate scripts**

```python
# scripts/gates/lint.py
import sys
from _proc import run_and_propagate

if __name__ == "__main__":
    sys.exit(run_and_propagate(["ruff", "check", "."]))
```

```python
# scripts/gates/types.py
import sys
from _proc import run_and_propagate

if __name__ == "__main__":
    sys.exit(run_and_propagate(["pyright"]))
```

```python
# scripts/gates/unit.py
import sys
from _proc import run_and_propagate

if __name__ == "__main__":
    sys.exit(run_and_propagate(["pytest", "-m", "unit", "-q"]))
```

```python
# scripts/gates/sim_smoke.py
import sys
from _proc import run_and_propagate

if __name__ == "__main__":
    sys.exit(run_and_propagate(["pytest", "-m", "sim", "-q"]))
```

- [ ] **Step 5: Run the helper test to pass and smoke the gates**

Run: `uv run pytest tests/gates/test_proc.py -v` → 2 passed.
Run: `uv run python scripts/gates/lint.py; echo "exit=$?"` → exit=0.
Run: `uv run python scripts/gates/unit.py; echo "exit=$?"` → exit=0.
Then `uv run ruff check . && uv run pyright`.

- [ ] **Step 6: Commit**

```bash
git add scripts/gates/_proc.py scripts/gates/lint.py scripts/gates/types.py scripts/gates/unit.py scripts/gates/sim_smoke.py tests/gates/test_proc.py
git commit -m "feat: tool gate scripts with exit-code propagation"
```

---

### Task 10: Validator CLI gates (manifest/session/kb)

**Files:**
- Create: `scripts/gates/validate_manifest.py`, `scripts/gates/validate_session.py`, `scripts/gates/validate_kb.py`
- Test: `tests/gates/test_validator_cli.py`

**Interfaces:**
- Consumes: `validate_manifest` (Task 5), `validate_session` (Task 6), `validate_entry_file` (Task 7).
- Produces: three CLI scripts, each taking a file path argument, printing errors to stderr, exiting `0` if valid and `1` otherwise. `validate_manifest.py <manifest.json>` uses the current working directory as `repo_root`.

- [ ] **Step 1: Write the failing test**

```python
# tests/gates/test_validator_cli.py
import json
import subprocess
import sys
import pytest

pytestmark = pytest.mark.unit


def _run(script, arg, cwd=None):
    return subprocess.run(
        [sys.executable, f"scripts/gates/{script}", str(arg)],
        cwd=cwd, capture_output=True, text=True,
    ).returncode


def test_valid_session_exits_zero(tmp_path):
    rec = {"session_id": "s1", "started_at": "2026-07-16T14:30:00Z",
           "model_backend": "anthropic:claude-opus-4-8",
           "tasks": [{"task_id": "T-001", "outcome": "escalated",
                      "nodes": [{"node": "dev", "result": "pass"}]}]}
    f = tmp_path / "s.json"
    f.write_text(json.dumps(rec), encoding="utf-8")
    assert _run("validate_session.py", f) == 0


def test_invalid_session_exits_one(tmp_path):
    f = tmp_path / "bad.json"
    f.write_text(json.dumps({"session_id": "s1"}), encoding="utf-8")
    assert _run("validate_session.py", f) == 1


def test_valid_kb_entry_exits_zero():
    assert _run("validate_kb.py", "kb/kb-0001-pybullet-arming.md") == 0
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/gates/test_validator_cli.py -v` → FAIL (scripts missing).

- [ ] **Step 3: Implement the three CLIs**

```python
# scripts/gates/validate_manifest.py
import json
import sys
from pathlib import Path

from factory.validation.manifest_validator import validate_manifest

if __name__ == "__main__":
    manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    errors = validate_manifest(manifest, Path.cwd())
    for e in errors:
        print(e, file=sys.stderr)
    sys.exit(1 if errors else 0)
```

```python
# scripts/gates/validate_session.py
import json
import sys
from pathlib import Path

from factory.validation.session_validator import validate_session

if __name__ == "__main__":
    record = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    errors = validate_session(record)
    for e in errors:
        print(e, file=sys.stderr)
    sys.exit(1 if errors else 0)
```

```python
# scripts/gates/validate_kb.py
import sys
from pathlib import Path

from factory.validation.kb_validator import validate_entry_file

if __name__ == "__main__":
    errors = validate_entry_file(Path(sys.argv[1]))
    for e in errors:
        print(e, file=sys.stderr)
    sys.exit(1 if errors else 0)
```

> These import `factory.*`, so run them through the project env (`uv run python scripts/gates/validate_session.py ...`). The test invokes them with `sys.executable` under `uv run`, so the installed `factory` package is importable.

- [ ] **Step 4: Run to pass**

Run: `uv run pytest tests/gates/test_validator_cli.py -v` → 3 passed. Then `ruff` + `pyright`.

- [ ] **Step 5: Commit**

```bash
git add scripts/gates/validate_manifest.py scripts/gates/validate_session.py scripts/gates/validate_kb.py tests/gates/test_validator_cli.py
git commit -m "feat: validator CLI gates for manifest, session, and kb"
```

---

### Task 11: Full-gate runner + README

**Files:**
- Create: `scripts/gates/all.py`, `README.md`
- Test: `tests/gates/test_all_gate.py`

**Interfaces:**
- Consumes: `run_and_propagate` (Task 9).
- Produces: `scripts/gates/all.py` runs lint, types, and unit gates in order, stops at the first non-zero, and exits with that code (sim excluded — it is opt-in and slower). Returns 0 only if all pass.

- [ ] **Step 1: Write the failing test**

```python
# tests/gates/test_all_gate.py
import subprocess
import sys
import pytest

pytestmark = pytest.mark.unit


def test_all_gate_passes_on_clean_repo():
    rc = subprocess.run([sys.executable, "scripts/gates/all.py"]).returncode
    assert rc == 0
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/gates/test_all_gate.py -v` → FAIL (`all.py` missing).

- [ ] **Step 3: Implement the runner**

```python
# scripts/gates/all.py
import sys
from _proc import run_and_propagate

GATES = [
    ["ruff", "check", "."],
    ["pyright"],
    ["pytest", "-m", "unit", "-q"],
]

if __name__ == "__main__":
    for cmd in GATES:
        code = run_and_propagate(cmd)
        if code != 0:
            sys.exit(code)
    sys.exit(0)
```

- [ ] **Step 4: Write `README.md`**

```markdown
# Cool Physical AI Project — Dev Factory Core

Deterministic substrate for the agent dev factory (see
`docs/superpowers/specs/2026-07-16-deterministic-agent-dev-factory-design.md`).

## Setup
```
uv sync
```

## Gates (exit-code only)
```
uv run python scripts/gates/all.py        # lint + types + unit
uv run python scripts/gates/sim_smoke.py  # pybullet sim tests (slower)
uv run python scripts/gates/validate_manifest.py <manifest.json>
uv run python scripts/gates/validate_session.py <session.json>
uv run python scripts/gates/validate_kb.py <kb/kb-XXXX-*.md>
```

## Layout
- `src/drone/` — flight interfaces, fake + pybullet controllers, scenarios
- `src/factory/` — schemas, validators, deterministic KB retrieval
- `kb/` — knowledge base (append-first); `index.json` is generated
- `tasks/`, `context-manifests/`, `sessions/` — factory stores
```

- [ ] **Step 5: Run to pass**

Run: `uv run pytest tests/gates/test_all_gate.py -v` → 1 passed.
Run: `uv run python scripts/gates/all.py; echo "exit=$?"` → exit=0.

- [ ] **Step 6: Commit**

```bash
git add scripts/gates/all.py README.md tests/gates/test_all_gate.py
git commit -m "feat: aggregate gate runner and project README"
```

---

## Self-Review

**Spec coverage (against `2026-07-16-deterministic-agent-dev-factory-design.md`):**
- §4 stores (`tasks/`, `context-manifests/`, `sessions/`, `kb/`) → Task 1 + Task 8.
- §5 gate concept (exit-code routing) → Tasks 9–11 (all exit-code only).
- §6 product-domain skeleton (`flight-controller-iface`, `sim-harness`) → Tasks 2–3.
- §7 context manifest schema + referential integrity → Tasks 4–5.
- §8 KB schema + deterministic glob/substring retrieval + index + append-first → Tasks 7–8.
- §9 session record schema + resume-critical fields + dod semantic → Tasks 4, 6.
- §11 takeoff/hover/land co-bootstrap slice → Task 3.
- **Deferred to Plan 2 (orchestrator), explicitly out of scope here:** the agent nodes, context injection, routing state machine, circuit breakers, session/KB *writing* during runs, Pi integration, model backend. This plan builds only the deterministic pieces those depend on.

**Placeholder scan:** none — every step ships runnable code or an exact command.

**Type consistency:** `FlightController`/`Pose`/`Detection`/`Command` defined in Task 2 and consumed unchanged in Tasks 3; `validate`/`SCHEMA_DIR` from Task 4 used in Tasks 5–7; `parse_entry` from Task 7 used in Task 8; `run_and_propagate` from Task 9 used in Tasks 9 & 11. Names match across tasks.

**Known risk flagged inline:** gym-pybullet-drones' `computeControlFromState` return arity varies by version (Task 3, Step 5 note); the sim test uses tolerant bounds to stay deterministic-enough.
