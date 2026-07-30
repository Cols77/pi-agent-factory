# Simulation Testbench Design

> Interactive and replay-based simulation testbench for drone mission scenarios.
> Sea polygon, swim/surf zones, shark/swimmer/surfer detections, with two usecases:
> watch swimmers and warn for shark.

## 1. Purpose

Build a simulation testbench that visualizes drone navigation over a segmented sea
polygon, with simulated detections of sharks, swimmers, and surfers. The testbench
supports:

- **Interactive mode**: real-time pygame window with keyboard controls, live HUD,
  and event injection
- **Replay mode**: headless mission execution with recorded trace, then playback
  or matplotlib post-mission analysis
- **Bug capture**: snapshot a scenario mid-mission with user description, save as
  reproducible YAML, with extensibility point for future requirements tracking
- **Multiple scenarios**: pre-defined YAML scenarios exercising the two usecases

## 2. Architecture

```
SimTestbench
├── Scenario (YAML) ──▶ MissionLoop (existing) ──▶ Recorder (trace)
│                           │
│                           ▼
│                    Simulation Engine
│                    ├── DetectionSpawner (Perception impl)
│                    ├── FakeFlightController (existing)
│                    └── PriorityFilter (existing)
│                           │
│                           ▼
│                    Visualization Layer
│                    ├── PygameRenderer (real-time)
│                    ├── MatplotlibPlotter (post-mission)
│                    └── HUD (overlays, alerts)
│                           │
│                           ▼
│                    Workflow Integration
│                    ├── Scenario Loader/Saver
│                    ├── BugCapture (dialog → YAML)
│                    └── bug_to_task CLI (→ factory task)
```

### 2.1 New package

```
src/sim/
  __init__.py
  testbench.py              # SimTestbench — orchestrates MissionLoop + rendering
  scenario.py               # Scenario dataclass, YAML load/save
  renderer.py               # Pygame rendering (world + HUD)
  plotter.py                # Matplotlib post-mission analysis plots
  detection_spawner.py      # Spawns entities, computes detections from drone pose
  recorder.py               # Mission trace recorder (list of Frames)
  injector.py               # Keyboard event dispatch
  text_input.py             # Text input dialog widget
  hud.py                    # HUD overlay helpers
  bug_capture.py            # Bug snapshot → YAML + factory task integration
  __main__.py               # CLI entry point: python -m sim <scenario.yaml>

scenarios/
  swim_patrol.yaml
  shark_warning.yaml
  multiple_threats.yaml
  false_alarm.yaml
  all_clear.yaml
  bugs/                     # Captured bug scenarios (gitignored except examples)

tests/sim/
  test_detection_spawner.py
  test_scenario.py
  test_recorder.py
```

### 2.2 Existing components used (unchanged)

- `src/drone/mission/loop.py` — MissionLoop
- `src/drone/mission/state.py` — MissionState
- `src/drone/mission/priority_filter.py` — PriorityFilter
- `src/drone/mission/fake_agent.py` — FakeAgent
- `src/drone/navigation/waypoint_sequencer.py` — WaypointSequencer
- `src/drone/navigation/perimeter_sweep.py` — PerimeterSweepAlgorithm
- `src/drone/navigation/registry.py` — NavRegistry
- `src/drone/fake_flight_controller.py` — FakeFlightController
- `src/drone/interfaces.py` — Core types

## 3. Scenario Format (YAML)

```yaml
name: "shark-warning"
description: "Shark detected at low confidence, drone approaches to confirm, warns swimmers"

# Overall sea polygon (closed, CCW order)
sea_polygon:
  vertices: [[0, 0], [100, 0], [120, 80], [60, 120], [-20, 60]]

# Pre-defined zones (offline, loaded at start)
zones:
  - id: "swim-zone"
    label: "swim_area"
    polygon: [[10, 10], [40, 10], [45, 40], [15, 45]]
    color: [0, 200, 255, 80]   # RGBA
  - id: "surf-zone"
    label: "surf_area"
    polygon: [[70, 10], [100, 15], [90, 50], [65, 40]]
    color: [255, 200, 0, 80]

# Drone navigation configuration
navigation:
  algorithm: "perimeter_sweep"
  altitude: 5.0
  offset: 2.0
  max_distance_from_shore: null

# Agent configuration
agent:
  type: "fake"           # "fake" or "llm"
  responses: []          # empty = always "continue" (for interactive mode)

# Detection spawner rules
detections:
  spawners:
    - label: "swimmer"
      pool: "inside_zone(swim-zone)"
      count: 3
      start_time: 0.0
      interval: 5.0          # re-randomize positions every 5s
      speed: 0.5             # m/s drift
    - label: "surfer"
      pool: "inside_zone(surf-zone)"
      count: 2
      start_time: 0.0
      interval: 8.0
      speed: 1.0
    - label: "shark"
      pool: "inside_polygon(sea_polygon)"
      count: 1
      start_time: 15.0       # appears at t=15s
      interval: 0.0          # stationary once spawned
      speed: 2.0

# Priority rules (override default)
priority_rules:
  - label: "shark"
    min_confidence: 0.7
    reason: "shark detected near swimmers"
```

