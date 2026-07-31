# Simulation Testbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a pygame-based interactive simulation testbench for drone mission scenarios with swim/surf zones, shark/swimmer/surfer detections, bug capture, and matplotlib post-mission analysis.

**Architecture:** A `SimTestbench` class wraps the existing `MissionLoop`, replacing `ScriptedPerception` with a `DetectionSpawner` that spawns entities from YAML scenario definitions. A pygame renderer draws the world in real-time, a recorder captures mission traces, and a bug capture dialog saves snapshots to YAML for factory task creation.

**Tech Stack:** Python 3.11+, pygame 2.5+, matplotlib 3.8+, existing drone mission system

## Global Constraints

- Python >=3.11, <3.13
- All new code in `src/sim/` package
- All new tests in `tests/sim/`
- Use existing types from `drone.interfaces` (Pose, Detection, NavPlan, WaterArea, etc.)
- Use existing `MissionLoop`, `FakeAgent`, `FakeFlightController`, `PriorityFilter`
- TDD: write failing test first, verify failure, write implementation, verify pass, commit
- pytest markers: `unit` for pure tests, `sim` for integration tests
- All YAML scenario files validated by tests

---

### Task 1: Scenario Dataclass and YAML I/O

**Files:**
- Create: `src/sim/__init__.py`
- Create: `src/sim/scenario.py`
- Create: `tests/sim/__init__.py`
- Create: `tests/sim/test_scenario.py`

**Interfaces:**
- Consumes: `drone.interfaces.WaterArea`
- Produces: `Scenario` dataclass with `load(path)`, `save(scenario, path)` methods

- [ ] **Step 1: Write the test for scenario round-trip**

```python
# tests/sim/test_scenario.py
from __future__ import annotations

import pytest
import tempfile
from pathlib import Path

from sim.scenario import Scenario, Zone, SpawnerRule


class TestScenarioRoundTrip:
    def test_minimal_scenario_round_trip(self):
        scenario = Scenario(
            name="test-scenario",
            description="A test scenario",
            sea_polygon={"vertices": [[0, 0], [100, 0], [100, 100], [0, 100]]},
            zones=[],
            navigation={"algorithm": "perimeter_sweep", "altitude": 5.0, "offset": 2.0},
            agent={"type": "fake", "responses": []},
            detections={"spawners": []},
            max_duration=300.0,
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            path = f.name
            Scenario.save(scenario, path)
        loaded = Scenario.load(path)
        assert loaded.name == scenario.name
        assert loaded.sea_polygon == scenario.sea_polygon
        assert loaded.navigation == scenario.navigation
        Path(path).unlink()

    def test_scenario_with_zones_and_spawners(self):
        scenario = Scenario(
            name="full-scenario",
            description="Scenario with zones and spawners",
            sea_polygon={"vertices": [[0, 0], [50, 0], [50, 50], [0, 50]]},
            zones=[
                Zone(id="swim-zone", label="swim_area",
                     polygon=[[5, 5], [20, 5], [20, 20], [5, 20]],
                     color=[0, 200, 255, 80]),
            ],
            navigation={"algorithm": "perimeter_sweep", "altitude": 5.0, "offset": 2.0},
            agent={"type": "fake", "responses": []},
            detections={
                "spawners": [
                    SpawnerRule(label="swimmer", pool="inside_zone(swim-zone)",
                                count=3, start_time=0.0, interval=5.0, speed=0.5),
                ]
            },
            priority_rules=[{"label": "shark", "min_confidence": 0.7, "reason": "shark detected"}],
            max_duration=300.0,
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            path = f.name
            Scenario.save(scenario, path)
        loaded = Scenario.load(path)
        assert len(loaded.zones) == 1
        assert loaded.zones[0].id == "swim-zone"
        assert len(loaded.detections["spawners"]) == 1
        assert loaded.detections["spawners"][0].label == "swimmer"
        Path(path).unlink()

    def test_load_nonexistent_raises(self):
        with pytest.raises(FileNotFoundError):
            Scenario.load("/nonexistent/path.yaml")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/sim/test_scenario.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sim'`

- [ ] **Step 3: Write the implementation**

```python
# src/sim/__init__.py
"""Simulation testbench for drone mission scenarios."""
from __future__ import annotations
```

```python
# src/sim/scenario.py
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

import yaml


@dataclass
class Zone:
    id: str
    label: str
    polygon: list[list[float]]
    color: list[int]  # RGBA


@dataclass
class SpawnerRule:
    label: str
    pool: str
    count: int
    start_time: float
    interval: float
    speed: float


@dataclass
class Scenario:
    name: str
    description: str
    sea_polygon: dict
    zones: list[Zone]
    navigation: dict
    agent: dict
    detections: dict
    priority_rules: list[dict] | None = None
    max_duration: float = 300.0

    @classmethod
    def load(cls, path: str | Path) -> Scenario:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Scenario file not found: {path}")
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls._from_dict(data)

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            yaml.dump(self._to_dict(), f, default_flow_style=False)

    @classmethod
    def _from_dict(cls, data: dict) -> Scenario:
        zones = [Zone(**z) for z in data.get("zones", [])]
        spawners = [SpawnerRule(**s) for s in data.get("detections", {}).get("spawners", [])]
        detections = {"spawners": spawners}
        return cls(
            name=data["name"],
            description=data["description"],
            sea_polygon=data["sea_polygon"],
            zones=zones,
            navigation=data["navigation"],
            agent=data["agent"],
            detections=detections,
            priority_rules=data.get("priority_rules"),
            max_duration=data.get("max_duration", 300.0),
        )

    def _to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "sea_polygon": self.sea_polygon,
            "zones": [asdict(z) for z in self.zones],
            "navigation": self.navigation,
            "agent": self.agent,
            "detections": {
                "spawners": [asdict(s) for s in self.detections["spawners"]],
            },
            "priority_rules": self.priority_rules,
            "max_duration": self.max_duration,
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/sim/test_scenario.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/sim/__init__.py src/sim/scenario.py tests/sim/__init__.py tests/sim/test_scenario.py
git commit -m "feat: scenario dataclass and YAML I/O for sim testbench"
```

---

### Task 2: Detection Spawner

**Files:**
- Create: `src/sim/detection_spawner.py`
- Create: `tests/sim/test_detection_spawner.py`

**Interfaces:**
- Consumes: `Scenario` (zones, spawners, sea_polygon), `drone.interfaces.Pose`, `drone.interfaces.Perception`
- Produces: `DetectionSpawner` implementing `Perception` protocol

- [ ] **Step 1: Write the test**

```python
# tests/sim/test_detection_spawner.py
from __future__ import annotations

import pytest
from drone.interfaces import Pose, Detection
from sim.detection_spawner import DetectionSpawner
from sim.scenario import Zone, SpawnerRule


class TestDetectionSpawner:
    def test_returns_empty_when_no_spawners(self):
        spawner = DetectionSpawner(
            spawners=[],
            zones=[],
            sea_polygon=[[0, 0], [10, 0], [10, 10], [0, 10]],
        )
        spawner.set_drone_pose(Pose(5, 5, 5, 0))
        dets = spawner.get_detections()
        assert dets == []

    def test_spawner_returns_expected_count(self):
        spawner = DetectionSpawner(
            spawners=[
                SpawnerRule(label="swimmer", pool="inside_polygon(sea_polygon)",
                            count=3, start_time=0.0, interval=0.0, speed=0.0),
            ],
            zones=[],
            sea_polygon=[[0, 0], [100, 0], [100, 100], [0, 100]],
            max_sensor_range=200.0,
        )
        spawner.set_drone_pose(Pose(50, 50, 5, 0))
        dets = spawner.get_detections()
        assert len(dets) == 3
        for d in dets:
            assert d.label == "swimmer"
            assert 0.0 <= d.confidence <= 1.0
            assert d.range > 0

    def test_confidence_decreases_with_distance(self):
        spawner = DetectionSpawner(
            spawners=[
                SpawnerRule(label="shark", pool="inside_polygon(sea_polygon)",
                            count=1, start_time=0.0, interval=0.0, speed=0.0),
            ],
            zones=[],
            sea_polygon=[[0, 0], [100, 0], [100, 100], [0, 100]],
            max_sensor_range=100.0,
        )
        # Drone far away -> low confidence
        spawner.set_drone_pose(Pose(0, 0, 5, 0))
        far_dets = spawner.get_detections()
        far_conf = far_dets[0].confidence

        # Drone close -> high confidence
        shark_pos = far_dets[0].position
        spawner.set_drone_pose(Pose(shark_pos.x + 1, shark_pos.y, 5, 0))
        close_dets = spawner.get_detections()
        close_conf = close_dets[0].confidence

        assert close_conf > far_conf, "Confidence should increase as drone approaches"

    def test_spawn_entity_adds_one(self):
        spawner = DetectionSpawner(
            spawners=[
                SpawnerRule(label="swimmer", pool="inside_polygon(sea_polygon)",
                            count=1, start_time=0.0, interval=0.0, speed=0.0),
            ],
            zones=[],
            sea_polygon=[[0, 0], [100, 0], [100, 100], [0, 100]],
        )
        spawner.set_drone_pose(Pose(50, 50, 5, 0))
        dets = spawner.get_detections()
        assert len(dets) == 1
        spawner.spawn_entity("shark")
        dets = spawner.get_detections()
        assert len(dets) == 2
        assert dets[1].label == "shark"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/sim/test_detection_spawner.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sim.detection_spawner'`