### 3.1 Pool DSL

- `inside_zone(<zone-id>)` — random positions inside the named zone polygon
- `inside_polygon(<name>)` — random positions inside a named polygon (e.g. `sea_polygon`)
- `outside_zone(<zone-id>, <bounds-polygon-name>)` — random positions outside a zone but inside the bounds polygon (e.g. `outside_zone(swim-zone, sea_polygon)`)

### 3.2 Scenario fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Unique scenario name |
| `description` | string | yes | Human-readable description |
| `sea_polygon` | vertices list | yes | Water boundary |
| `zones` | list | no | Pre-defined swim/surf zones |
| `navigation` | dict | yes | Algorithm, altitude, offset |
| `agent` | dict | yes | Agent type and responses |
| `detections.spawners` | list | yes | Entity spawner rules |
| `priority_rules` | list | no | Custom priority filter rules |
| `max_duration` | float | no | Mission timeout (default 300s) |

## 4. Detection Spawner

File: `src/sim/detection_spawner.py`

Implements the `Perception` protocol. On each call to `get_detections()`:

1. Advance each entity's position within its pool region (random walk at configured speed)
2. For each entity, compute distance/range/bearing from the drone's current pose
3. Compute detection confidence: `clamp(1.0 - distance / max_sensor_range, 0.0, 1.0)`
4. Return a `Detection` for each entity with `label`, `confidence`, `bearing`, `range`, `position`
5. Confidence is capped at a per-entity max confidence (e.g. shark starts at 0.4 max until drone is within 30m, then unlocks to 1.0 — enabling the "approach to confirm" pattern)

```python
class DetectionSpawner:
    def __init__(
        self,
        spawners: list[SpawnerRule],
        zones: list[Zone],
        sea_polygon: list[tuple[float, float]],
        max_sensor_range: float = 100.0,
    ) -> None:
        ...

    def get_detections(self) -> list[Detection]:
        """Return current detections, computed from entity positions and drone pose."""
        ...

    def set_drone_pose(self, pose: Pose) -> None:
        """Update drone position for range/bearing computation."""
        ...

    def spawn_entity(self, label: str) -> None:
        """Spawn one additional entity of the given label (for keyboard injection)."""
        ...
```

## 5. Rendering

### 5.1 Pygame Renderer

File: `src/sim/renderer.py`

Draws the simulation world:

- Sea polygon fill (blue gradient or solid)
- Zone polygons (semi-transparent colored fills: swim=cyan, surf=yellow)
- Drone icon (triangle showing heading)
- Entity markers (colored circles: swimmer=blue, surfer=orange, shark=red)
- Detection range rings (faint circles around entities when confidence < threshold)
- Grid lines (optional, for distance reference)
- Event markers (star icons for shark alerts, X icons for warnings)

### 5.2 HUD

File: `src/sim/hud.py`

Drawn as a semi-transparent overlay panel:

```
┌──────────────────────────────────────────────┐
│  MISSION: shark-warning                       │
│  TIME: 023.4s  SPEED: 1×  FPS: 60            │
│  NAV: perimeter_sweep (12/48 waypoints)       │
│  BATTERY: 87%                                 │
│                                              │
│  DETECTIONS:                                 │
│  ● 3 swimmers (in swim zone)                 │
│  ● 2 surfers (in surf zone)                  │
│  ● 1 shark (at 45m, confidence 0.65)         │
│                                              │
│  LAST EVENT: shark detected at 23.4s         │
│  AGENT: investigating target                 │
│                                              │
│  [S]pawn shark  [B]ug capture  [Esc] quit    │
└──────────────────────────────────────────────┘
```

### 5.3 Matplotlib Plotter

File: `src/sim/plotter.py`

After mission completion, generates a three-panel figure:

1. **Top-down map** — sea polygon, zones, drone trajectory (dashed line), detection positions (colored markers), event markers
2. **Detection timeline** — horizontal bar chart showing which detections were active over time, with confidence shading
3. **Confidence vs Range** — scatter plot of confidence vs range for each label, to visualize the distance-based confidence model

Saved to `docs/superpowers/sim-reports/<scenario-name>-<timestamp>.png`.

## 6. Recorder & Replay

File: `src/sim/recorder.py`

```python
@dataclass
class Frame:
    mission_clock: float
    drone_pose: Pose
    detections: list[Detection]
    active_directive: Directive | None
    waypoint_status: dict

class Recorder:
    def __init__(self, record_interval: float = 0.5) -> None: ...
    def record(self, loop: MissionLoop) -> None: ...
    def trace(self) -> list[Frame]: ...
    def save(self, path: str) -> None: ...
    @classmethod
    def load(cls, path: str) -> Recorder: ...
```

For replay mode: load a trace, then step through frames in the renderer at a configurable playback speed.

## 7. Interactive Controls