- [ ] **Step 3: Write the implementation**

```python
# src/sim/detection_spawner.py
from __future__ import annotations

import math
import random
from dataclasses import dataclass

from drone.interfaces import Pose, Detection
from sim.scenario import Zone, SpawnerRule


@dataclass
class Entity:
    label: str
    position: Pose
    speed: float
    pool_bounds: list[tuple[float, float]]  # polygon vertices
    pool_is_inside: bool  # True = stay inside polygon, False = stay outside
    start_time: float


class DetectionSpawner:
    """Perception implementation that spawns entities from scenario rules."""

    def __init__(
        self,
        spawners: list[SpawnerRule],
        zones: list[Zone],
        sea_polygon: list[list[float]],
        max_sensor_range: float = 100.0,
    ) -> None:
        self._zones = zones
        self._sea_polygon = sea_polygon
        self._max_sensor_range = max_sensor_range
        self._drone_pose = Pose(0, 0, 0, 0)
        self._entities: list[Entity] = []
        self._spawner_defs = spawners
        self._clock: float = 0.0

        # Initialize entities for spawners with start_time=0
        for spawner in spawners:
            if spawner.start_time <= 0.0:
                for _ in range(spawner.count):
                    pos = self._random_position_in_pool(spawner.pool)
                    self._entities.append(Entity(
                        label=spawner.label,
                        position=pos,
                        speed=spawner.speed,
                        pool_bounds=self._resolve_pool_bounds(spawner.pool),
                        pool_is_inside=self._pool_is_inside(spawner.pool),
                        start_time=spawner.start_time,
                    ))

    def set_drone_pose(self, pose: Pose) -> None:
        self._drone_pose = pose

    def get_detections(self) -> list[Detection]:
        self._clock += 0.05  # approximate timestep
        self._tick_entities()
        self._check_spawn_timers()

        dets: list[Detection] = []
        for entity in self._entities:
            dx = entity.position.x - self._drone_pose.x
            dy = entity.position.y - self._drone_pose.y
            rng = math.sqrt(dx * dx + dy * dy)
            bearing = math.degrees(math.atan2(dy, dx)) % 360
            confidence = max(0.0, min(1.0, 1.0 - rng / self._max_sensor_range))

            dets.append(Detection(
                label=entity.label,
                confidence=confidence,
                bearing=bearing,
                range=rng,
                position=entity.position,
            ))
        return dets

    def spawn_entity(self, label: str) -> None:
        """Spawn one additional entity (for keyboard injection)."""
        # Find a spawner definition matching the label
        pool = "inside_polygon(sea_polygon)"
        speed = 1.0
        for s in self._spawner_defs:
            if s.label == label:
                pool = s.pool
                speed = s.speed
                break
        pos = self._random_position_in_pool(pool)
        self._entities.append(Entity(
            label=label,
            position=pos,
            speed=speed,
            pool_bounds=self._resolve_pool_bounds(pool),
            pool_is_inside=self._pool_is_inside(pool),
            start_time=0.0,
        ))

    def _tick_entities(self) -> None:
        """Move each entity with a random walk."""
        for entity in self._entities:
            if entity.speed <= 0:
                continue
            angle = random.uniform(0, 2 * math.pi)
            step = entity.speed * 0.05  # per-tick movement
            nx = entity.position.x + math.cos(angle) * step
            ny = entity.position.y + math.sin(angle) * step
            entity.position = Pose(nx, ny, 0, 0)

    def _check_spawn_timers(self) -> None:
        """Spawn entities whose start_time has been reached."""
        for spawner in self._spawner_defs:
            if sparker.start_time <= 0.0:
                continue  # already spawned in __init__
            if self._clock >= spawner.start_time:
                # Check if we've already spawned this group
                already_spawned = any(
                    e.label == spawner.label for e in self._entities
                )
                if not already_spawned:
                    for _ in range(spawner.count):
                        pos = self._random_position_in_pool(spawner.pool)
                        self._entities.append(Entity(
                            label=spawner.label,
                            position=pos,
                            speed=spawner.speed,
                            pool_bounds=self._resolve_pool_bounds(spawner.pool),
                            pool_is_inside=self._pool_is_inside(spawner.pool),
                            start_time=spawner.start_time,
                        ))

    def _resolve_pool_bounds(self, pool_expr: str) -> list[tuple[float, float]]:
        if pool_expr.startswith("inside_zone("):
            zone_id = pool_expr[12:-1]
            for z in self._zones:
                if z.id == zone_id:
                    return [(p[0], p[1]) for p in z.polygon]
            return []
        elif pool_expr.startswith("inside_polygon("):
            name = pool_expr[15:-1]
            if name == "sea_polygon":
                return [(p[0], p[1]) for p in self._sea_polygon]
            return []
        return []

    def _pool_is_inside(self, pool_expr: str) -> bool:
        return not pool_expr.startswith("outside_")

    def _random_position_in_pool(self, pool_expr: str) -> Pose:
        bounds = self._resolve_pool_bounds(pool_expr)
        if not bounds:
            return Pose(0, 0, 0, 0)
        min_x = min(p[0] for p in bounds)
        max_x = max(p[0] for p in bounds)
        min_y = min(p[1] for p in bounds)
        max_y = max(p[1] for p in bounds)
        x = random.uniform(min_x, max_x)
        y = random.uniform(min_y, max_y)
        return Pose(x, y, 0, 0)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/sim/test_detection_spawner.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/sim/detection_spawner.py tests/sim/test_detection_spawner.py
git commit -m "feat: detection spawner for sim testbench"
```

---

### Task 3: Recorder (Mission Trace)

**Files:**
- Create: `src/sim/recorder.py`
- Create: `tests/sim/test_recorder.py`

**Interfaces:**
- Consumes: `drone.interfaces.Pose`, `drone.interfaces.Detection`, `drone.interfaces.Directive`
- Produces: `Recorder` that records `Frame` objects and can save/load traces

- [ ] **Step 1: Write the test**

```python
# tests/sim/test_recorder.py
from __future__ import annotations

import pytest
import tempfile
from pathlib import Path

from drone.interfaces import Pose, Detection, Directive
from sim.recorder import Recorder, Frame


class TestRecorder:
    def test_record_and_trace(self):
        recorder = Recorder(record_interval=0.0)  # record every call
        recorder.record(
            mission_clock=0.0,
            drone_pose=Pose(0, 0, 5, 0),
            detections=[Detection(label="swimmer", confidence=0.9, bearing=0, range=10, position=Pose(10, 0, 0, 0))],
            active_directive=Directive(kind="continue"),
            waypoint_status={"current_idx": 0, "total": 10, "completed": 0},
        )
        recorder.record(
            mission_clock=1.0,
            drone_pose=Pose(5, 0, 5, 0),
            detections=[],
            active_directive=None,
            waypoint_status={"current_idx": 2, "total": 10, "completed": 2},
        )
        trace = recorder.trace()
        assert len(trace) == 2
        assert trace[0].mission_clock == 0.0
        assert trace[1].mission_clock == 1.0
        assert len(trace[0].detections) == 1
        assert trace[0].detections[0].label == "swimmer"

    def test_save_and_load(self):
        recorder = Recorder(record_interval=0.0)
        recorder.record(
            mission_clock=0.0,
            drone_pose=Pose(5, 5, 5, 0),
            detections=[],
            active_directive=Directive(kind="continue"),
            waypoint_status={"current_idx": 0, "total": 5, "completed": 0},
        )
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False, mode="w") as f:
            path = f.name
            recorder.save(f.name)
        loaded = Recorder.load(path)
        assert len(loaded.trace()) == 1
        assert loaded.trace()[0].drone_pose.x == 5.0
        Path(path).unlink()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/sim/test_recorder.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sim.recorder'`

- [ ] **Step 3: Write the implementation**

```python
# src/sim/recorder.py
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import yaml

from drone.interfaces import Pose, Detection, Directive


@dataclass
class Frame:
    mission_clock: float
    drone_pose: Pose
    detections: list[Detection]
    active_directive: Directive | None
    waypoint_status: dict


class Recorder:
    """Records mission trace frames for replay and analysis."""

    def __init__(self, record_interval: float = 0.5) -> None:
        self._record_interval = record_interval
        self._frames: list[Frame] = []
        self._last_recorded: float = -999.0

    def record(
        self,
        mission_clock: float,
        drone_pose: Pose,
        detections: list[Detection],
        active_directive: Directive | None,
        waypoint_status: dict,
    ) -> None:
        if mission_clock - self._last_recorded < self._record_interval:
            return
        self._frames.append(Frame(
            mission_clock=mission_clock,
            drone_pose=drone_pose,
            detections=detections,
            active_directive=active_directive,
            waypoint_status=waypoint_status,
        ))
        self._last_recorded = mission_clock

    def trace(self) -> list[Frame]:
        return list(self._frames)

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = []
        for frame in self._frames:
            data.append({
                "mission_clock": frame.mission_clock,
                "drone_pose": {"x": frame.drone_pose.x, "y": frame.drone_pose.y,
                               "z": frame.drone_pose.z, "heading": frame.drone_pose.heading},
                "detections": [
                    {"label": d.label, "confidence": d.confidence,
                     "bearing": d.bearing, "range": d.range,
                     "position": {"x": d.position.x, "y": d.position.y,
                                  "z": d.position.z, "heading": d.position.heading}}
                    for d in frame.detections
                ],
                "active_directive": {"kind": frame.active_directive.kind, "args": dict(frame.active_directive.args)}
                if frame.active_directive else None,
                "waypoint_status": frame.waypoint_status,
            })
        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False)

    @classmethod
    def load(cls, path: str | Path) -> Recorder:
        with open(path) as f:
            data = yaml.safe_load(f)
        recorder = cls(record_interval=0.0)
        for item in data:
            dp = item["drone_pose"]
            pose = Pose(dp["x"], dp["y"], dp["z"], dp["heading"])
            dets = []
            for d in item["detections"]:
                p = d["position"]
                dets.append(Detection(d["label"], d["confidence"], d["bearing"], d["range"],
                                       Pose(p["x"], p["y"], p["z"], p["heading"])))
            directive = None
            if item["active_directive"]:
                ad = item["active_directive"]
                directive = Directive(kind=ad["kind"], args=ad["args"])
            recorder._frames.append(Frame(
                mission_clock=item["mission_clock"],
                drone_pose=pose,
                detections=dets,
                active_directive=directive,
                waypoint_status=item["waypoint_status"],
            ))
        return recorder
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/sim/test_recorder.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/sim/recorder.py tests/sim/test_recorder.py
git commit -m "feat: mission trace recorder for sim testbench"
```

---

### Task 4: Text Input Dialog (Pygame Widget)

**Files:**
- Create: `src/sim/text_input.py`

**Interfaces:**
- Consumes: `pygame.Surface`, `pygame.event.Event`
- Produces: `TextInput` dialog widget

- [ ] **Step 1: Write the test (headless, no display)**

```python
# tests/sim/test_text_input.py
from __future__ import annotations

import pytest


class TestTextInputWidget:
    def test_import(self):
        from sim.text_input import TextInput
        # Just verify it imports cleanly
        assert True

    def test_text_input_style(self):
        """Test that the style/panel definitions are valid."""
        from sim.text_input import PANEL_WIDTH, PANEL_HEIGHT, FONT_SIZE
        assert PANEL_WIDTH > 0
        assert PANEL_HEIGHT > 0
        assert FONT_SIZE > 0
```

- [ ] **Step 2: Run test (will fail at import step initially)**

- [ ] **Step 3: Write the implementation**

```python
# src/sim/text_input.py
from __future__ import annotations

import pygame

# Panel dimensions
PANEL_WIDTH = 600
PANEL_HEIGHT = 300
FONT_SIZE = 20


class TextInput:
    """A simple text input dialog for pygame."""

    def __init__(self, screen: pygame.Surface, prompt: str) -> None:
        self._screen = screen
        self._prompt = prompt
        self._text: str = ""
        self._done = False
        self._cancelled = False
        self._font = pygame.font.Font(None, FONT_SIZE)

    @property
    def text(self) -> str:
        return self._text

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN:
                self._done = True
            elif event.key == pygame.K_ESCAPE:
                self._cancelled = True
                self._done = True
            elif event.key == pygame.K_BACKSPACE:
                self._text = self._text[:-1]
            else:
                if len(self._text) < 200 and event.unicode.isprintable():
                    self._text += event.unicode

    def draw(self) -> None:
        """Draw the dialog overlay on the screen."""
        w, h = self._screen.get_size()
        panel_x = (w - PANEL_WIDTH) // 2
        panel_y = (h - PANEL_HEIGHT) // 2

        # Dim background
        overlay = pygame.Surface((w, h), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self._screen.blit(overlay, (0, 0))

        # Panel background
        pygame.draw.rect(self._screen, (40, 40, 60),
                         (panel_x, panel_y, PANEL_WIDTH, PANEL_HEIGHT),
                         border_radius=8)

        # Prompt text
        prompt_surf = self._font.render(self._prompt, True, (200, 200, 220))
        self._screen.blit(prompt_surf, (panel_x + 20, panel_y + 30))

        # Text input area
        input_rect = pygame.Rect(panel_x + 20, panel_y + 80, PANEL_WIDTH - 40, 40)
        pygame.draw.rect(self._screen, (60, 60, 80), input_rect, border_radius=4)
        pygame.draw.rect(self._screen, (100, 140, 255), input_rect, 2, border_radius=4)

        # Cursor blink
        display_text = self._text
        if (pygame.time.get_ticks() // 500) % 2 == 0:
            display_text += "|"
        text_surf = self._font.render(display_text, True, (255, 255, 255))
        self._screen.blit(text_surf, (panel_x + 30, panel_y + 88))

        # Hint text
        hint = self._font.render("[Enter] save  [Esc] cancel", True, (150, 150, 180))
        self._screen.blit(hint, (panel_x + 20, panel_y + PANEL_HEIGHT - 40))

    def is_done(self) -> bool:
        return self._done
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/sim/test_text_input.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/sim/text_input.py tests/sim/test_text_input.py
git commit -m "feat: text input dialog widget for pygame"
```

---

### Task 5: Pygame Renderer and HUD

**Files:**
- Create: `src/sim/renderer.py`
- Create: `src/sim/hud.py`

**Interfaces:**
- Consumes: `Scenario`, `Pose`, `Detection`, `Directive`, `pygame.Surface`
- Produces: `Renderer` class with `draw_world()`, `draw_hud()` methods

- [ ] **Step 1: Write smoke test**

```python
# tests/sim/test_renderer.py
from __future__ import annotations

import pytest


class TestRendererImports:
    def test_import_renderer(self):
        from sim.renderer import Renderer
        assert True

    def test_import_hud(self):
        from sim.hud import HUD
        assert True
```

- [ ] **Step 2: Run test (will fail initially)**

- [ ] **Step 3: Write the implementation**