| Key | Action |
|-----|--------|
| `Space` | Pause / Resume |
| `S` | Spawn a shark at random position |
| `W` | Spawn a swimmer at random position |
| `F` | Spawn a surfer at random position |
| `R` | Reset / Restart scenario |
| `Esc` | Exit to menu or quit |
| `P` | Save screenshot to `screenshots/` |
| `B` | Open bug capture dialog |
| `1` | Speed 1× (realtime) |
| `2` | Speed 2× |
| `3` | Speed 5× |

## 8. Bug Capture

File: `src/sim/bug_capture.py`

When `B` is pressed:
1. Simulation pauses
2. Text input dialog appears (pygame text entry widget)
3. User types a description of what went wrong
4. On Enter, saves a YAML snapshot of the full current scenario state plus user description
5. The `requirements` field is left empty — an extensibility point for the future requirements addon

```yaml
# scenarios/bugs/2026-07-30-shark-no-reaction.yaml
name: "bug-shark-no-reaction"
captured_at: 45.2
user_description: "The drone didn't react to the shark near the swim zone..."
requirements: []  # extensibility: future requirements tracking
scenario:
  sea_polygon: {vertices: [[0,0], ...]}
  zones: [...]
  detections: {spawners: [...]}
  drone_pose: {x: 42.3, y: 18.7, z: 5.0}
  mission_state:
    mission_clock: 45.2
    waypoints_completed: 12
    waypoints_total: 48
    battery: 0.74
  agent_responses:
    - {kind: "continue", args: {}, time: 40.1}
    - {kind: "continue", args: {}, time: 45.0}
```

A CLI tool converts bug scenarios to factory tasks:

```bash
python -m sim.bug_to_task scenarios/bugs/shark-no-reaction.yaml
```

## 9. Scenarios

### 9.1 swim_patrol.yaml

**Usecase:** Watch swimmers
**Description:** 3 swimmers in swim zone. At t=20s, one swimmer drifts outside. Drone detects out-of-zone swimmer and responds.
**Expected:** Agent detects out-of-zone swimmer, issues directive to investigate, drone adjusts course.

### 9.2 shark_warning.yaml

**Usecase:** Warn for shark — navigation plan pre-emption
**Description:** 2 swimmers in swim zone, 1 surfer in surf zone. At t=15s, a shark appears at low confidence (0.4) at 80m range. Agent issues `override` to investigate. Drone approaches → confidence rises to 0.9 → agent confirms shark → warns swimmers → drone returns to patrol.
**Expected:** Full pre-emption cycle: patrol → investigate → confirm → warn → resume patrol.

### 9.3 multiple_threats.yaml

**Usecase:** Priority resolution
**Description:** 3 swimmers, 2 surfers, 2 sharks appearing at different times. Tests that the agent correctly prioritizes the closest/ most urgent threat.
**Expected:** Agent responds to nearest/highest-confidence threat first.

### 9.4 false_alarm.yaml

**Usecase:** Low-confidence no follow-up
**Description:** A shark is detected at low confidence but moves away (out of sensor range). Agent should not chase.
**Expected:** Agent continues patrol, drops the detection from active concerns.

### 9.5 all_clear.yaml

**Usecase:** Baseline normal patrol
**Description:** 2 swimmers, 1 surfer, no threats. Drone completes full perimeter sweep without incident.
**Expected:** Mission completes normally, all waypoints reached.

## 10. Workflow Integration

### 10.1 Bug-to-task pipeline

1. User presses `B` in interactive mode
2. Bug capture dialog opens → user describes the issue
3. YAML snapshot saved to `scenarios/bugs/<date>-<description>.yaml`
4. (Optional) `python -m sim.bug_to_task` converts to a factory task:
   - Validates the scenario YAML
   - Creates a task in the factory ledger
   - The task includes: the bug scenario as a test case, the user description, and a reference to the original scenario
5. The developer picks up the task, fixes the code, re-runs the bug scenario to verify

### 10.2 Requirements addon extensibility

The `requirements` field in bug captures is intentionally left empty. The future requirements tracking system can:
- Add a `requirements` field to the Scenario dataclass
- Populate it with requirement IDs when creating bug scenarios
- Link bug scenarios to requirement verification

No changes to the bug capture code are needed — the field is already in the schema.

## 11. Testing Strategy

- **Unit tests** (`pytest -m unit`): DetectionSpawner entity spawning, Scenario YAML round-trip, Recorder trace, text input widget
- **Sim tests** (`pytest -m sim`): Full mission loop with DetectionSpawner, renderer smoke test (headless, no window), scenario-driven integration tests
- **Scenario verification**: Each scenario YAML file is loaded and validated by `test_scenario.py`

## 12. Dependencies

Added to `pyproject.toml` (already installed):
- `pygame>=2.5`
- `matplotlib>=3.8`

No new dependencies beyond these.

## 13. Non-Goals

- Real camera input or computer vision (deferred)
- Real drone hardware integration (deferred)
- PyBullet 3D physics simulation (deferred)
- Telekinesis transport (deferred)
- Requirements tracking system (separate parallel effort)