```python
# src/sim/renderer.py
from __future__ import annotations

import math
from typing import Any

import pygame

from drone.interfaces import Pose, Detection
from sim.scenario import Scenario, Zone


# Colors
COLOR_SEA = (20, 80, 160)
COLOR_SEA_EDGE = (40, 120, 200)
COLOR_DRONE = (255, 255, 255)
COLOR_SWIMMER = (0, 150, 255)
COLOR_SURFER = (255, 180, 0)
COLOR_SHARK = (255, 50, 50)
COLOR_GRID = (40, 60, 80)
COLOR_EVENT_STAR = (255, 255, 0)
COLOR_EVENT_WARN = (255, 100, 100)


def _world_to_screen(world_x: float, world_y: float,
                      offset_x: float, offset_y: float, scale: float,
                      screen_w: int, screen_h: int) -> tuple[float, float]:
    """Convert world coordinates to screen pixel coordinates."""
    sx = screen_w / 2 + (world_x - offset_x) * scale
    sy = screen_h / 2 - (world_y - offset_y) * scale  # flip Y axis
    return sx, sy


class Renderer:
    """Pygame renderer for the simulation world."""

    def __init__(self, screen: pygame.Surface, scenario: Scenario) -> None:
        self._screen = screen
        self._scenario = scenario
        self._offset_x: float = 0.0
        self._offset_y: float = 0.0
        self._scale: float = 3.0  # pixels per meter
        self._pending_events: list[dict] = []  # events to show on screen

    def add_event(self, event_type: str, position: Pose, label: str) -> None:
        self._pending_events.append({
            "type": event_type,  # "shark_alert" or "warning"
            "position": position,
            "label": label,
            "created_at": pygame.time.get_ticks(),
        })

    def set_view(self, center_x: float, center_y: float, scale: float) -> None:
        self._offset_x = center_x
        self._offset_y = center_y
        self._scale = scale

    def draw_world(
        self,
        drone_pose: Pose,
        detections: list[Detection],
        waypoints: list[Pose] | None = None,
    ) -> None:
        """Draw the full world state."""
        screen_w, screen_h = self._screen.get_size()

        # Background
        self._screen.fill((10, 10, 20))

        # Grid
        self._draw_grid()

        # Sea polygon
        verts = self._scenario.sea_polygon["vertices"]
        if verts:
            self._draw_polygon(verts, COLOR_SEA, COLOR_SEA_EDGE, 2)

        # Zones
        for zone in self._scenario.zones:
            self._draw_zone(zone)

        # Waypoints (nav plan)
        if waypoints:
            self._draw_waypoints(waypoints)

        # Event markers
        self._draw_event_markers()

        # Detections
        for det in detections:
            self._draw_detection(det, drone_pose)

        # Drone
        self._draw_drone(drone_pose)

    def _draw_grid(self) -> None:
        screen_w, screen_h = self._screen.get_size()
        grid_size = 10  # meters
        step = grid_size * self._scale

        cx = screen_w / 2 - self._offset_x * self._scale
        cy = screen_h / 2 + self._offset_y * self._scale

        x_start = (cx % step) - step
        y_start = (cy % step) - step

        for x in range(int(x_start), screen_w + int(step), int(step)):
            pygame.draw.line(self._screen, COLOR_GRID, (x, 0), (x, screen_h), 1)
        for y in range(int(y_start), screen_h + int(step), int(step)):
            pygame.draw.line(self._screen, COLOR_GRID, (0, y), (screen_w, y), 1)

    def _draw_polygon(self, verts: list, fill_color: tuple,
                      edge_color: tuple, edge_width: int) -> None:
        screen_poly = []
        for vx, vy in verts:
            sx, sy = _world_to_screen(float(vx), float(vy), self._offset_x,
                                      self._offset_y, self._scale,
                                      self._screen.get_width(), self._screen.get_height())
            screen_poly.append((int(sx), int(sy)))
        if len(screen_poly) >= 3:
            pygame.draw.polygon(self._screen, fill_color, screen_poly)
            pygame.draw.polygon(self._screen, edge_color, screen_poly, edge_width)

    def _draw_zone(self, zone: Zone) -> None:
        rgba = zone.color
        color = (rgba[0], rgba[1], rgba[2])
        alpha = rgba[3] if len(rgba) > 3 else 80

        # Draw with alpha using a surface
        screen_poly = []
        for vx, vy in zone.polygon:
            sx, sy = _world_to_screen(float(vx), float(vy), self._offset_x,
                                      self._offset_y, self._scale,
                                      self._screen.get_width(), self._screen.get_height())
            screen_poly.append((int(sx), int(sy)))

        if len(screen_poly) >= 3:
            surf = pygame.Surface(self._screen.get_size(), pygame.SRCALPHA)
            pygame.draw.polygon(surf, (*color, alpha), screen_poly)
            pygame.draw.polygon(surf, (*color, 200), screen_poly, 2)
            self._screen.blit(surf, (0, 0))

            # Label
            cx = sum(p[0] for p in screen_poly) // len(screen_poly)
            cy = sum(p[1] for p in screen_poly) // len(screen_poly)
            font = pygame.font.Font(None, 18)
            label = font.render(zone.label.replace("_", " ").title(), True, (200, 200, 200))
            self._screen.blit(label, (cx - label.get_width() // 2, cy - label.get_height() // 2))

    def _draw_waypoints(self, waypoints: list[Pose]) -> None:
        if len(waypoints) < 2:
            return
        screen_pts = []
        for wp in waypoints:
            sx, sy = _world_to_screen(wp.x, wp.y, self._offset_x,
                                      self._offset_y, self._scale,
                                      self._screen.get_width(), self._screen.get_height())
            screen_pts.append((int(sx), int(sy)))

        # Draw path
        pygame.draw.lines(self._screen, (100, 200, 255), False, screen_pts, 1)

        # Draw waypoint dots
        for i, (sx, sy) in enumerate(screen_pts):
            color = (150, 220, 255) if i > 0 else (0, 255, 100)
            pygame.draw.circle(self._screen, color, (sx, sy), 3)

    def _draw_drone(self, pose: Pose) -> None:
        sx, sy = _world_to_screen(pose.x, pose.y, self._offset_x,
                                  self._offset_y, self._scale,
                                  self._screen.get_width(), self._screen.get_height())
        # Triangle pointing in heading direction
        heading_rad = math.radians(pose.heading)
        size = 10
        pts = [
            (sx + size * math.cos(heading_rad),
             sy - size * math.sin(heading_rad)),
            (sx + size * 0.5 * math.cos(heading_rad + 2.5),
             sy - size * 0.5 * math.sin(heading_rad + 2.5)),
            (sx + size * 0.5 * math.cos(heading_rad - 2.5),
             sy - size * 0.5 * math.sin(heading_rad - 2.5)),
        ]
        pygame.draw.polygon(self._screen, COLOR_DRONE, pts)
        pygame.draw.circle(self._screen, (200, 200, 255), (int(sx), int(sy)), 12, 1)

    def _draw_detection(self, det: Detection, drone_pose: Pose) -> None:
        sx, sy = _world_to_screen(det.position.x, det.position.y, self._offset_x,
                                  self._offset_y, self._scale,
                                  self._screen.get_width(), self._screen.get_height())

        # Color by label
        label_lower = det.label.lower()
        if "shark" in label_lower:
            color = COLOR_SHARK
        elif "surf" in label_lower:
            color = COLOR_SURFER
        else:
            color = COLOR_SWIMMER

        # Size by confidence
        radius = max(4, int(8 * det.confidence))
        pygame.draw.circle(self._screen, color, (int(sx), int(sy)), radius)
        if det.confidence < 0.5:
            pygame.draw.circle(self._screen, (100, 100, 100), (int(sx), int(sy)), radius + 3, 1)

        # Label
        font = pygame.font.Font(None, 14)
        label = font.render(f"{det.label} {det.confidence:.2f}", True, (200, 200, 200))
        self._screen.blit(label, (sx - label.get_width() // 2, sy - radius - 16))

        # Range ring
        pygame.draw.circle(self._screen, (80, 80, 80, 100),
                           (int(sx), int(sy)), int(det.range * self._scale * 0.1), 1)

    def _draw_event_markers(self) -> None:
        """Draw fading event markers."""
        current_time = pygame.time.get_ticks()
        self._pending_events = [
            e for e in self._pending_events
            if current_time - e["created_at"] < 5000  # 5s display
        ]
        for event in self._pending_events:
            pos = event["position"]
            sx, sy = _world_to_screen(pos.x, pos.y, self._offset_x,
                                      self._offset_y, self._scale,
                                      self._screen.get_width(), self._screen.get_height())
            color = COLOR_EVENT_STAR if event["type"] == "shark_alert" else COLOR_EVENT_WARN
            font = pygame.font.Font(None, 20)
            text = font.render(event["label"], True, color)
            self._screen.blit(text, (sx - text.get_width() // 2, sy - 30))
            # Star icon
            pygame.draw.circle(self._screen, color, (int(sx), int(sy - 20)), 5)
```

```python
# src/sim/hud.py
from __future__ import annotations

import pygame


class HUD:
    """Heads-up display overlay for the simulation testbench."""

    BG_COLOR = (0, 0, 0, 140)
    TEXT_COLOR = (220, 220, 240)
    HIGHLIGHT_COLOR = (100, 200, 255)
    WARN_COLOR = (255, 150, 100)

    def __init__(self, font_size: int = 18) -> None:
        self._font = pygame.font.Font(None, font_size)
        self._small_font = pygame.font.Font(None, 14)

    def draw(
        self,
        screen: pygame.Surface,
        mission_name: str,
        mission_clock: float,
        speed_mult: float,
        fps: float,
        nav_status: str,
        battery: float,
        detection_summary: dict[str, int],
        event_log: list[str],
        controls_hint: str = "[S] shark  [W] swimmer  [F] surfer  [B] bug  [Esc] quit",
    ) -> None:
        """Draw the HUD panel."""
        w, _ = screen.get_size()

        # Background panel (right side)
        panel_w = 320
        panel_surf = pygame.Surface((panel_w, 600), pygame.SRCALPHA)
        panel_surf.fill(self.BG_COLOR)

        y = 10
        lines = []

        # Mission info
        lines.append((f"MISSION: {mission_name}", self.HIGHLIGHT_COLOR))
        lines.append((f"TIME: {mission_clock:06.1f}s  SPEED: {speed_mult}×  FPS: {fps:.0f}", self.TEXT_COLOR))
        lines.append(("", self.TEXT_COLOR))

        # Nav status
        lines.append((f"NAV: {nav_status}", self.TEXT_COLOR))
        battery_color = self.WARN_COLOR if battery < 0.2 else self.TEXT_COLOR
        lines.append((f"BATTERY: {battery * 100:.0f}%", battery_color))
        lines.append(("", self.TEXT_COLOR))

        # Detections
        lines.append(("DETECTIONS:", self.HIGHLIGHT_COLOR))
        if detection_summary:
            for label, count in detection_summary.items():
                lines.append((f"  ● {count} {label}(s)", self.TEXT_COLOR))
        else:
            lines.append(("  (none)", self.TEXT_COLOR))
        lines.append(("", self.TEXT_COLOR))

        # Event log (last 5)
        lines.append(("EVENTS:", self.HIGHLIGHT_COLOR))
        if event_log:
            for entry in event_log[-5:]:
                color = self.WARN_COLOR if "shark" in entry.lower() else self.TEXT_COLOR
                lines.append((f"  • {entry[:50]}", color))
        else:
            lines.append(("  (none)", self.TEXT_COLOR))
        lines.append(("", self.TEXT_COLOR))

        # Controls hint
        lines.append((controls_hint, (150, 150, 180)))

        # Render all lines
        for text, color in lines:
            if text == "":
                y += 8
                continue
            surf = self._font.render(text, True, color)
            panel_surf.blit(surf, (10, y))
            y += 22

        screen.blit(panel_surf, (w - panel_w - 10, 10))
```

- [ ] **Step 4: Run smoke test**

Run: `uv run pytest tests/sim/test_renderer.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/sim/renderer.py src/sim/hud.py tests/sim/test_renderer.py
git commit -m "feat: pygame renderer and HUD for sim testbench"
```

---

### Task 6: SimTestbench (Main Orchestrator)

**Files:**
- Create: `src/sim/testbench.py`
- Create: `src/sim/injector.py`
- Create: `src/sim/__main__.py`

**Interfaces:**
- Consumes: `Scenario`, `DetectionSpawner`, `Renderer`, `HUD`, `Recorder`, `TextInput`, `MissionLoop`, `FakeAgent`, `FakeFlightController`
- Produces: `SimTestbench` class (main loop), CLI entry point

- [ ] **Step 1: Write the integration test**

```python
# tests/sim/test_testbench_basic.py
from __future__ import annotations

import pytest


class TestTestbenchImport:
    def test_import(self):
        from sim.testbench import SimTestbench
        assert True
```

- [ ] **Step 2: Run test (fails initially)**

- [ ] **Step 3: Write the implementation**

```python
# src/sim/testbench.py
from __future__ import annotations

import math
import sys
from pathlib import Path

import pygame

from drone.interfaces import Directive, Pose, Detection, PriorityRule
from drone.fake_flight_controller import FakeFlightController
from drone.mission.loop import MissionLoop
from drone.mission.fake_agent import FakeAgent
from drone.mission.priority_filter import PriorityFilter
from drone.mission.state import MissionState
from drone.navigation.waypoint_sequencer import WaypointSequencer
from drone.navigation.registry import NavRegistry
from drone.navigation.perimeter_sweep import PerimeterSweepAlgorithm

from sim.scenario import Scenario
from sim.detection_spawner import DetectionSpawner
from sim.renderer import Renderer
from sim.hud import HUD
from sim.recorder import Recorder
from sim.text_input import TextInput
from sim.injector import EventInjector


class SimTestbench:
    """Main testbench orchestrator.

    Runs a MissionLoop with a DetectionSpawner, renders with pygame,
    and handles interactive controls.
    """

    SCREEN_WIDTH = 1280
    SCREEN_HEIGHT = 800

    def __init__(self, scenario_path: str | Path) -> None:
        self._scenario = Scenario.load(scenario_path)
        self._clock = pygame.time.Clock()
        self._running = False
        self._paused = False
        self._speed_mult = 1.0
        self._event_log: list[str] = []
        self._detection_summary: dict[str, int] = {}
        self._bug_capture_callback = None

        # Pygame init
        pygame.init()
        self._screen = pygame.display.set_mode(
            (self.SCREEN_WIDTH, self.SCREEN_HEIGHT),
            pygame.RESIZABLE,
        )
        pygame.display.set_caption(f"Sim Testbench — {self._scenario.name}")

        # Build simulation components
        self._build_simulation()

        # Build rendering
        self._renderer = Renderer(self._screen, self._scenario)
        self._hud = HUD()
        self._recorder = Recorder(record_interval=1.0)
        self._injector = EventInjector(self)

        # Center view on sea polygon centroid
        verts = self._scenario.sea_polygon["vertices"]
        if verts:
            cx = sum(v[0] for v in verts) / len(verts)
            cy = sum(v[1] for v in verts) / len(verts)
            self._renderer.set_view(cx, cy, 3.0)

    def set_bug_capture_callback(self, callback) -> None:
        """Set callback for bug capture: fn(scenario, description, state) -> None."""
        self._bug_capture_callback = callback

    def _build_simulation(self) -> None:
        nav = self._scenario.navigation
        sea_verts = [(v[0], v[1]) for v in self._scenario.sea_polygon["vertices"]]

        # Flight controller
        self._fc = FakeFlightController()

        # Detection spawner
        self._spawner = DetectionSpawner(
            spawners=self._scenario.detections["spawners"],
            zones=self._scenario.zones,
            sea_polygon=sea_verts,
        )

        # Navigation algorithm
        algo = PerimeterSweepAlgorithm(
            altitude=nav.get("altitude", 5.0),
            offset=nav.get("offset", 2.0),
            max_distance_from_shore=nav.get("max_distance_from_shore"),
        )
        # Build an initial nav plan
        from drone.interfaces import WaterArea, NavContext
        water = WaterArea(vertices=sea_verts)
        context = NavContext(current_pose=Pose(0, 0, 0, 0), completed_area=[])
        initial_plan = algo.plan(water, context)

        # Agent — use FakeAgent; for LLM agent mode we'd wire LlmAgent later
        agent = FakeAgent(responses=[
            Directive(kind="update_nav", args={"nav_plan": initial_plan}),
        ] + [Directive(kind="continue") for _ in range(2000)])

        # Priority rules from scenario
        priority_rules = None
        if self._scenario.priority_rules:
            priority_rules = [
                PriorityRule(
                    label=r["label"],
                    min_confidence=r["min_confidence"],
                    reason_template=r["reason"],
                )
                for r in self._scenario.priority_rules
            ]

        # Mission loop
        self._loop = MissionLoop(
            fc=self._fc,
            perception=self._spawner,
            agent=agent,
            priority_rules=priority_rules,
            heartbeat_interval=3.0,
            dt=0.05,
        )
        self._loop.start(self._scenario.description)

    def run(self) -> None:
        """Run the main event loop."""
        self._running = True

        while self._running:
            dt = 0.05  # fixed timestep
            self._handle_events()

            if not self._paused:
                # Run simulation tick(s) according to speed multiplier
                for _ in range(int(self._speed_mult)):
                    self._tick_simulation(dt)

            self._draw_frame()
            self._clock.tick(60)

        pygame.quit()

    def _handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self._running = False
            elif event.type == pygame.KEYDOWN:
                self._injector.handle_key(event.key)

    def _tick_simulation(self, dt: float) -> None:
        if self._loop is None:
            return

        # Run mission loop tick
        self._loop._tick_advance()
        self._loop._handle_priority_events()
        self._loop._handle_heartbeat()
        self._loop._handle_battery_critical()

        # Update detection spawner with drone pose
        pose = self._fc.get_pose()
        self._spawner.set_drone_pose(pose)

        # Record
        wp_status = {}
        if self._loop._sequencer:
            wp_status = self._loop._sequencer.status()
        self._recorder.record(
            mission_clock=self._loop._state.mission_clock if self._loop._state else 0,
            drone_pose=pose,
            detections=self._spawner.get_detections(),
            active_directive=None,
            waypoint_status=wp_status,
        )

        # Update event log from mission state
        if self._loop._state and self._loop._state.action_log:
            last_action = self._loop._state.action_log[-1]
            self._event_log.append(f"[{last_action[0]:.1f}s] {last_action[1]}")

        # Update detection summary
        dets = self._spawner.get_detections()
        summary: dict[str, int] = {}
        for d in dets:
            summary[d.label] = summary.get(d.label, 0) + 1
        self._detection_summary = summary

        # Check for loop termination
        if self._loop._state and self._loop._state.mission_clock >= self._scenario.max_duration:
            self._paused = True
            self._event_log.append("MISSION COMPLETE — max duration reached")

        if self._fc.get_battery() < 0.1:
            self._paused = True
            self._event_log.append("MISSION COMPLETE — battery critical")

    def _draw_frame(self) -> None:
        pose = self._fc.get_pose()
        dets = self._spawner.get_detections()

        # Get waypoints for rendering
        waypoints = None
        if self._loop._sequencer and self._loop._sequencer._plan:
            waypoints = self._loop._sequencer._plan.waypoints

        # Draw world
        self._renderer.draw_world(pose, dets, waypoints)

        # Draw HUD
        nav_status = "no plan"
        if self._loop._sequencer:
            s = self._loop._sequencer.status()
            if s["plan_name"]:
                nav_status = f"{s['plan_name']} ({s['completed']}/{s['total']} waypoints)"

        self._hud.draw(
            screen=self._screen,
            mission_name=self._scenario.name,
            mission_clock=self._loop._state.mission_clock if self._loop._state else 0,
            speed_mult=self._speed_mult,
            fps=self._clock.get_fps(),
            nav_status=nav_status,
            battery=self._fc.get_battery(),
            detection_summary=self._detection_summary,
            event_log=self._event_log,
        )

        # Pause overlay
        if self._paused:
            overlay = pygame.Surface(self._screen.get_size(), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 100))
            self._screen.blit(overlay, (0, 0))
            font = pygame.font.Font(None, 48)
            pause_text = font.render("PAUSED", True, (255, 255, 255))
            self._screen.blit(
                pause_text,
                (self.SCREEN_WIDTH // 2 - pause_text.get_width() // 2,
                 self.SCREEN_HEIGHT // 2 - pause_text.get_height() // 2),
            )

        pygame.display.flip()

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    def toggle_pause(self) -> None:
        self._paused = not self._paused

    def set_speed(self, mult: float) -> None:
        self._speed_mult = mult

    def spawn_entity(self, label: str) -> None:
        self._spawner.spawn_entity(label)
        self._event_log.append(f"SPAWNED {label} (manual)")

    def reset(self) -> None:
        self._build_simulation()
        self._event_log.clear()
        self._detection_summary.clear()
        self._paused = False

    def quit(self) -> None:
        self._running = False

    @property
    def scenario(self) -> Scenario:
        return self._scenario

    @property
    def fc(self):
        return self._fc

    @property
    def screen(self):
        return self._screen
```

```python
# src/sim/injector.py
from __future__ import annotations

import pygame


class EventInjector:
    """Handles keyboard events for the SimTestbench."""

    def __init__(self, testbench) -> None:
        self._tb = testbench

    def handle_key(self, key: int) -> None:
        if key == pygame.K_SPACE:
            self._tb.toggle_pause()
        elif key == pygame.K_s:
            self._tb.spawn_entity("shark")
        elif key == pygame.K_w:
            self._tb.spawn_entity("swimmer")
        elif key == pygame.K_f:
            self._tb.spawn_entity("surfer")
        elif key == pygame.K_r:
            self._tb.reset()
        elif key == pygame.K_ESCAPE:
            self._tb.quit()
        elif key == pygame.K_p:
            self._save_screenshot()
        elif key == pygame.K_b:
            self._open_bug_capture()
        elif key == pygame.K_1:
            self._tb.set_speed(1.0)
        elif key == pygame.K_2:
            self._tb.set_speed(2.0)
        elif key == pygame.K_3:
            self._tb.set_speed(5.0)

    def _save_screenshot(self) -> None:
        import os
        from datetime import datetime
        screenshots_dir = Path("screenshots")
        screenshots_dir.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = screenshots_dir / f"{self._tb.scenario.name}_{ts}.png"
        pygame.image.save(self._tb.screen, str(path))
        print(f"Screenshot saved: {path}")

    def _open_bug_capture(self) -> None:
        from sim.text_input import TextInput
        from sim.bug_capture import capture_bug

        self._tb.pause()
        dialog = TextInput(self._tb.screen, "What went wrong?")
        clock = pygame.time.Clock()

        while not dialog.is_done():
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return
                dialog.handle_event(event)

            # Redraw frame with dialog overlay
            # (reuse current frame draw, then overlay dialog)
            self._tb._draw_frame()
            dialog.draw()
            pygame.display.flip()
            clock.tick(30)

        if not dialog.cancelled and dialog.text.strip():
            capture_bug(self._tb, dialog.text.strip())
```


```python
# src/sim/__main__.py
"""CLI entry point: python -m sim <scenario.yaml>"""
from __future__ import annotations

import sys
from pathlib import Path

from sim.testbench import SimTestbench


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python -m sim <scenario.yaml>", file=sys.stderr)
        return 1

    scenario_path = Path(sys.argv[1])
    if not scenario_path.exists():
        print(f"Scenario file not found: {scenario_path}", file=sys.stderr)
        return 1

    tb = SimTestbench(scenario_path)
    tb.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run smoke test**

Run: `uv run pytest tests/sim/test_testbench_basic.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/sim/testbench.py src/sim/injector.py src/sim/__main__.py tests/sim/test_testbench_basic.py
git commit -m "feat: sim testbench main orchestrator with pygame event loop"
```

---

### Task 7: Bug Capture

**Files:**
- Create: `src/sim/bug_capture.py`

**Interfaces:**
- Consumes: `SimTestbench`, `Scenario`, `Recorder`
- Produces: YAML snapshot file in `scenarios/bugs/`

- [ ] **Step 1: Write the test**

```python
# tests/sim/test_bug_capture.py
from __future__ import annotations

import pytest
import tempfile
from pathlib import Path

from sim.bug_capture import BugSnapshot, capture_bug_snapshot


class TestBugSnapshot:
    def test_snapshot_creation(self):
        snapshot = BugSnapshot(
            name="test-bug",
            captured_at=45.2,
            user_description="The drone didn't react",
            requirements=[],
            scenario={"sea_polygon": {"vertices": [[0, 0], [10, 0]]}, "zones": []},
            drone_pose={"x": 5, "y": 5, "z": 5},
            mission_state={"mission_clock": 45.2, "waypoints_completed": 12},
        )
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False, mode="w") as f:
            path = f.name
            snapshot.save(path)
        loaded = BugSnapshot.load(path)
        assert loaded.name == "test-bug"
        assert loaded.captured_at == 45.2
        assert loaded.user_description == "The drone didn't react"
        Path(path).unlink()
```

- [ ] **Step 2: Run test (fails initially)**

- [ ] **Step 3: Write the implementation**

```python
# src/sim/bug_capture.py
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


BUGS_DIR = Path("scenarios") / "bugs"


@dataclass
class BugSnapshot:
    """A snapshot of a scenario at the moment a bug was captured."""
    name: str
    captured_at: float
    user_description: str
    requirements: list[str]
    scenario: dict
    drone_pose: dict
    mission_state: dict

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False)

    @classmethod
    def load(cls, path: str | Path) -> BugSnapshot:
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls(**data)


def capture_bug(testbench, description: str) -> str:
    """Capture the current testbench state as a bug snapshot YAML.

    Returns the path to the saved snapshot file.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = description.lower().replace(" ", "-")[:30]
    filename = f"{timestamp}-{safe_name}.yaml"
    path = BUGS_DIR / filename

    state = testbench._loop._state if testbench._loop._state else None

    snapshot = BugSnapshot(
        name=f"bug-{safe_name}",
        captured_at=state.mission_clock if state else 0.0,
        user_description=description,
        requirements=[],
        scenario={
            "sea_polygon": testbench._scenario.sea_polygon,
            "zones": [asdict(z) for z in testbench._scenario.zones],
            "detections": {
                "spawners": [
                    asdict(s) for s in testbench._scenario.detections["spawners"]
                ],
            },
        },
        drone_pose={
            "x": testbench.fc.get_pose().x,
            "y": testbench.fc.get_pose().y,
            "z": testbench.fc.get_pose().z,
        },
        mission_state={
            "mission_clock": state.mission_clock if state else 0.0,
            "waypoints_completed": state.waypoints_completed if state else 0,
            "waypoints_total": state.waypoints_total if state else 0,
            "battery": state.battery if state else 1.0,
        },
    )

    snapshot.save(path)
    testbench._event_log.append(f"BUG CAPTURED: {path}")
    print(f"\n[BUG] Captured to {path}")
    return str(path)
```

- [ ] **Step 4: Run test**   

Run: `uv run pytest tests/sim/test_bug_capture.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/sim/bug_capture.py tests/sim/test_bug_capture.py
git commit -m "feat: bug capture snapshot for sim testbench"
```

---

### Task 8: Matplotlib Plotter

**Files:**
- Create: `src/sim/plotter.py`

**Interfaces:**
- Consumes: `Recorder` trace, `Scenario`
- Produces: PNG report figure

- [ ] **Step 1: Write the test**

```python
# tests/sim/test_plotter.py
from __future__ import annotations

import pytest
import tempfile
from pathlib import Path

from drone.interfaces import Pose, Detection, Directive
from sim.recorder import Recorder
from sim.plotter import generate_report


class TestPlotter:
    def test_generate_report_creates_file(self):
        recorder = Recorder(record_interval=0.0)
        recorder.record(0.0, Pose(0, 0, 5, 0), [], Directive(kind="continue"), {"current_idx": 0, "total": 5, "completed": 0})
        recorder.record(1.0, Pose(5, 0, 5, 0), [], None, {"current_idx": 1, "total": 5, "completed": 1})
        recorder.record(2.0, Pose(10, 0, 5, 0), [Detection("shark", 0.9, 45, 10, Pose(15, 5, 0, 0))], Directive(kind="land"), {"current_idx": 2, "total": 5, "completed": 2})

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            path = f.name
            generate_report(recorder, path, mission_name="test-report")
            file_size = Path(path).stat().st_size
            assert file_size > 1000  # should be a real PNG
            Path(path).unlink()
```

- [ ] **Step 2: Run test (fails initially)**

- [ ] **Step 3: Write the implementation**

```python
# src/sim/plotter.py
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # headless

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import Polygon as MplPolygon

from sim.recorder import Recorder, Frame


def generate_report(
    recorder: Recorder,
    output_path: str | Path,
    mission_name: str = "mission",
    sea_polygon: list[list[float]] | None = None,
    zones: list[dict] | None = None,
) -> None:
    """Generate a three-panel matplotlib report figure."""
    trace = recorder.trace()
    if not trace:
        return

    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    fig.suptitle(f"Mission: {mission_name}  |  Duration: {trace[-1].mission_clock:.1f}s",
                 fontsize=14, fontweight="bold")

    # Panel 1: Top-down map
    ax1 = axes[0]
    ax1.set_title("Trajectory & Detections")
    ax1.set_xlabel("X (m)")
    ax1.set_ylabel("Y (m)")
    ax1.grid(True, alpha=0.3)

    # Sea polygon
    if sea_polygon:
        verts = [(v[0], v[1]) for v in sea_polygon]
        poly = MplPolygon(verts, fill=True, alpha=0.1, color="blue", ec="blue", lw=1)
        ax1.add_patch(poly)

    # Zones
    if zones:
        for z in zones:
            zv = [(p[0], p[1]) for p in z.get("polygon", [])]
            if zv:
                zp = MplPolygon(zv, fill=True, alpha=0.15, color="green",
                                ec="green", lw=1, ls="--")
                ax1.add_patch(zp)

    # Trajectory
    xs = [f.drone_pose.x for f in trace]
    ys = [f.drone_pose.y for f in trace]
    ax1.plot(xs, ys, "b-", alpha=0.7, lw=1.5, label="Trajectory")
    ax1.scatter(xs[0], ys[0], c="green", s=80, marker="o", label="Start", zorder=5)
    ax1.scatter(xs[-1], ys[-1], c="red", s=80, marker="x", label="End", zorder=5)

    # Detection markers
    for frame in trace:
        for det in frame.detections:
            color = "red" if "shark" in det.label.lower() else "orange" if "surf" in det.label.lower() else "blue"
            ax1.scatter(det.position.x, det.position.y, c=color, s=30 * det.confidence, alpha=0.6, marker="o")

    ax1.set_aspect("equal")
    ax1.legend(fontsize=8)

    # Panel 2: Detection timeline
    ax2 = axes[1]
    ax2.set_title("Detection Timeline")
    ax2.set_xlabel("Time (s)")
    ax2.set_ylabel("Detections")

    labels_seen: dict[str, list[tuple[float, float]]] = {}
    for frame in trace:
        t = frame.mission_clock
        for det in frame.detections:
            if det.label not in labels_seen:
                labels_seen[det.label] = []
            labels_seen[det.label].append((t, det.confidence))

    colors = {"shark": "red", "swimmer": "blue", "surfer": "orange"}
    for i, (label, points) in enumerate(labels_seen.items()):
        if not points:
            continue
        times = [p[0] for p in points]
        confs = [p[1] for p in points]
        color = colors.get(label, "gray")
        ax2.scatter(times, [i] * len(times), c=confs, cmap="RdYlGn",
                    s=40, vmin=0, vmax=1, alpha=0.8)

    ax2.set_yticks(range(len(labels_seen)))
    ax2.set_yticklabels(labels_seen.keys())

    # Panel 3: Confidence vs Range
    ax3 = axes[2]
    ax3.set_title("Confidence vs Range")
    ax3.set_xlabel("Range (m)")
    ax3.set_ylabel("Confidence")

    for frame in trace:
        for det in frame.detections:
            color = colors.get(det.label, "gray")
            ax3.scatter(det.range, det.confidence, c=color, alpha=0.5, s=20)

    ax3.grid(True, alpha=0.3)
    ax3.set_xlim(0, None)
    ax3.set_ylim(0, 1.1)

    plt.tight_layout()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
```

- [ ] **Step 4: Run test**

Run: `uv run pytest tests/sim/test_plotter.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/sim/plotter.py tests/sim/test_plotter.py
git commit -m "feat: matplotlib post-mission report generator"
```

---

### Task 9: Scenario YAML Files

**Files:**
- Create: `scenarios/swim_patrol.yaml`
- Create: `scenarios/shark_warning.yaml`
- Create: `scenarios/multiple_threats.yaml`
- Create: `scenarios/false_alarm.yaml`
- Create: `scenarios/all_clear.yaml`

- [ ] **Step 1: Create swim_patrol.yaml**

```yaml
# scenarios/swim_patrol.yaml
name: "swim-patrol"
description: "Drone patrols swim zone, detects swimmer drifting outside"
sea_polygon:
  vertices: [[0, 0], [120, 0], [140, 90], [70, 130], [-30, 70]]
zones:
  - id: "swim-zone"
    label: "swim_area"
    polygon: [[5, 5], [35, 5], [40, 35], [10, 40]]
    color: [0, 200, 255, 80]
  - id: "surf-zone"
    label: "surf_area"
    polygon: [[80, 10], [115, 15], [100, 55], [70, 45]]
    color: [255, 200, 0, 80]
navigation:
  algorithm: "perimeter_sweep"
  altitude: 5.0
  offset: 3.0
agent:
  type: "fake"
  responses: []
detections:
  spawners:
    - label: "swimmer"
      pool: "inside_zone(swim-zone)"
      count: 3
      start_time: 0.0
      interval: 0.0
      speed: 0.3
    - label: "surfer"
      pool: "inside_zone(surf-zone)"
      count: 2
      start_time: 0.0
      interval: 0.0
      speed: 1.0
max_duration: 120.0
```

- [ ] **Step 2: Create shark_warning.yaml**

```yaml
# scenarios/shark_warning.yaml
name: "shark-warning"
description: "Shark detected at low confidence, drone approaches to confirm, warns swimmers"
sea_polygon:
  vertices: [[0, 0], [100, 0], [120, 80], [60, 120], [-20, 60]]
zones:
  - id: "swim-zone"
    label: "swim_area"
    polygon: [[10, 10], [40, 10], [45, 40], [15, 45]]
    color: [0, 200, 255, 80]
  - id: "surf-zone"
    label: "surf_area"
    polygon: [[70, 10], [100, 15], [90, 50], [65, 40]]
    color: [255, 200, 0, 80]
navigation:
  algorithm: "perimeter_sweep"
  altitude: 5.0
  offset: 2.0
agent:
  type: "fake"
  responses: []
detections:
  spawners:
    - label: "swimmer"
      pool: "inside_zone(swim-zone)"
      count: 2
      start_time: 0.0
      interval: 0.0
      speed: 0.3
    - label: "surfer"
      pool: "inside_zone(surf-zone)"
      count: 1
      start_time: 0.0
      interval: 0.0
      speed: 1.0
    - label: "shark"
      pool: "inside_polygon(sea_polygon)"
      count: 1
      start_time: 15.0
      interval: 0.0
      speed: 1.5
priority_rules:
  - label: "shark"
    min_confidence: 0.7
    reason: "shark detected near swimmers"
max_duration: 180.0
```

- [ ] **Step 3: Create multiple_threats.yaml**

```yaml
# scenarios/multiple_threats.yaml
name: "multiple-threats"
description: "Multiple sharks and distractions — tests priority resolution"
sea_polygon:
  vertices: [[0, 0], [150, 0], [170, 100], [80, 140], [-30, 80]]
zones:
  - id: "swim-zone"
    label: "swim_area"
    polygon: [[5, 5], [45, 5], [50, 45], [10, 50]]
    color: [0, 200, 255, 80]
  - id: "surf-zone"
    label: "surf_area"
    polygon: [[100, 10], [140, 20], [120, 60], [85, 50]]
    color: [255, 200, 0, 80]
navigation:
  algorithm: "perimeter_sweep"
  altitude: 5.0
  offset: 3.0
agent:
  type: "fake"
  responses: []
detections:
  spawners:
    - label: "swimmer"
      pool: "inside_zone(swim-zone)"
      count: 3
      start_time: 0.0
      interval: 0.0
      speed: 0.3
    - label: "surfer"
      pool: "inside_zone(surf-zone)"
      count: 2
      start_time: 0.0
      interval: 0.0
      speed: 1.0
    - label: "shark"
      pool: "inside_polygon(sea_polygon)"
      count: 1
      start_time: 10.0
      interval: 0.0
      speed: 2.0
    - label: "shark"
      pool: "inside_polygon(sea_polygon)"
      count: 1
      start_time: 25.0
      interval: 0.0
      speed: 1.8
priority_rules:
  - label: "shark"
    min_confidence: 0.7
    reason: "shark detected"
max_duration: 200.0
```

- [ ] **Step 4: Create false_alarm.yaml**

```yaml
# scenarios/false_alarm.yaml
name: "false-alarm"
description: "Shark detected at low confidence but moves out of range — agent should not chase"
sea_polygon:
  vertices: [[0, 0], [150, 0], [180, 100], [90, 150], [-40, 80]]
zones:
  - id: "swim-zone"
    label: "swim_area"
    polygon: [[10, 10], [50, 10], [55, 50], [15, 55]]
    color: [0, 200, 255, 80]
  - id: "surf-zone"
    label: "surf_area"
    polygon: [[110, 15], [145, 25], [125, 70], [95, 55]]
    color: [255, 200, 0, 80]
navigation:
  algorithm: "perimeter_sweep"
  altitude: 5.0
  offset: 3.0
agent:
  type: "fake"
  responses: []
detections:
  spawners:
    - label: "swimmer"
      pool: "inside_zone(swim-zone)"
      count: 2
      start_time: 0.0
      interval: 0.0
      speed: 0.3
    - label: "surfer"
      pool: "inside_zone(surf-zone)"
      count: 1
      start_time: 0.0
      interval: 0.0
      speed: 1.0
    - label: "shark"
      pool: "inside_polygon(sea_polygon)"
      count: 1
      start_time: 20.0
      interval: 0.0
      speed: 3.5  # fast moving — will leave sensor range quickly
priority_rules:
  - label: "shark"
    min_confidence: 0.7
    reason: "shark detected"
max_duration: 150.0
```

- [ ] **Step 5: Create all_clear.yaml**

```yaml
# scenarios/all_clear.yaml
name: "all-clear"
description: "Normal patrol — no threats, drone completes full perimeter sweep"
sea_polygon:
  vertices: [[0, 0], [80, 0], [100, 60], [50, 100], [-10, 50]]
zones:
  - id: "swim-zone"
    label: "swim_area"
    polygon: [[5, 5], [25, 5], [30, 25], [8, 28]]
    color: [0, 200, 255, 80]
  - id: "surf-zone"
    label: "surf_area"
    polygon: [[60, 5], [80, 10], [70, 35], [55, 30]]
    color: [255, 200, 0, 80]
navigation:
  algorithm: "perimeter_sweep"
  altitude: 5.0
  offset: 2.0
agent:
  type: "fake"
  responses: []
detections:
  spawners:
    - label: "swimmer"
      pool: "inside_zone(swim-zone)"
      count: 2
      start_time: 0.0
      interval: 0.0
      speed: 0.2
    - label: "surfer"
      pool: "inside_zone(surf-zone)"
      count: 1
      start_time: 0.0
      interval: 0.0
      speed: 0.8
max_duration: 180.0
```

- [ ] **Step 6: Commit**

```bash
git add scenarios/
git commit -m "feat: five demo scenarios for sim testbench"
```

---

### Task 10: bug_to_task CLI Integration

**Files:**
- Create: `src/sim/bug_to_task.py`

**Interfaces:**
- Consumes: `BugSnapshot`, factory orchestrator's `plan_to_tasks` module
- Produces: A factory task file

- [ ] **Step 1: Write the test**

```python
# tests/sim/test_bug_to_task.py
from __future__ import annotations

import pytest
import tempfile
from pathlib import Path

from sim.bug_to_task import bug_snapshot_to_task


class TestBugToTask:
    def test_generates_task_yaml(self):
        content = {
            "name": "bug-test",
            "captured_at": 30.0,
            "user_description": "Test bug",
            "requirements": [],
            "scenario": {"sea_polygon": {"vertices": [[0, 0], [10, 0]]}},
            "drone_pose": {"x": 5, "y": 5, "z": 5},
            "mission_state": {"mission_clock": 30.0},
        }
        # Verify the function accepts a dict with the right shape
        from sim.bug_to_task import build_task_description
        desc = build_task_description(content)
        assert "test" in desc.lower()
        assert "30.0" in desc
```

- [ ] **Step 2: Run test (fails initially)**

- [ ] **Step 3: Write the implementation**

```python
# src/sim/bug_to_task.py
"""CLI tool: convert a bug snapshot to a factory task."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


def build_task_description(snapshot_data: dict) -> str:
    """Build a human-readable task description from a bug snapshot."""
    name = snapshot_data.get("name", "unknown")
    desc = snapshot_data.get("user_description", "No description")
    clock = snapshot_data.get("captured_at", 0.0)
    pose = snapshot_data.get("drone_pose", {})
    mission = snapshot_data.get("mission_state", {})

    lines = [
        f"# Bug: {name}",
        "",
        f"**Captured at t={clock:.1f}s**",
        "",
        f"**Description:** {desc}",
        "",
        "## Mission State at Capture",
        f"- Drone position: ({pose.get('x', '?')}, {pose.get('y', '?')}, {pose.get('z', '?')})",
        f"- Mission clock: {mission.get('mission_clock', '?')}s",
        f"- Waypoints: {mission.get('waypoints_completed', '?')}/{mission.get('waypoints_total', '?')}",
        f"- Battery: {mission.get('battery', '?')}",
        "",
        "## How to Reproduce",
        "1. Run the simulation testbench with the original scenario",
        "2. The bug occurs at the captured mission time",
        "3. See the bug snapshot YAML for exact state",
        "",
        "## Acceptance Criteria",
        f"- [ ] Fix the issue described: {desc}",
        "- [ ] Re-run the bug scenario to verify the fix",
        "- [ ] The scenario completes without the described issue",
    ]
    return "\n".join(lines)


def bug_to_task(bug_path: str | Path) -> str:
    """Convert a bug snapshot YAML to a factory task file.

    Returns the path to the created task file.
    """
    bug_path = Path(bug_path)
    if not bug_path.exists():
        raise FileNotFoundError(f"Bug snapshot not found: {bug_path}")

    with open(bug_path) as f:
        snapshot = yaml.safe_load(f)

    description = build_task_description(snapshot)
    task_name = snapshot.get("name", "bug-fix").replace(" ", "-")

    tasks_dir = Path("tasks")
    tasks_dir.mkdir(exist_ok=True)
    task_path = tasks_dir / f"T-{task_name}.md"

    with open(task_path, "w") as f:
        f.write(description)

    print(f"Task created: {task_path}")
    print(f"  To add it to the factory ledger, run:")
    print(f"  python -m factory.orchestrator.plan_to_tasks {task_path}")
    return str(task_path)


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python -m sim.bug_to_task <bug-snapshot.yaml>", file=sys.stderr)
        return 1

    try:
        bug_to_task(sys.argv[1])
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test**

Run: `uv run pytest tests/sim/test_bug_to_task.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/sim/bug_to_task.py tests/sim/test_bug_to_task.py
git commit -m "feat: bug_to_task CLI for converting bug snapshots to factory tasks"
```

---

### Task 11: Pytest Marker Update and Smoke Test

**Files:**
- Modify: `pyproject.toml` (add `sim` marker if not present)
- Create: `tests/sim/test_smoke.py`

- [ ] **Step 1: Check pyproject.toml for markers**

Run: `grep -A5 'markers' pyproject.toml`
Expected: shows existing markers (`unit`, `agent`, `sim`)

If `sim` marker exists, no change needed. If not:
```toml
# In pyproject.toml, add to [tool.pytest.ini_options] markers:
# "sim: simulation testbench tests",
```

- [ ] **Step 2: Write smoke test**

```python
# tests/sim/test_smoke.py
from __future__ import annotations

import pytest

pytestmark = pytest.mark.sim


class TestSimSmoke:
    """Smoke tests that verify the full sim testbench can initialize."""

    def test_import_all_modules(self):
        """All sim modules import without error."""
        from sim import scenario
        from sim import detection_spawner
        from sim import recorder
        from sim import text_input
        from sim import renderer
        from sim import hud
        from sim import testbench
        from sim import injector
        from sim import bug_capture
        from sim import plotter
        from sim import bug_to_task
        assert True

    def test_load_all_scenarios(self):
        """All scenario YAML files load correctly."""
        from sim.scenario import Scenario
        from pathlib import Path
        scenario_dir = Path("scenarios")
        yaml_files = list(scenario_dir.glob("*.yaml"))
        assert len(yaml_files) >= 5, f"Expected >=5 scenarios, found {len(yaml_files)}"
        for path in yaml_files:
            scenario = Scenario.load(str(path))
            assert scenario.name, f"Scenario missing name: {path}"
            assert scenario.sea_polygon, f"Scenario missing sea_polygon: {path}"
```

- [ ] **Step 3: Run smoke test**

Run: `uv run pytest tests/sim/test_smoke.py -m sim -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tests/sim/test_smoke.py
git commit -m "test: sim testbench smoke tests (imports + scenario validation)"
```

---

### Task 12: Update Factory Gate Scripts

**Files:**
- Modify: `scripts/gates/sim_smoke.py` (update if it exists, otherwise create)
- Modify: `scripts/gates/all.py` (add sim gate if missing)

- [ ] **Step 1: Read existing gate scripts**

Run: `cat scripts/gates/sim_smoke.py`
If the file exists and already runs `pytest -m sim`, no change needed.

- [ ] **Step 2: Create or update sim_smoke.py**

```python
# scripts/gates/sim_smoke.py
"""Run sim-level tests (testbench, mission loop with fake FC)."""
from __future__ import annotations

import subprocess
import sys


def main() -> int:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-m", "sim", "-v", "--tb=short"],
        capture_output=False,
    )
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Commit**

```bash
git add scripts/gates/sim_smoke.py
git commit -m "chore: add sim smoke gate script for testbench tests"
```

---

### Self-Review Checklist

1. **Spec coverage:** All sections of the spec are covered: scenario YAML (Task 1, 9), detection spawner (Task 2), recorder (Task 3), text input (Task 4), renderer/HUD (Task 5), testbench main loop (Task 6), bug capture (Task 7), plotter (Task 8), bug_to_task (Task 10), pytest markers (Task 11), gate scripts (Task 12).

2. **Placeholder scan:** Every step contains actual code. No TBD, TODO, or "implement later".

3. **Type consistency:** All interfaces use `drone.interfaces` types (Pose, Detection, etc.). Function signatures match across tasks — e.g. `DetectionSpawner.get_detections()` returns `list[Detection]` everywhere it's consumed.
