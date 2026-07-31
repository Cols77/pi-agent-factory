# Mission Agent & Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the drone mission "brain" — a stateful LLM-backed agent that receives mission context, uses tools to plan and update navigation, and issues directives that a waypoint sequencer translates into flight controller calls.

**Architecture:** Three-rhythm mission loop (fast tick, heartbeat, event interrupt) with a clear separation: the agent never drives the flight controller directly — it returns Directives; the DirectiveExecutor translates those into WaypointSequencer/FlightController actions. NavigationAlgorithm registry with one concrete implementation (PerimeterSweep). ScriptedPerception + FakeAgent for deterministic testing.

**Tech Stack:** Python 3.11+, pytest, anthropic SDK, google-genai SDK, openai SDK

## Global Constraints

- Python ≥3.11, <3.13
- All new types in `src/drone/interfaces.py` unless otherwise specified
- Test markers: `unit` (fast deterministic), `agent` (mocked LLM), `sim` (pybullet)
- Default pytest runs `-m unit` only; gate adds `-m agent` after unit
- LLM API errors → fallback `Directive(kind="continue")`
- Battery <10% → auto-land, bypasses agent
- Tool implementations are pure functions — no side effects until mission loop acts on Directive
- `@dataclass(frozen=True)` for all value types
- `@runtime_checkable` for Protocol types

## File Structure

```
src/drone/
  interfaces.py              # CREATE: all core types (Pose, Detection, WaterArea, NavPlan, Directive, etc.)
  fake_flight_controller.py  # CREATE: FakeFlightController for testing
  mission/
    __init__.py               # CREATE: package init, re-exports
    state.py                  # CREATE: MissionState accumulator
    loop.py                   # CREATE: MissionLoop + MissionResult
    priority_filter.py        # CREATE: PriorityFilter + PriorityRule + DetectionEvent
    scripted_perception.py    # CREATE: ScriptedPerception
    fake_agent.py             # CREATE: FakeAgent
    llm_agent.py              # CREATE: LlmAgent + ModelConfig + ProviderAdapter protocol
    tools.py                  # CREATE: tool implementations (pure functions)
    directive_executor.py     # CREATE: DirectiveExecutor
  navigation/
    __init__.py               # CREATE: package init, re-exports
    waypoint_sequencer.py     # CREATE: WaypointSequencer
    registry.py               # CREATE: NavRegistry
    perimeter_sweep.py        # CREATE: PerimeterSweepAlgorithm

tests/
  unit/
    drone/
      test_interfaces.py          # CREATE: unit tests for core types
      test_mission_state.py        # CREATE: unit tests for MissionState
      test_waypoint_sequencer.py   # CREATE: unit tests for WaypointSequencer
      test_perimeter_sweep.py     # CREATE: unit tests for PerimeterSweep
      test_priority_filter.py     # CREATE: unit tests for PriorityFilter
      test_directive.py           # CREATE: unit tests for Directive validation
      test_nav_registry.py        # CREATE: unit tests for NavRegistry
  agent/
    test_fake_agent.py            # CREATE: FakeAgent tests
    test_agent_scenarios.py       # CREATE: scenario tests with mocked LLM
    test_llm_agent.py             # CREATE: LlmAgent unit tests (mocked providers)
    test_directive_executor.py    # CREATE: DirectiveExecutor tests
  integration/
    test_mission_loop.py          # CREATE: full MissionLoop integration test
```

---

### Task 1: Core Data Types & FakeFlightController

**Files:**
- Create: `src/drone/interfaces.py`
- Create: `src/drone/fake_flight_controller.py`
- Create: `tests/unit/drone/test_interfaces.py`

**Interfaces:**
- Consumes: nothing (base layer)
- Produces: `Pose`, `Detection`, `Command`, `FlightController` (Protocol), `Perception` (Protocol), `WaterArea`, `NavPlan`, `Directive`, `NavContext`, `MissionPlanner` (Protocol), `NavigationAlgorithm` (Protocol), `PriorityRule`, `DetectionEvent`, `ModelConfig`

- [ ] **Step 1: Write failing tests for core types**

```python
# tests/unit/drone/test_interfaces.py
"""Unit tests for core data types in src/drone/interfaces.py."""
from __future__ import annotations

import pytest
from dataclasses import FrozenInstanceError


class TestPose:
    def test_construct(self):
        from drone.interfaces import Pose
        p = Pose(x=1.0, y=2.0, z=3.0, heading=90.0)
        assert p.x == 1.0
        assert p.y == 2.0
        assert p.z == 3.0
        assert p.heading == 90.0

    def test_frozen(self):
        from drone.interfaces import Pose
        p = Pose(x=0, y=0, z=0, heading=0)
        with pytest.raises(FrozenInstanceError):
            p.x = 5  # type: ignore[misc]

    def test_defaults(self):
        from drone.interfaces import Pose
        p = Pose()
        assert p.x == 0.0 and p.y == 0.0 and p.z == 0.0 and p.heading == 0.0


class TestDetection:
    def test_construct(self):
        from drone.interfaces import Detection
        d = Detection(label="distress", confidence=0.9, bearing=45.0, range=10.0, position=Pose(x=5, y=5, z=0, heading=0))
        assert d.label == "distress"
        assert d.confidence == 0.9

    def test_frozen(self):
        from drone.interfaces import Detection
        d = Detection(label="boat", confidence=0.5, bearing=0, range=0, position=Pose())
        with pytest.raises(FrozenInstanceError):
            d.label = "ship"  # type: ignore[misc]


class TestCommand:
    def test_construct(self):
        from drone.interfaces import Command
        c = Command(action="goto", x=1.0, y=2.0, z=3.0)
        assert c.action == "goto"

    def test_frozen(self):
        from drone.interfaces import Command
        c = Command(action="hover")
        with pytest.raises(FrozenInstanceError):
            c.action = "land"  # type: ignore[misc]


class TestWaterArea:
    def test_construct(self):
        from drone.interfaces import WaterArea
        w = WaterArea(vertices=[(0, 0), (10, 0), (10, 10), (0, 10)])
        assert len(w.vertices) == 4

    def test_frozen(self):
        from drone.interfaces import WaterArea
        w = WaterArea(vertices=[(0, 0), (1, 0), (1, 1)])
        with pytest.raises(FrozenInstanceError):
            w.vertices = []  # type: ignore[misc]


class TestNavPlan:
    def test_construct(self):
        from drone.interfaces import NavPlan, Pose
        w = [Pose(0, 0, 5, 0), Pose(10, 0, 5, 0)]
        np = NavPlan(waypoints=w, algorithm_name="perimeter_sweep", created_at=1.5)
        assert np.algorithm_name == "perimeter_sweep"
        assert np.created_at == 1.5
        assert len(np.waypoints) == 2


class TestDirective:
    def test_update_nav(self):
        from drone.interfaces import Directive, NavPlan, Pose
        plan = NavPlan(waypoints=[Pose()], algorithm_name="test", created_at=0)
        d = Directive(kind="update_nav", args={"nav_plan": plan})
        assert d.kind == "update_nav"
        assert d.args["nav_plan"] == plan

    def test_continue(self):
        from drone.interfaces import Directive
        d = Directive(kind="continue")
        assert d.kind == "continue"
        assert d.args == {}

    def test_land(self):
        from drone.interfaces import Directive
        d = Directive(kind="land")
        assert d.kind == "land"


class TestNavContext:
    def test_construct(self):
        from drone.interfaces import NavContext, Pose
        ctx = NavContext(current_pose=Pose(1, 2, 3, 0), completed_area=[(0, 0), (1, 1)])
        assert ctx.current_pose.x == 1


class TestPriorityRule:
    def test_construct(self):
        from drone.interfaces import PriorityRule
        r = PriorityRule(label="distress", min_confidence=0.8, reason_template="possible {label}")
        assert r.label == "distress"
        assert r.min_confidence == 0.8


class TestDetectionEvent:
    def test_construct(self):
        from drone.interfaces import DetectionEvent, Detection, Pose
        det = Detection(label="distress", confidence=0.9, bearing=0, range=0, position=Pose())
        ev = DetectionEvent(detection=det, reason="possible distress")
        assert ev.reason == "possible distress"


class TestModelConfig:
    def test_construct(self):
        from drone.interfaces import ModelConfig
        mc = ModelConfig(provider="google", model="gemini-flash", api_key="key123")
        assert mc.provider == "google"


class TestProtocols:
    def test_flight_controller_is_protocol(self):
        from drone.interfaces import FlightController
        assert hasattr(FlightController, "__protocol_attrs__") or hasattr(FlightController, "__abstractmethods__") or hasattr(FlightController, "__subclasshook__")

    def test_perception_is_protocol(self):
        from drone.interfaces import Perception
        assert hasattr(Perception, "__protocol_attrs__") or hasattr(Perception, "__abstractmethods__") or hasattr(Perception, "__subclasshook__")

    def test_mission_planner_is_protocol(self):
        from drone.interfaces import MissionPlanner
        assert hasattr(MissionPlanner, "__protocol_attrs__") or hasattr(MissionPlanner, "__abstractmethods__") or hasattr(MissionPlanner, "__subclasshook__")

    def test_navigation_algorithm_is_protocol(self):
        from drone.interfaces import NavigationAlgorithm
        assert hasattr(NavigationAlgorithm, "__protocol_attrs__") or hasattr(NavigationAlgorithm, "__abstractmethods__") or hasattr(NavigationAlgorithm, "__subclasshook__")


class TestFakeFlightController:
    def test_initial_state(self):
        from drone.fake_flight_controller import FakeFlightController
        fc = FakeFlightController()
        assert fc.get_battery() == 1.0
        assert fc.is_armed() is False

    def test_arm_takeoff(self):
        from drone.fake_flight_controller import FakeFlightController
        fc = FakeFlightController()
        fc.arm()
        assert fc.is_armed() is True
        fc.takeoff(altitude=5.0)
        fc.step(0.1)
        assert fc.get_pose().z > 0

    def test_goto_and_step(self):
        from drone.fake_flight_controller import FakeFlightController
        fc = FakeFlightController()
        fc.arm()
        fc.takeoff(altitude=5.0)
        for _ in range(200):
            fc.step(0.05)
        fc.goto(10.0, 5.0, 5.0)
        for _ in range(200):
            fc.step(0.05)
        pose = fc.get_pose()
        assert abs(pose.x - 10.0) < 1.0
        assert abs(pose.y - 5.0) < 1.0

    def test_land(self):
        from drone.fake_flight_controller import FakeFlightController
        fc = FakeFlightController()
        fc.arm()
        fc.takeoff(altitude=5.0)
        for _ in range(200):
            fc.step(0.05)
        fc.land()
        for _ in range(200):
            fc.step(0.05)
        assert fc.get_pose().z < 0.1

    def test_battery_drains(self):
        from drone.fake_flight_controller import FakeFlightController
        fc = FakeFlightController()
        fc.arm()
        fc.takeoff(altitude=5.0)
        for _ in range(200):
            fc.step(0.05)
        initial_battery = fc.get_battery()
        fc.goto(50.0, 50.0, 5.0)
        for _ in range(400):
            fc.step(0.05)
        assert fc.get_battery() < initial_battery

    def test_satisfies_flight_controller_protocol(self):
        from drone.interfaces import FlightController
        from drone.fake_flight_controller import FakeFlightController
        fc = FakeFlightController()
        assert isinstance(fc, FlightController)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/drone/test_interfaces.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'drone'`

- [ ] **Step 3: Implement interfaces.py**

```python
# src/drone/__init__.py
"""Drone mission system."""
```

```python
# src/drone/interfaces.py
"""Core data types and protocols for the drone mission system."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Pose:
    """3D position + heading."""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    heading: float = 0.0


@dataclass(frozen=True)
class Detection:
    """A detected object."""
    label: str
    confidence: float
    bearing: float
    range: float
    position: Pose


@dataclass(frozen=True)
class Command:
    """Simple reactive command."""
    action: str  # "goto", "hover", "land"
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


@dataclass(frozen=True)
class WaterArea:
    """2D polygon representing the water boundary."""
    vertices: list[tuple[float, float]]



@dataclass(frozen=True)
class NavPlan:
    """Named sequence of waypoints for the sequencer to follow."""
    waypoints: list[Pose]
    algorithm_name: str
    created_at: float


@dataclass(frozen=True)
class Directive:
    """Agent output — what the mission loop should do next."""
    kind: str  # "update_nav", "override", "continue", "land", "return_base"
    args: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class NavContext:
    """Context for navigation planning."""
    current_pose: Pose
    completed_area: list[tuple[float, float]]


@dataclass(frozen=True)
class PriorityRule:
    """Rule for detecting high-priority events."""
    label: str
    min_confidence: float
    reason_template: str


@dataclass(frozen=True)
class DetectionEvent:
    """A detection that triggered a priority rule."""
    detection: Detection
    reason: str


@dataclass(frozen=True)
class ModelConfig:
    """Configuration for a single LLM model."""
    provider: str   # "google" | "anthropic" | "openrouter" | "openai_compat"
    model: str
    api_key: str


@runtime_checkable
class FlightController(Protocol):
    """Flight hardware abstraction."""
    def arm(self) -> None: ...
    def takeoff(self, altitude: float) -> None: ...
    def land(self) -> None: ...
    def goto(self, x: float, y: float, z: float) -> None: ...
    def step(self, dt: float) -> None: ...
    def get_pose(self) -> Pose: ...
    def get_battery(self) -> float: ...
    def is_armed(self) -> bool: ...


@runtime_checkable
class Perception(Protocol):
    """Perception abstraction."""
    def get_detections(self) -> list[Detection]: ...


@runtime_checkable
class MissionPlanner(Protocol):
    """Stateful agent — called with full mission context."""
    def decide(self, state: MissionState) -> Directive: ...


# Forward reference — MissionState is defined in mission/state.py
# The type checker resolves this; runtime uses the actual class.
# We import it here for the Protocol annotation.
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from drone.mission.state import MissionState


@runtime_checkable
class NavigationAlgorithm(Protocol):
    """Generates a NavPlan from a water area and current context."""
    def plan(self, water: WaterArea, context: NavContext) -> NavPlan: ...
```

- [ ] **Step 4: Implement FakeFlightController**

```python
# src/drone/fake_flight_controller.py
"""Deterministic fake flight controller for testing."""
from __future__ import annotations

from drone.interfaces import FlightController, Pose


class FakeFlightController:
    """Simple kinematic fake FC — moves toward targets at fixed speed."""

    SPEED: float = 5.0        # m/s horizontal
    VERTICAL_SPEED: float = 2.0  # m/s vertical
    BATTERY_DRAIN: float = 0.0001  # per step while armed

    def __init__(self) -> None:
        self._pose = Pose(x=0.0, y=0.0, z=0.0, heading=0.0)
        self._armed: bool = False
        self._target_x: float = 0.0
        self._target_y: float = 0.0
        self._target_z: float = 0.0
        self._landing: bool = False
        self._battery: float = 1.0

    def arm(self) -> None:
        self._armed = True

    def takeoff(self, altitude: float) -> None:
        if not self._armed:
            raise RuntimeError("Cannot take off — not armed")
        self._target_z = altitude

    def land(self) -> None:
        self._landing = True
        self._target_z = 0.0

    def goto(self, x: float, y: float, z: float) -> None:
        self._target_x = x
        self._target_y = y
        self._target_z = z
        self._landing = False

    def step(self, dt: float) -> None:
        if not self._armed:
            return

        # Move toward target
        dx = self._target_x - self._pose.x
        dy = self._target_y - self._pose.y
        dz = self._target_z - self._pose.z

        h_dist = (dx * dx + dy * dy) ** 0.5
        if h_dist > 0.01:
            move = min(self.SPEED * dt, h_dist)
            self._pose = Pose(
                x=self._pose.x + dx / h_dist * move,
                y=self._pose.y + dy / h_dist * move,
                z=self._pose.z,
                heading=self._pose.heading,
            )

        dz = self._target_z - self._pose.z
        if abs(dz) > 0.01:
            move = min(self.VERTICAL_SPEED * dt, abs(dz))
            self._pose = Pose(
                x=self._pose.x,
                y=self._pose.y,
                z=self._pose.z + move * (1 if dz > 0 else -1),
                heading=self._pose.heading,
            )

        # Battery drain
        if self._armed:
            self._battery = max(0.0, self._battery - self.BATTERY_DRAIN)

    def get_pose(self) -> Pose:
        return self._pose

    def get_battery(self) -> float:
        return self._battery

    def is_armed(self) -> bool:
        return self._armed
```

- [ ] **Step 5: Create package init files**

```python
# src/drone/__init__.py
"""Drone mission system."""
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/unit/drone/test_interfaces.py -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add src/drone/__init__.py src/drone/interfaces.py src/drone/fake_flight_controller.py tests/unit/drone/test_interfaces.py
git commit -m "feat: core drone types (Pose, Detection, WaterArea, NavPlan, Directive, protocols) + FakeFlightController"
```

---

### Task 2: MissionState

**Files:**
- Create: `src/drone/mission/__init__.py`
- Create: `src/drone/mission/state.py`
- Create: `tests/unit/drone/test_mission_state.py`

**Interfaces:**
- Consumes: `Pose`, `Detection`, `NavPlan`, `Directive` from Task 1
- Produces: `MissionState` class with `update()`, `summary()`, `advance_waypoint()`, `set_nav_plan()`, `mark_objective()`

- [ ] **Step 1: Write failing tests for MissionState**

```python
# tests/unit/drone/test_mission_state.py
"""Unit tests for MissionState."""
from __future__ import annotations

import pytest
from drone.interfaces import Pose, Detection, NavPlan, Directive
from drone.mission.state import MissionState


class TestMissionStateConstruction:
    def test_default_construction(self):
        state = MissionState(mission_objectives="Survey water area")
        assert state.mission_objectives == "Survey water area"
        assert state.mission_clock == 0.0
        assert state.nav_plan is None
        assert state.current_waypoint_idx == 0
        assert state.waypoints_completed == 0
        assert state.waypoints_total == 0
        assert state.battery == 1.0
        assert state.action_log == []
        assert state.all_detections == []
        assert state.new_detections == []


class TestMissionStateUpdate:
    def test_update_advances_clock(self):
        state = MissionState(mission_objectives="test")
        state.update(pose=Pose(1, 2, 3, 0), detections=[], last_directive_result=None, dt=0.05)
        assert state.mission_clock == 0.05

    def test_update_accumulates_detections(self):
        state = MissionState(mission_objectives="test")
        det = Detection(label="boat", confidence=0.9, bearing=45, range=10, position=Pose())
        state.update(pose=Pose(), detections=[det], last_directive_result=None, dt=0.05)
        assert len(state.all_detections) == 1
        assert len(state.new_detections) == 1

    def test_update_clears_new_detections_on_next_call(self):
        state = MissionState(mission_objectives="test")
        det1 = Detection(label="boat", confidence=0.9, bearing=0, range=0, position=Pose())
        det2 = Detection(label="ship", confidence=0.8, bearing=0, range=0, position=Pose())
        state.update(pose=Pose(), detections=[det1], last_directive_result=None, dt=0.05)
        assert len(state.new_detections) == 1
        state.update(pose=Pose(), detections=[det2], last_directive_result=None, dt=0.05)
        assert len(state.new_detections) == 1  # only the new one
        assert len(state.all_detections) == 2

    def test_update_records_pose_and_battery(self):
        state = MissionState(mission_objectives="test")
        state.update(pose=Pose(5, 5, 5, 90), detections=[], last_directive_result=None, battery=0.8, dt=0.05)
        assert state.current_pose == Pose(5, 5, 5, 90)
        assert state.battery == 0.8

    def test_update_logs_directive_result(self):
        state = MissionState(mission_objectives="test")
        d = Directive(kind="continue")
        state.update(pose=Pose(), detections=[], last_directive_result="no-op", dt=0.05)
        assert len(state.action_log) == 1
        assert state.action_log[0] == (0.05, "no-op")


class TestMissionStateSummary:
    def test_basic_summary(self):
        state = MissionState(mission_objectives="Survey water")
        s = state.summary()
        assert "MISSION: Survey water" in s
        assert "TIME ELAPSED:" in s
        assert "BATTERY:" in s

    def test_summary_with_detections(self):
        state = MissionState(mission_objectives="test")
        det = Detection(label="distress", confidence=0.95, bearing=90, range=20, position=Pose())
        state.update(pose=Pose(), detections=[det], last_directive_result=None, dt=0.05)
        s = state.summary()
        assert "distress" in s
        assert "HIGH" in s  # 0.95 >= 0.9

    def test_summary_low_confidence(self):
        state = MissionState(mission_objectives="test")
        det = Detection(label="bird", confidence=0.3, bearing=0, range=0, position=Pose())
        state.update(pose=Pose(), detections=[det], last_directive_result=None, dt=0.05)
        s = state.summary()
        assert "LOW" in s  # < 0.5

    def test_summary_medium_confidence(self):
        state = MissionState(mission_objectives="test")
        det = Detection(label="boat", confidence=0.7, bearing=0, range=0, position=Pose())
        state.update(pose=Pose(), detections=[det], last_directive_result=None, dt=0.05)
        s = state.summary()
        assert "MEDIUM" in s  # 0.5-0.9

    def test_summary_battery_critical(self):
        state = MissionState(mission_objectives="test")
        state.update(pose=Pose(), detections=[], last_directive_result=None, battery=0.05, dt=0.05)
        s = state.summary()
        assert "CRITICAL" in s

    def test_summary_nav_plan(self):
        state = MissionState(mission_objectives="test")
        plan = NavPlan(waypoints=[Pose(1, 0, 5, 0), Pose(2, 0, 5, 0)], algorithm_name="perimeter_sweep", created_at=0)
        state.set_nav_plan(plan)
        s = state.summary()
        assert "perimeter_sweep" in s
        assert "0/2" in s

    def test_summary_no_nav_plan(self):
        state = MissionState(mission_objectives="test")
        s = state.summary()
        assert "No active nav plan" in s

    def test_summary_objectives(self):
        state = MissionState(mission_objectives="test")
        state.mark_objective("survey_water", "in_progress")
        s = state.summary()
        assert "survey_water" in s
        assert "in_progress" in s


class TestAdvanceWaypoint:
    def test_advance(self):
        state = MissionState(mission_objectives="test")
        plan = NavPlan(waypoints=[Pose(1, 0, 5, 0), Pose(2, 0, 5, 0), Pose(3, 0, 5, 0)], algorithm_name="test", created_at=0)
        state.set_nav_plan(plan)
        assert state.current_waypoint_idx == 0
        state.advance_waypoint()
        assert state.current_waypoint_idx == 1
        assert state.waypoints_completed == 1

    def test_advance_beyond_end_stays_at_last(self):
        state = MissionState(mission_objectives="test")
        plan = NavPlan(waypoints=[Pose(1, 0, 5, 0)], algorithm_name="test", created_at=0)
        state.set_nav_plan(plan)
        state.advance_waypoint()
        assert state.current_waypoint_idx == 1  # past end
        assert state.waypoints_completed == 1


class TestSetNavPlan:
    def test_set_resets_tracking(self):
        state = MissionState(mission_objectives="test")
        plan1 = NavPlan(waypoints=[Pose(1, 0, 5, 0), Pose(2, 0, 5, 0)], algorithm_name="a", created_at=0)
        state.set_nav_plan(plan1)
        state.advance_waypoint()
        assert state.waypoints_completed == 1
        plan2 = NavPlan(waypoints=[Pose(5, 5, 5, 0)], algorithm_name="b", created_at=1.0)
        state.set_nav_plan(plan2)
        assert state.current_waypoint_idx == 0
        assert state.waypoints_completed == 0
        assert state.waypoints_total == 1
        assert state.nav_plan == plan2


class TestMarkObjective:
    def test_mark(self):
        state = MissionState(mission_objectives="test")
        state.mark_objective("survey_water", "in_progress")
        assert state.objectives_status["survey_water"] == "in_progress"
        state.mark_objective("survey_water", "complete")
        assert state.objectives_status["survey_water"] == "complete"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/drone/test_mission_state.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'drone.mission'`

- [ ] **Step 3: Implement MissionState**

```python
# src/drone/mission/__init__.py
"""Mission subsystem."""
```

```python
# src/drone/mission/state.py
"""MissionState — mutable accumulator, single source of truth for the agent."""
from __future__ import annotations

from drone.interfaces import Pose, Detection, NavPlan, Directive


def _confidence_label(confidence: float) -> str:
    if confidence < 0.5:
        return "LOW"
    if confidence < 0.9:
        return "MEDIUM"
    return "HIGH"


class MissionState:
    """Mutable accumulator — the single source of truth the agent reads."""

    def __init__(self, mission_objectives: str) -> None:
        # Identity
        self.mission_objectives: str = mission_objectives
        self.mission_clock: float = 0.0

        # Perception log
        self.all_detections: list[Detection] = []
        self.new_detections: list[Detection] = []

        # Navigation
        self.nav_plan: NavPlan | None = None
        self.current_waypoint_idx: int = 0
        self.waypoints_completed: int = 0
        self.waypoints_total: int = 0

        # Action history — stores (mission_clock, result_description)
        self.action_log: list[tuple[float, str]] = []

        # Objective tracking
        self.objectives_status: dict[str, str] = {}

        # Drone state
        self.current_pose: Pose = Pose()
        self.battery: float = 1.0

    def update(
        self,
        pose: Pose,
        detections: list[Detection],
        last_directive_result: str | None,
        *,
        dt: float = 0.05,
        battery: float | None = None,
        is_priority: bool = False,
    ) -> None:
        """Ingest new data. Advances clock, accumulates detections."""
        self.mission_clock += dt
        self.current_pose = pose
        if battery is not None:
            self.battery = battery

        # Accumulate detections
        self.new_detections = list(detections)
        self.all_detections.extend(detections)

        # Log directive result
        if last_directive_result is not None:
            self.action_log.append((self.mission_clock, last_directive_result))

    def summary(self) -> str:
        """Produce NL text for the LLM agent."""
        lines: list[str] = []

        lines.append(f"MISSION: {self.mission_objectives}")
        lines.append("")
        lines.append(f"TIME ELAPSED: {self.mission_clock:.1f}s")
        lines.append("")

        # Current status
        status_parts: list[str] = []
        if self.nav_plan is not None:
            status_parts.append(f"Following {self.nav_plan.algorithm_name} plan")
        else:
            status_parts.append("No active navigation plan")
        obj_active = [k for k, v in self.objectives_status.items() if v == "in_progress"]
        if obj_active:
            status_parts.append(f"objectives in progress: {', '.join(obj_active)}")
        lines.append(f"CURRENT STATUS: {'; '.join(status_parts)}")
        lines.append("")

        # Previous actions
        lines.append("PREVIOUS ACTIONS:")
        if self.action_log:
            for clock, desc in self.action_log[-10:]:  # last 10
                lines.append(f"- [{clock:.1f}s] {desc}")
        else:
            lines.append("- (none)")
        lines.append("")

        # New detections
        lines.append("NEW DETECTIONS (since last call):")
        if self.new_detections:
            for det in self.new_detections:
                level = _confidence_label(det.confidence)
                lines.append(
                    f"- {det.label} at bearing {det.bearing:.0f}° "
                    f"range {det.range:.1f}m confidence {det.confidence:.2f} {level}"
                )
        else:
            lines.append("- (none)")
        lines.append("")

        # Detection summary
        lines.append("DETECTION SUMMARY:")
        label_counts: dict[str, list[float]] = {}
        for det in self.all_detections:
            label_counts.setdefault(det.label, []).append(det.confidence)
        for label, confs in label_counts.items():
            total = len(confs)
            high = sum(1 for c in confs if c >= 0.9)
            pending = sum(1 for c in confs if c < 0.5)
            lines.append(f"- {total} {label}(s) detected total, {high} classified ≥0.90, {pending} pending")
        lines.append("")

        # Objectives
        lines.append("OBJECTIVES:")
        if self.objectives_status:
            for obj_id, status in self.objectives_status.items():
                lines.append(f"- {obj_id}: {status}")
        else:
            lines.append("- (none)")
        lines.append("")

        # Nav plan
        lines.append("NAV PLAN:")
        if self.nav_plan is not None:
            lines.append(
                f"{self.nav_plan.algorithm_name}, waypoints "
                f"{self.waypoints_completed}/{self.waypoints_total} complete"
            )
        else:
            lines.append("- [No active nav plan]")
        lines.append("")

        # Battery
        battery_str = f"{self.battery * 100:.0f}%"
        if self.battery < 0.1:
            battery_str += " [CRITICAL]"
        lines.append(f"BATTERY: {battery_str}")

        return "\n".join(lines)

    def advance_waypoint(self) -> None:
        """Called by sequencer when a waypoint is reached."""
        if self.nav_plan is not None and self.current_waypoint_idx < self.waypoints_total:
            self.current_waypoint_idx += 1
            self.waypoints_completed += 1

    def set_nav_plan(self, plan: NavPlan) -> None:
        """Replace the active navigation plan. Resets waypoint tracking."""
        self.nav_plan = plan
        self.current_waypoint_idx = 0
        self.waypoints_completed = 0
        self.waypoints_total = len(plan.waypoints)

    def mark_objective(self, objective_id: str, status: str) -> None:
        """Update an objective's status."""
        self.objectives_status[objective_id] = status
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/drone/test_mission_state.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/drone/mission/__init__.py src/drone/mission/state.py tests/unit/drone/test_mission_state.py
git commit -m "feat: MissionState accumulator with update, summary, waypoint tracking, objectives"
```

---

### Task 3: PriorityFilter

**Files:**
- Create: `src/drone/mission/priority_filter.py`
- Create: `tests/unit/drone/test_priority_filter.py`

**Interfaces:**
- Consumes: `PriorityRule`, `DetectionEvent`, `Detection`, `Pose` from Task 1
- Produces: `PriorityFilter` class with `check()`, `default()` class method

- [ ] **Step 1: Write failing tests for PriorityFilter**

```python
# tests/unit/drone/test_priority_filter.py
"""Unit tests for PriorityFilter."""
from __future__ import annotations

from drone.interfaces import PriorityRule, DetectionEvent, Detection, Pose
from drone.mission.priority_filter import PriorityFilter


class TestPriorityFilterCheck:
    def test_match(self):
        rule = PriorityRule(label="distress", min_confidence=0.8, reason_template="possible {label}")
        pf = PriorityFilter(rules=[rule])
        det = Detection(label="distress", confidence=0.9, bearing=0, range=0, position=Pose())
        result = pf.check(det)
        assert result is not None
        assert result.reason == "possible distress"
        assert result.detection == det

    def test_no_match_label(self):
        rule = PriorityRule(label="distress", min_confidence=0.8, reason_template="possible {label}")
        pf = PriorityFilter(rules=[rule])
        det = Detection(label="boat", confidence=0.9, bearing=0, range=0, position=Pose())
        result = pf.check(det)
        assert result is None

    def test_no_match_confidence_below_threshold(self):
        rule = PriorityRule(label="distress", min_confidence=0.8, reason_template="possible {label}")
        pf = PriorityFilter(rules=[rule])
        det = Detection(label="distress", confidence=0.5, bearing=0, range=0, position=Pose())
        result = pf.check(det)
        assert result is None

    def test_match_exact_confidence(self):
        rule = PriorityRule(label="distress", min_confidence=0.8, reason_template="possible {label}")
        pf = PriorityFilter(rules=[rule])
        det = Detection(label="distress", confidence=0.8, bearing=0, range=0, position=Pose())
        result = pf.check(det)
        assert result is not None

    def test_multiple_rules_first_match(self):
        r1 = PriorityRule(label="distress", min_confidence=0.8, reason_template="possible {label}")
        r2 = PriorityRule(label="fire", min_confidence=0.7, reason_template="detected {label}")
        pf = PriorityFilter(rules=[r1, r2])
        det = Detection(label="fire", confidence=0.8, bearing=0, range=0, position=Pose())
        result = pf.check(det)
        assert result is not None
        assert result.reason == "detected fire"

    def test_no_rules_returns_none(self):
        pf = PriorityFilter(rules=[])
        det = Detection(label="distress", confidence=0.99, bearing=0, range=0, position=Pose())
        result = pf.check(det)
        assert result is None


class TestPriorityFilterDefault:
    def test_default_has_distress_rule(self):
        pf = PriorityFilter.default()
        det = Detection(label="distress", confidence=0.85, bearing=0, range=0, position=Pose())
        result = pf.check(det)
        assert result is not None
        assert "distress" in result.reason

    def test_default_ignores_low_confidence(self):
        pf = PriorityFilter.default()
        det = Detection(label="distress", confidence=0.3, bearing=0, range=0, position=Pose())
        result = pf.check(det)
        assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/drone/test_priority_filter.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'drone.mission.priority_filter'`

- [ ] **Step 3: Implement PriorityFilter**

```python
# src/drone/mission/priority_filter.py
"""PriorityFilter — checks detections against priority rules."""
from __future__ import annotations

from drone.interfaces import PriorityRule, DetectionEvent, Detection


class PriorityFilter:
    """Check detections against a set of priority rules."""

    def __init__(self, rules: list[PriorityRule] | None = None) -> None:
        self._rules = rules if rules is not None else []

    def check(self, detection: Detection) -> DetectionEvent | None:
        """Return a DetectionEvent if any rule matches, else None."""
        for rule in self._rules:
            if detection.label == rule.label and detection.confidence >= rule.min_confidence:
                return DetectionEvent(
                    detection=detection,
                    reason=rule.reason_template.format(label=rule.label),
                )
        return None

    @classmethod
    def default(cls) -> PriorityFilter:
        """Default rules: distress at >=0.8 confidence."""
        return cls(rules=[
            PriorityRule(
                label="distress",
                min_confidence=0.8,
                reason_template="possible {label}",
            ),
        ])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/drone/test_priority_filter.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/drone/mission/priority_filter.py tests/unit/drone/test_priority_filter.py
git commit -m "feat: PriorityFilter with rule matching and default distress rule"
```

---

### Task 4: WaypointSequencer

**Files:**
- Create: `src/drone/navigation/__init__.py`
- Create: `src/drone/navigation/waypoint_sequencer.py`
- Create: `tests/unit/drone/test_waypoint_sequencer.py`

**Interfaces:**
- Consumes: `FlightController`, `NavPlan`, `Pose` from Task 1
- Produces: `WaypointSequencer` class with `set_plan()`, `step()`, `is_complete()`, `status()`

- [ ] **Step 1: Write failing tests for WaypointSequencer**

```python
# tests/unit/drone/test_waypoint_sequencer.py
"""Unit tests for WaypointSequencer."""
from __future__ import annotations

from drone.interfaces import NavPlan, Pose
from drone.fake_flight_controller import FakeFlightController
from drone.navigation.waypoint_sequencer import WaypointSequencer


class TestWaypointSequencerSetPlan:
    def test_set_plan_resets(self):
        fc = FakeFlightController()
        seq = WaypointSequencer(fc)
        plan = NavPlan(waypoints=[Pose(5, 0, 5, 0), Pose(10, 0, 5, 0)], algorithm_name="test", created_at=0)
        seq.set_plan(plan)
        s = seq.status()
        assert s["current_idx"] == 0
        assert s["total"] == 2
        assert s["plan_name"] == "test"

    def test_replace_plan_resets(self):
        fc = FakeFlightController()
        seq = WaypointSequencer(fc)
        plan1 = NavPlan(waypoints=[Pose(5, 0, 5, 0)], algorithm_name="a", created_at=0)
        seq.set_plan(plan1)
        # Step a few times to advance
        fc.arm()
        fc.takeoff(5.0)
        for _ in range(200):
            fc.step(0.05)
        for _ in range(200):
            seq.step(0.05)
        plan2 = NavPlan(waypoints=[Pose(20, 0, 5, 0)], algorithm_name="b", created_at=1.0)
        seq.set_plan(plan2)
        assert seq.status()["current_idx"] == 0
        assert seq.status()["plan_name"] == "b"


class TestWaypointSequencerStep:
    def test_step_advances_toward_waypoint(self):
        fc = FakeFlightController()
        seq = WaypointSequencer(fc)
        plan = NavPlan(waypoints=[Pose(3, 0, 5, 0)], algorithm_name="test", created_at=0)
        seq.set_plan(plan)
        fc.arm()
        fc.takeoff(5.0)
        for _ in range(200):
            fc.step(0.05)
        # Now step sequencer toward waypoint
        for _ in range(200):
            seq.step(0.05)
        pose = fc.get_pose()
        assert abs(pose.x - 3.0) < 1.0

    def test_step_returns_true_when_reached(self):
        fc = FakeFlightController()
        seq = WaypointSequencer(fc)
        plan = NavPlan(waypoints=[Pose(0, 0, 5, 0)], algorithm_name="test", created_at=0)
        seq.set_plan(plan)
        fc.arm()
        fc.takeoff(5.0)
        for _ in range(200):
            fc.step(0.05)
        # Already near first waypoint (x=0, y=0, z=5)
        reached = False
        for _ in range(100):
            if seq.step(0.05):
                reached = True
                break
        assert reached

    def test_step_returns_false_when_not_reached(self):
        fc = FakeFlightController()
        seq = WaypointSequencer(fc)
        plan = NavPlan(waypoints=[Pose(100, 100, 5, 0)], algorithm_name="test", created_at=0)
        seq.set_plan(plan)
        fc.arm()
        fc.takeoff(5.0)
        for _ in range(200):
            fc.step(0.05)
        result = seq.step(0.05)
        assert result is False


class TestWaypointSequencerComplete:
    def test_not_complete_initially(self):
        fc = FakeFlightController()
        seq = WaypointSequencer(fc)
        plan = NavPlan(waypoints=[Pose(5, 0, 5, 0)], algorithm_name="test", created_at=0)
        seq.set_plan(plan)
        assert seq.is_complete() is False

    def test_complete_after_all_waypoints(self):
        fc = FakeFlightController()
        seq = WaypointSequencer(fc)
        plan = NavPlan(waypoints=[Pose(0, 0, 5, 0)], algorithm_name="test", created_at=0)
        seq.set_plan(plan)
        fc.arm()
        fc.takeoff(5.0)
        for _ in range(200):
            fc.step(0.05)
        # Reach the waypoint
        for _ in range(200):
            seq.step(0.05)
        assert seq.is_complete() is True


class TestWaypointSequencerStatus:
    def test_status_format(self):
        fc = FakeFlightController()
        seq = WaypointSequencer(fc)
        plan = NavPlan(waypoints=[Pose(1, 0, 5, 0), Pose(2, 0, 5, 0), Pose(3, 0, 5, 0)], algorithm_name="sweep", created_at=0)
        seq.set_plan(plan)
        s = seq.status()
        assert s == {"current_idx": 0, "total": 3, "completed": 0, "plan_name": "sweep"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/drone/test_waypoint_sequencer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'drone.navigation'`

- [ ] **Step 3: Implement WaypointSequencer**

```python
# src/drone/navigation/__init__.py
"""Navigation subsystem."""
```

```python
# src/drone/navigation/waypoint_sequencer.py
"""WaypointSequencer — ticks the flight controller toward the current waypoint."""
from __future__ import annotations

import math

from drone.interfaces import FlightController, NavPlan, Pose


class WaypointSequencer:
    """Ticks the flight controller toward the current waypoint."""

    WAYPOINT_REACH_THRESHOLD: float = 0.5  # meters

    def __init__(self, fc: FlightController) -> None:
        self._fc = fc
        self._plan: NavPlan | None = None
        self._current_idx: int = 0
        self._completed: int = 0

    def set_plan(self, plan: NavPlan) -> None:
        """Set or replace the active nav plan. Resets to waypoint 0."""
        self._plan = plan
        self._current_idx = 0
        self._completed = 0

    def step(self, dt: float) -> bool:
        """Advance toward current waypoint. Returns True if waypoint was reached this step."""
        if self._plan is None:
            return False

        if self._current_idx >= len(self._plan.waypoints):
            return False

        wp = self._plan.waypoints[self._current_idx]
        self._fc.goto(wp.x, wp.y, wp.z)
        self._fc.step(dt)

        pose = self._fc.get_pose()
        dist = math.sqrt(
            (pose.x - wp.x) ** 2 +
            (pose.y - wp.y) ** 2 +
            (pose.z - wp.z) ** 2
        )

        if dist < self.WAYPOINT_REACH_THRESHOLD:
            self._current_idx += 1
            self._completed += 1
            return True

        return False

    def is_complete(self) -> bool:
        """All waypoints reached."""
        if self._plan is None:
            return False
        return self._current_idx >= len(self._plan.waypoints)

    def status(self) -> dict:
        """{"current_idx": N, "total": M, "completed": K, "plan_name": str}"""
        total = len(self._plan.waypoints) if self._plan is not None else 0
        name = self._plan.algorithm_name if self._plan is not None else ""
        return {
            "current_idx": self._current_idx,
            "total": total,
            "completed": self._completed,
            "plan_name": name,
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/drone/test_waypoint_sequencer.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/drone/navigation/__init__.py src/drone/navigation/waypoint_sequencer.py tests/unit/drone/test_waypoint_sequencer.py
git commit -m "feat: WaypointSequencer with plan tracking, step, reach detection"
```

---

### Task 5: NavRegistry

**Files:**
- Create: `src/drone/navigation/registry.py`
- Create: `tests/unit/drone/test_nav_registry.py`

**Interfaces:**
- Consumes: `NavigationAlgorithm` protocol from Task 1
- Produces: `NavRegistry` class with `register()`, `lookup()`, `list_algorithms()`

- [ ] **Step 1: Write failing tests for NavRegistry**

```python
# tests/unit/drone/test_nav_registry.py
"""Unit tests for NavRegistry."""
from __future__ import annotations

import pytest
from drone.interfaces import NavPlan, NavContext, WaterArea, NavigationAlgorithm, Pose
from drone.navigation.registry import NavRegistry


class _DummyAlgo:
    """Trivial NavigationAlgorithm for testing."""
    def plan(self, water: WaterArea, context: NavContext) -> NavPlan:
        return NavPlan(
            waypoints=[Pose(0, 0, 5, 0)],
            algorithm_name="dummy",
            created_at=0.0,
        )


class TestNavRegistry:
    def test_register_and_lookup(self):
        reg = NavRegistry()
        algo = _DummyAlgo()
        reg.register("dummy", algo)
        found = reg.lookup("dummy")
        assert found is algo

    def test_lookup_unknown_raises(self):
        reg = NavRegistry()
        with pytest.raises(KeyError):
            reg.lookup("nonexistent")

    def test_list_algorithms(self):
        reg = NavRegistry()
        reg.register("alpha", _DummyAlgo())
        reg.register("beta", _DummyAlgo())
        names = reg.list_algorithms()
        assert "alpha" in names
        assert "beta" in names

    def test_list_empty(self):
        reg = NavRegistry()
        assert reg.list_algorithms() == []

    def test_register_replaces(self):
        reg = NavRegistry()
        algo1 = _DummyAlgo()
        algo2 = _DummyAlgo()
        reg.register("same", algo1)
        reg.register("same", algo2)
        assert reg.lookup("same") is algo2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/drone/test_nav_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'drone.navigation.registry'`

- [ ] **Step 3: Implement NavRegistry**

```python
# src/drone/navigation/registry.py
"""NavRegistry — registry of named NavigationAlgorithm implementations."""
from __future__ import annotations

from drone.interfaces import NavigationAlgorithm


class NavRegistry:
    """Registry of named NavigationAlgorithm implementations."""

    def __init__(self) -> None:
        self._algorithms: dict[str, NavigationAlgorithm] = {}

    def register(self, name: str, algorithm: NavigationAlgorithm) -> None:
        self._algorithms[name] = algorithm

    def lookup(self, name: str) -> NavigationAlgorithm:
        if name not in self._algorithms:
            raise KeyError(f"No algorithm registered with name '{name}'")
        return self._algorithms[name]

    def list_algorithms(self) -> list[str]:
        return list(self._algorithms.keys())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/drone/test_nav_registry.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/drone/navigation/registry.py tests/unit/drone/test_nav_registry.py
git commit -m "feat: NavRegistry for named navigation algorithm lookup"
```

---

### Task 6: PerimeterSweepAlgorithm

**Files:**
- Create: `src/drone/navigation/perimeter_sweep.py`
- Create: `tests/unit/drone/test_perimeter_sweep.py`

**Interfaces:**
- Consumes: `WaterArea`, `NavContext`, `NavPlan`, `Pose`, `NavigationAlgorithm` from Task 1
- Produces: `PerimeterSweepAlgorithm` class with `plan()`

- [ ] **Step 1: Write failing tests for PerimeterSweep**

```python
# tests/unit/drone/test_perimeter_sweep.py
"""Unit tests for PerimeterSweepAlgorithm."""
from __future__ import annotations

import math
from drone.interfaces import WaterArea, NavContext, NavPlan, Pose
from drone.navigation.perimeter_sweep import PerimeterSweepAlgorithm


class TestPerimeterSweepBasic:
    def test_square_produces_waypoints(self):
        """A square water area should produce perimeter waypoints."""
        water = WaterArea(vertices=[(0, 0), (10, 0), (10, 10), (0, 10)])
        ctx = NavContext(current_pose=Pose(0, 0, 0, 0), completed_area=[])
        algo = PerimeterSweepAlgorithm(altitude=5.0, offset=1.0)
        plan = algo.plan(water, ctx)
        assert isinstance(plan, NavPlan)
        assert plan.algorithm_name == "perimeter_sweep"
        assert len(plan.waypoints) >= 4  # at least one per side
        # All waypoints at correct altitude
        for wp in plan.waypoints:
            assert wp.z == 5.0

    def test_triangle_produces_waypoints(self):
        water = WaterArea(vertices=[(0, 0), (10, 0), (5, 10)])
        ctx = NavContext(current_pose=Pose(0, 0, 0, 0), completed_area=[])
        algo = PerimeterSweepAlgorithm(altitude=5.0, offset=1.0)
        plan = algo.plan(water, ctx)
        assert len(plan.waypoints) >= 3

    def test_waypoints_start_near_current_pose(self):
        water = WaterArea(vertices=[(0, 0), (10, 0), (10, 10), (0, 10)])
        ctx = NavContext(current_pose=Pose(10, 0, 0, 0), completed_area=[])
        algo = PerimeterSweepAlgorithm(altitude=5.0, offset=1.0)
        plan = algo.plan(water, ctx)
        assert len(plan.waypoints) > 0
        first = plan.waypoints[0]
        # First waypoint should be closest to current_pose (10, 0)
        dists = [math.sqrt((wp.x - 10) ** 2 + (wp.y - 0) ** 2) for wp in plan.waypoints[:-1]]  # exclude loop-close
        assert math.sqrt((first.x - 10) ** 2 + (first.y - 0) ** 2) == min(dists)

    def test_loop_closes(self):
        """Last waypoint should be same as first (close the loop)."""
        water = WaterArea(vertices=[(0, 0), (10, 0), (10, 10), (0, 10)])
        ctx = NavContext(current_pose=Pose(0, 0, 0, 0), completed_area=[])
        algo = PerimeterSweepAlgorithm(altitude=5.0, offset=1.0)
        plan = algo.plan(water, ctx)
        assert len(plan.waypoints) >= 2
        first = plan.waypoints[0]
        last = plan.waypoints[-1]
        assert abs(first.x - last.x) < 0.1
        assert abs(first.y - last.y) < 0.1


class TestPerimeterSweepInset:
    def test_inset_waypoints_are_inside(self):
        """Inset waypoints should be inside the polygon."""
        water = WaterArea(vertices=[(0, 0), (10, 0), (10, 10), (0, 10)])
        ctx = NavContext(current_pose=Pose(0, 0, 0, 0), completed_area=[])
        algo = PerimeterSweepAlgorithm(altitude=5.0, offset=2.0)
        plan = algo.plan(water, ctx)
        for wp in plan.waypoints[:-1]:  # exclude loop-close
            assert 2.0 <= wp.x <= 8.0, f"x={wp.x} not in [2, 8]"
            assert 2.0 <= wp.y <= 8.0, f"y={wp.y} not in [2, 8]"


class TestPerimeterSweepMaxDistFromShore:
    def test_max_distance_clips_waypoints(self):
        """Large water area with max_distance_from_shore should clip inner points."""
        water = WaterArea(vertices=[(0, 0), (100, 0), (100, 100), (0, 100)])
        ctx = NavContext(current_pose=Pose(0, 0, 0, 0), completed_area=[])
        algo = PerimeterSweepAlgorithm(altitude=5.0, offset=1.0, max_distance_from_shore=5.0)
        plan = algo.plan(water, ctx)
        # All waypoints should be within 5+1=6 meters of shoreline
        for wp in plan.waypoints[:-1]:
            # Distance to nearest edge
            d = min(wp.x, wp.y, 100 - wp.x, 100 - wp.y)
            assert d <= 7.0, f"waypoint at ({wp.x},{wp.y}) is {d}m from shore"


class TestPerimeterSweepDefaultParams:
    def test_default_altitude_and_offset(self):
        water = WaterArea(vertices=[(0, 0), (10, 0), (10, 10), (0, 10)])
        ctx = NavContext(current_pose=Pose(0, 0, 0, 0), completed_area=[])
        algo = PerimeterSweepAlgorithm()
        plan = algo.plan(water, ctx)
        for wp in plan.waypoints:
            assert wp.z == 5.0  # default altitude
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/drone/test_perimeter_sweep.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'drone.navigation.perimeter_sweep'`

- [ ] **Step 3: Implement PerimeterSweepAlgorithm**

```python
# src/drone/navigation/perimeter_sweep.py
"""PerimeterSweepAlgorithm — traces water polygon perimeter at a fixed inward offset."""
from __future__ import annotations

import math

from drone.interfaces import WaterArea, NavContext, NavPlan, Pose


def _inset_polygon(vertices: list[tuple[float, float]], offset: float) -> list[tuple[float, float]]:
    """Inset a polygon by moving each edge inward along its normal."""
    n = len(vertices)
    if n < 3:
        return vertices[:]

    # Compute edge normals (inward-pointing for CCW polygon)
    edges: list[tuple[float, float, float, float, float, float]] = []  # (x1,y1,x2,y2,nx,ny)
    for i in range(n):
        x1, y1 = vertices[i]
        x2, y2 = vertices[(i + 1) % n]
        dx, dy = x2 - x1, y2 - y1
        length = math.sqrt(dx * dx + dy * dy)
        if length < 1e-12:
            continue
        # Inward normal for CCW polygon: (-dy, dx) / length
        nx, ny = -dy / length, dx / length
        edges.append((x1, y1, x2, y2, nx, ny))

    if len(edges) < 3:
        return vertices[:]

    # Offset each edge
    offset_edges: list[tuple[float, float, float, float]] = []  # (ox1, oy1, ox2, oy2)
    for x1, y1, x2, y2, nx, ny in edges:
        offset_edges.append((x1 + nx * offset, y1 + ny * offset, x2 + nx * offset, y2 + ny * offset))

    # Intersect adjacent offset edges
    new_vertices: list[tuple[float, float]] = []
    m = len(offset_edges)
    for i in range(m):
        ox1, oy1, ox2, oy2 = offset_edges[i]
        px1, py1, px2, py2 = offset_edges[(i + 1) % m]

        # Line intersection
        d1x, d1y = ox2 - ox1, oy2 - oy1
        d2x, d2y = px2 - px1, py2 - py1

        denom = d1x * d2y - d1y * d2x
        if abs(denom) < 1e-12:
            # Parallel — use midpoint
            new_vertices.append(((ox2 + px1) / 2, (oy2 + py1) / 2))
        else:
            t = ((px1 - ox1) * d2y - (py1 - oy1) * d2x) / denom
            new_vertices.append((ox1 + t * d1x, oy1 + t * d1y))

    return new_vertices


def _distance_to_nearest_edge(px: float, py: float, vertices: list[tuple[float, float]]) -> float:
    """Distance from point to nearest edge of the polygon."""
    n = len(vertices)
    min_dist = float('inf')
    for i in range(n):
        x1, y1 = vertices[i]
        x2, y2 = vertices[(i + 1) % n]
        # Point-to-segment distance
        dx, dy = x2 - x1, y2 - y1
        length_sq = dx * dx + dy * dy
        if length_sq < 1e-12:
            dist = math.sqrt((px - x1) ** 2 + (py - y1) ** 2)
        else:
            t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / length_sq))
            proj_x, proj_y = x1 + t * dx, y1 + t * dy
            dist = math.sqrt((px - proj_x) ** 2 + (py - proj_y) ** 2)
        min_dist = min(min_dist, dist)
    return min_dist


def _ensure_ccw(vertices: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Ensure polygon vertices are in CCW order."""
    # Compute signed area
    n = len(vertices)
    area = 0.0
    for i in range(n):
        x1, y1 = vertices[i]
        x2, y2 = vertices[(i + 1) % n]
        area += (x2 - x1) * (y2 + y1)
    if area > 0:  # CW
        return list(reversed(vertices))
    return vertices[:]


class PerimeterSweepAlgorithm:
    """Traces the water polygon perimeter at a fixed inward offset and constant altitude."""

    def __init__(
        self,
        altitude: float = 5.0,
        offset: float = 2.0,
        max_distance_from_shore: float | None = None,
    ) -> None:
        self._altitude = altitude
        self._offset = offset
        self._max_distance = max_distance_from_shore

    def plan(self, water: WaterArea, context: NavContext) -> NavPlan:
        # Ensure CCW for consistent inset normals
        verts = _ensure_ccw(list(water.vertices))

        # Inset the polygon
        inset_verts = _inset_polygon(verts, self._offset)

        # Clip by max_distance_from_shore
        if self._max_distance is not None and len(inset_verts) >= 3:
            clipped = []
            for vx, vy in inset_verts:
                dist = _distance_to_nearest_edge(vx, vy, verts)
                if dist <= self._max_distance + self._offset:
                    clipped.append((vx, vy))
            inset_verts = clipped if len(clipped) >= 3 else inset_verts

        if len(inset_verts) < 3:
            # Degenerate — return single waypoint at centroid
            cx = sum(v[0] for v in verts) / len(verts)
            cy = sum(v[1] for v in verts) / len(verts)
            waypoints = [Pose(cx, cy, self._altitude, 0), Pose(cx, cy, self._altitude, 0)]
        else:
            # Order waypoints starting from vertex closest to current_pose
            cx, cy = context.current_pose.x, context.current_pose.y
            dists = [math.sqrt((vx - cx) ** 2 + (vy - cy) ** 2) for vx, vy in inset_verts]
            start_idx = dists.index(min(dists))
            # Reorder from start_idx, going CCW
            ordered = inset_verts[start_idx:] + inset_verts[:start_idx]

            # Create Pose waypoints
            waypoints = [Pose(vx, vy, self._altitude, 0) for vx, vy in ordered]
            # Close the loop
            waypoints.append(Pose(ordered[0][0], ordered[0][1], self._altitude, 0))

        return NavPlan(
            waypoints=waypoints,
            algorithm_name="perimeter_sweep",
            created_at=0.0,  # set by caller
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/drone/test_perimeter_sweep.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/drone/navigation/perimeter_sweep.py tests/unit/drone/test_perimeter_sweep.py
git commit -m "feat: PerimeterSweepAlgorithm with polygon inset, max-distance clipping"
```

---

### Task 7: ScriptedPerception

**Files:**
- Create: `src/drone/mission/scripted_perception.py`
- Create: `tests/unit/drone/test_scripted_perception.py` (listed as unit since deterministic)

**Interfaces:**
- Consumes: `Detection`, `Pose` from Task 1
- Produces: `ScriptedPerception` with `get_detections()`, `constant()`, `sequential()` class methods

- [ ] **Step 1: Write failing tests for ScriptedPerception**

```python
# tests/unit/drone/test_scripted_perception.py
"""Unit tests for ScriptedPerception."""
from __future__ import annotations

from drone.interfaces import Detection, Pose
from drone.mission.scripted_perception import ScriptedPerception


def _det(label: str) -> Detection:
    return Detection(label=label, confidence=0.9, bearing=0, range=0, position=Pose())


class TestScriptedPerceptionSequential:
    def test_sequential_returns_steps(self):
        sp = ScriptedPerception.sequential([
            [_det("a")],
            [_det("b"), _det("c")],
        ])
        assert len(sp.get_detections()) == 1
        assert len(sp.get_detections()) == 2

    def test_sequential_returns_empty_after_exhausted(self):
        sp = ScriptedPerception.sequential([[_det("x")]])
        sp.get_detections()  # step 0
        result = sp.get_detections()  # step 1 — exhausted
        assert result == []
        result2 = sp.get_detections()  # still empty
        assert result2 == []


class TestScriptedPerceptionConstant:
    def test_constant_repeats_forever(self):
        dets = [_det("a"), _det("b")]
        sp = ScriptedPerception.constant(dets)
        for _ in range(10):
            result = sp.get_detections()
            assert len(result) == 2
            assert result[0].label == "a"


class TestScriptedPerceptionRaw:
    def test_raw_script(self):
        sp = ScriptedPerception(script=[[_det("x")], []])
        assert len(sp.get_detections()) == 1
        assert sp.get_detections() == []
        assert sp.get_detections() == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/drone/test_scripted_perception.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'drone.mission.scripted_perception'`

- [ ] **Step 3: Implement ScriptedPerception**

```python
# src/drone/mission/scripted_perception.py
"""ScriptedPerception — deterministic Perception implementation for testing."""
from __future__ import annotations

from drone.interfaces import Detection


class ScriptedPerception:
    """Deterministic Perception implementation for testing."""

    def __init__(self, script: list[list[Detection]]) -> None:
        self._script = script
        self._idx: int = 0

    def get_detections(self) -> list[Detection]:
        """Return next scripted detection list. Returns empty list after script exhausted."""
        if self._idx >= len(self._script):
            return []
        result = self._script[self._idx]
        self._idx += 1
        return result

    @classmethod
    def constant(cls, detections: list[Detection]) -> ScriptedPerception:
        """Returns the same detections every call (infinite repeat)."""
        # Use a wrapper that never advances past step 0
        return _ConstantPerception(detections)

    @classmethod
    def sequential(cls, steps: list[list[Detection]]) -> ScriptedPerception:
        """Returns steps[0], steps[1], ..., then empty lists."""
        return cls(script=steps)


class _ConstantPerception(ScriptedPerception):
    """Special ScriptedPerception that always returns the same detections."""

    def __init__(self, detections: list[Detection]) -> None:
        super().__init__(script=[detections])

    def get_detections(self) -> list[Detection]:
        # Always return step 0 without advancing
        return self._script[0]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/drone/test_scripted_perception.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/drone/mission/scripted_perception.py tests/unit/drone/test_scripted_perception.py
git commit -m "feat: ScriptedPerception with sequential and constant modes"
```

---

### Task 8: FakeAgent

**Files:**
- Create: `src/drone/mission/fake_agent.py`
- Create: `tests/agent/test_fake_agent.py`

**Interfaces:**
- Consumes: `MissionPlanner`, `MissionState`, `Directive` from Tasks 1–2
- Produces: `FakeAgent` class implementing `MissionPlanner`

- [ ] **Step 1: Write failing tests for FakeAgent**

```python
# tests/agent/test_fake_agent.py
"""Tests for FakeAgent."""
from __future__ import annotations

import pytest
from drone.interfaces import Directive, MissionPlanner
from drone.mission.state import MissionState
from drone.mission.fake_agent import FakeAgent


class TestFakeAgent:
    def test_returns_scripted_directives(self):
        state = MissionState(mission_objectives="test")
        agent = FakeAgent(responses=[
            Directive(kind="continue"),
            Directive(kind="land"),
        ])
        assert agent.decide(state).kind == "continue"
        assert agent.decide(state).kind == "land"

    def test_returns_continue_after_exhausted(self):
        state = MissionState(mission_objectives="test")
        agent = FakeAgent(responses=[Directive(kind="land")])
        agent.decide(state)  # consume the scripted response
        result = agent.decide(state)
        assert result.kind == "continue"

    def test_default_is_continue(self):
        state = MissionState(mission_objectives="test")
        agent = FakeAgent()  # no responses
        result = agent.decide(state)
        assert result.kind == "continue"

    def test_satisfies_mission_planner_protocol(self):
        agent = FakeAgent()
        assert isinstance(agent, MissionPlanner)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/agent/test_fake_agent.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'drone.mission.fake_agent'`

- [ ] **Step 3: Implement FakeAgent**

```python
# src/drone/mission/fake_agent.py
"""FakeAgent — deterministic MissionPlanner for testing."""
from __future__ import annotations

from drone.interfaces import Directive, MissionPlanner
from drone.mission.state import MissionState


class FakeAgent:
    """Deterministic MissionPlanner for testing."""

    def __init__(self, responses: list[Directive] | None = None) -> None:
        self._responses = list(responses) if responses is not None else []
        self._idx: int = 0

    def decide(self, state: MissionState) -> Directive:
        """Return next scripted directive. Returns continue after script exhausted."""
        if self._idx < len(self._responses):
            result = self._responses[self._idx]
            self._idx += 1
            return result
        return Directive(kind="continue")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/agent/test_fake_agent.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/drone/mission/fake_agent.py tests/agent/test_fake_agent.py
git commit -m "feat: FakeAgent for deterministic mission planner testing"
```

---

### Task 9: DirectiveExecutor

**Files:**
- Create: `src/drone/mission/directive_executor.py`
- Create: `tests/agent/test_directive_executor.py`

**Interfaces:**
- Consumes: `Directive`, `FlightController`, `WaypointSequencer`, `MissionState`, `NavPlan`, `Detection`, `Pose` from Tasks 1–4
- Produces: `DirectiveExecutor` class with `execute()` returning result description string

- [ ] **Step 1: Write failing tests for DirectiveExecutor**

```python
# tests/agent/test_directive_executor.py
"""Tests for DirectiveExecutor."""
from __future__ import annotations

from drone.interfaces import Directive, NavPlan, Detection, Pose
from drone.fake_flight_controller import FakeFlightController
from drone.mission.state import MissionState
from drone.navigation.waypoint_sequencer import WaypointSequencer
from drone.mission.directive_executor import DirectiveExecutor


def _make_executor():
    fc = FakeFlightController()
    seq = WaypointSequencer(fc)
    state = MissionState(mission_objectives="test")
    return DirectiveExecutor(fc=fc, sequencer=seq, state=state), fc, seq, state


class TestDirectiveExecutorContinue:
    def test_continue_is_noop(self):
        ex, fc, seq, state = _make_executor()
        result = ex.execute(Directive(kind="continue"))
        assert "continue" in result.lower() or "no-op" in result.lower()


class TestDirectiveExecutorUpdateNav:
    def test_update_nav_sets_plan(self):
        ex, fc, seq, state = _make_executor()
        plan = NavPlan(waypoints=[Pose(5, 5, 5, 0), Pose(10, 10, 5, 0)], algorithm_name="sweep", created_at=0)
        result = ex.execute(Directive(kind="update_nav", args={"nav_plan": plan}))
        assert state.nav_plan == plan
        assert "update" in result.lower() or "nav" in result.lower()


class TestDirectiveExecutorLand:
    def test_land_calls_fc_land(self):
        ex, fc, seq, state = _make_executor()
        fc.arm()
        fc.takeoff(5.0)
        for _ in range(200):
            fc.step(0.05)
        result = ex.execute(Directive(kind="land"))
        assert "land" in result.lower()


class TestDirectiveExecutorReturnBase:
    def test_return_base_creates_home_plan(self):
        ex, fc, seq, state = _make_executor()
        result = ex.execute(Directive(kind="return_base"))
        assert state.nav_plan is not None
        # Plan should head toward origin
        assert any(abs(wp.x) < 1 and abs(wp.y) < 1 for wp in state.nav_plan.waypoints)
        assert "return" in result.lower() or "base" in result.lower()


class TestDirectiveExecutorOverride:
    def test_override_builds_investigation_plan(self):
        ex, fc, seq, state = _make_executor()
        det = Detection(label="distress", confidence=0.9, bearing=45, range=10, position=Pose(5, 5, 0, 0))
        result = ex.execute(Directive(kind="override", args={"detection": det}))
        assert state.nav_plan is not None
        assert len(state.nav_plan.waypoints) >= 1
        assert "override" in result.lower() or "investigate" in result.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/agent/test_directive_executor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'drone.mission.directive_executor'`

- [ ] **Step 3: Implement DirectiveExecutor**

```python
# src/drone/mission/directive_executor.py
"""DirectiveExecutor — translates a Directive into concrete actions."""
from __future__ import annotations

from drone.interfaces import Directive, FlightController, NavPlan, Detection, Pose
from drone.mission.state import MissionState
from drone.navigation.waypoint_sequencer import WaypointSequencer


class DirectiveExecutor:
    """Translates a Directive into concrete actions on the WaypointSequencer and FlightController."""

    def __init__(
        self,
        fc: FlightController,
        sequencer: WaypointSequencer,
        state: MissionState,
    ) -> None:
        self._fc = fc
        self._sequencer = sequencer
        self._state = state

    def execute(self, directive: Directive) -> str:
        """Execute a directive. Returns a result description for the next MissionState.update()."""
        kind = directive.kind

        if kind == "continue":
            return "continue: following current plan"

        if kind == "update_nav":
            plan = directive.args["nav_plan"]
            assert isinstance(plan, NavPlan)
            self._sequencer.set_plan(plan)
            self._state.set_nav_plan(plan)
            return f"update_nav: set {plan.algorithm_name} plan with {len(plan.waypoints)} waypoints"

        if kind == "override":
            det = directive.args["detection"]
            assert isinstance(det, Detection)
            # Build single-waypoint investigation plan
            invest_plan = NavPlan(
                waypoints=[det.position],
                algorithm_name="investigate",
                created_at=self._state.mission_clock,
            )
            self._sequencer.set_plan(invest_plan)
            self._state.set_nav_plan(invest_plan)
            return f"override: investigating {det.label} at ({det.position.x:.1f}, {det.position.y:.1f})"

        if kind == "land":
            self._fc.land()
            return "land: initiating landing"

        if kind == "return_base":
            home_plan = NavPlan(
                waypoints=[Pose(0, 0, self._state.current_pose.z, 0)],
                algorithm_name="return_base",
                created_at=self._state.mission_clock,
            )
            self._sequencer.set_plan(home_plan)
            self._state.set_nav_plan(home_plan)
            return "return_base: heading to origin"

        return f"unknown directive kind: {kind}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/agent/test_directive_executor.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/drone/mission/directive_executor.py tests/agent/test_directive_executor.py
git commit -m "feat: DirectiveExecutor — translates Directives into FC/Sequencer actions"
```

---

### Task 10: LlmAgent & Provider Adapters

**Files:**
- Create: `src/drone/mission/tools.py`
- Create: `src/drone/mission/llm_agent.py`
- Create: `tests/agent/test_llm_agent.py`

**Interfaces:**
- Consumes: `ModelConfig`, `Directive`, `MissionPlanner`, `NavPlan`, `NavRegistry`, `MissionState`, `WaterArea`, `NavContext`, `Detection`, `Pose` from Tasks 1–6
- Produces: `LlmAgent` implementing `MissionPlanner`, `ProviderAdapter` protocol, tool definitions and implementations

- [ ] **Step 1: Write failing tests for LlmAgent**

```python
# tests/agent/test_llm_agent.py
"""Tests for LlmAgent with mocked providers."""
from __future__ import annotations

import json
import pytest
from unittest.mock import MagicMock, patch

from drone.interfaces import (
    ModelConfig, Directive, NavPlan, Pose, WaterArea, NavContext,
    MissionPlanner, Detection,
)
from drone.mission.state import MissionState
from drone.mission.llm_agent import LlmAgent
from drone.mission.tools import plan_navigation, investigate_target
from drone.navigation.registry import NavRegistry
from drone.navigation.perimeter_sweep import PerimeterSweepAlgorithm


def _make_state() -> MissionState:
    state = MissionState(mission_objectives="Survey water area for distress signals")
    state.set_nav_plan(NavPlan(
        waypoints=[Pose(5, 0, 5, 0), Pose(10, 0, 5, 0)],
        algorithm_name="perimeter_sweep",
        created_at=0,
    ))
    state.update(pose=Pose(3, 0, 5, 0), detections=[], last_directive_result=None, dt=0.05)
    return state


def _make_registry() -> NavRegistry:
    reg = NavRegistry()
    reg.register("perimeter_sweep", PerimeterSweepAlgorithm())
    return reg


class TestToolPlanNavigation:
    def test_plan_navigation_returns_navplan(self):
        reg = _make_registry()
        water = WaterArea(vertices=[(0, 0), (10, 0), (10, 10), (0, 10)])
        ctx = NavContext(current_pose=Pose(), completed_area=[])
        result = plan_navigation(registry=reg, water_area=water, algorithm="perimeter_sweep", context=ctx)
        assert isinstance(result, NavPlan)
        assert result.algorithm_name == "perimeter_sweep"

    def test_plan_navigation_unknown_algorithm_raises(self):
        reg = _make_registry()
        water = WaterArea(vertices=[(0, 0), (10, 0), (10, 10), (0, 10)])
        ctx = NavContext(current_pose=Pose(), completed_area=[])
        with pytest.raises(KeyError):
            plan_navigation(registry=reg, water_area=water, algorithm="nonexistent", context=ctx)


class TestToolInvestigateTarget:
    def test_investigate_returns_single_waypoint_plan(self):
        det = Detection(label="distress", confidence=0.9, bearing=0, range=0, position=Pose(5, 5, 0, 0))
        result = investigate_target(detection=det)
        assert isinstance(result, NavPlan)
        assert len(result.waypoints) == 1
        assert result.waypoints[0] == det.position


class TestLlmAgentFallback:
    def test_api_failure_returns_continue(self):
        """When all providers fail, agent returns continue."""
        config = ModelConfig(provider="google", model="test-model", api_key="fake-key")
        reg = _make_registry()
        agent = LlmAgent(model_chain=[config], registry=reg)
        state = _make_state()
        # Mock all provider adapters to raise
        with patch.object(agent, "_call_provider", side_effect=RuntimeError("API error")):
            result = agent.decide(state)
            assert result.kind == "continue"

    def test_malformed_response_returns_continue(self):
        """When LLM returns unparseable response, agent returns continue."""
        config = ModelConfig(provider="google", model="test-model", api_key="fake-key")
        reg = _make_registry()
        agent = LlmAgent(model_chain=[config], registry=reg)
        state = _make_state()
        with patch.object(agent, "_call_provider", return_value="not valid json"):
            result = agent.decide(state)
            assert result.kind == "continue"


class TestLlmAgentDirectiveParsing:
    def test_parse_update_nav_directive(self):
        reg = _make_registry()
        agent = LlmAgent(model_chain=[], registry=reg)
        # Test internal parse
        raw = {"kind": "continue"}
        result = agent._parse_directive(json.dumps(raw))
        assert result.kind == "continue"

    def test_parse_land_directive(self):
        reg = _make_registry()
        agent = LlmAgent(model_chain=[], registry=reg)
        raw = {"kind": "land"}
        result = agent._parse_directive(json.dumps(raw))
        assert result.kind == "land"

    def test_parse_invalid_json_returns_continue(self):
        reg = _make_registry()
        agent = LlmAgent(model_chain=[], registry=reg)
        result = agent._parse_directive("not json at all")
        assert result.kind == "continue"

    def test_parse_invalid_kind_returns_continue(self):
        reg = _make_registry()
        agent = LlmAgent(model_chain=[], registry=reg)
        raw = {"kind": "fly_to_mars"}
        result = agent._parse_directive(json.dumps(raw))
        assert result.kind == "continue"


class TestLlmAgentSatisfiesProtocol:
    def test_is_mission_planner(self):
        reg = _make_registry()
        agent = LlmAgent(model_chain=[], registry=reg)
        assert isinstance(agent, MissionPlanner)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/agent/test_llm_agent.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'drone.mission.llm_agent'`

- [ ] **Step 3: Implement tool functions**

```python
# src/drone/mission/tools.py
"""Tool implementations — pure functions, no side effects."""
from __future__ import annotations

from drone.interfaces import (
    WaterArea, NavContext, NavPlan, NavigationAlgorithm,
    Detection, Pose,
)
from drone.navigation.registry import NavRegistry


def plan_navigation(
    registry: NavRegistry,
    water_area: WaterArea,
    algorithm: str,
    context: NavContext,
    max_distance_from_shore: float | None = None,
) -> NavPlan:
    """Generate waypoints for a named algorithm."""
    algo = registry.lookup(algorithm)
    plan = algo.plan(water_area, context)
    return plan


def update_navigation(nav_plan: NavPlan) -> NavPlan:
    """Replace current nav plan mid-flight."""
    return nav_plan


def abort_navigation() -> None:
    """Cancel current nav, hover in place."""
    return None


def investigate_target(detection: Detection) -> NavPlan:
    """Single-waypoint plan to fly to a detection."""
    return NavPlan(
        waypoints=[detection.position],
        algorithm_name="investigate",
        created_at=0.0,  # caller sets
    )


def get_mission_status(state_summary: str) -> str:
    """Read current state (no side effect)."""
    return state_summary


def mark_objective(objective_id: str, status: str) -> str:
    """Update objective tracking."""
    return f"Marked {objective_id} as {status}"
```

- [ ] **Step 4: Implement LlmAgent**

```python
# src/drone/mission/llm_agent.py
"""LlmAgent — real LLM-backed MissionPlanner with configurable model chain."""
from __future__ import annotations

import json
import logging
from typing import Any

from drone.interfaces import ModelConfig, Directive, MissionPlanner
from drone.mission.state import MissionState
from drone.mission.tools import plan_navigation, investigate_target, mark_objective
from drone.navigation.registry import NavRegistry

logger = logging.getLogger(__name__)

VALID_DIRECTIVE_KINDS = {"update_nav", "override", "continue", "land", "return_base"}

SYSTEM_PROMPT = """You are a drone mission controller. You receive a mission status summary
and decide what to do next. You have tools to plan and update navigation,
investigate targets, check mission status, and mark objectives.

Rules:
- Always ensure a navigation plan is active. If none exists, create one.
- High-priority detections (distress, danger) override the current plan.
  Investigate first, then resume or replan navigation.
- If a detection has low confidence, you may request the drone to approach
  for a better view before classifying.
- Land immediately if battery is critically low (the system will enforce this).
- Output a Directive as your final response: {"kind": "...", "args": {...}}
  Valid kinds: update_nav, override, continue, land, return_base."""

# Tool schemas for LLM function calling
TOOL_DEFINITIONS = [
    {
        "name": "plan_navigation",
        "description": "Generate waypoints for a named navigation algorithm",
        "parameters": {
            "type": "object",
            "properties": {
                "algorithm": {"type": "string", "description": "Algorithm name (e.g. perimeter_sweep)"},
                "max_distance_from_shore": {"type": "number", "description": "Optional max distance from shore in meters"},
            },
            "required": ["algorithm"],
        },
    },
    {
        "name": "investigate_target",
        "description": "Build a single-waypoint plan to fly to a detection",
        "parameters": {
            "type": "object",
            "properties": {
                "detection_label": {"type": "string"},
                "detection_x": {"type": "number"},
                "detection_y": {"type": "number"},
                "detection_z": {"type": "number"},
            },
            "required": ["detection_label", "detection_x", "detection_y", "detection_z"],
        },
    },
    {
        "name": "mark_objective",
        "description": "Update objective tracking",
        "parameters": {
            "type": "object",
            "properties": {
                "objective_id": {"type": "string"},
                "status": {"type": "string", "enum": ["pending", "in_progress", "complete", "failed"]},
            },
            "required": ["objective_id", "status"],
        },
    },
    {
        "name": "get_mission_status",
        "description": "Read current state (no side effect)",
        "parameters": {"type": "object", "properties": {}},
    },
]


class LlmAgent:
    """Real LLM-backed MissionPlanner. Configurable model chain with automatic fallback."""

    def __init__(
        self,
        model_chain: list[ModelConfig],
        registry: NavRegistry,
    ) -> None:
        self._model_chain = model_chain
        self._registry = registry

    def decide(self, state: MissionState) -> Directive:
        """Call LLM with state summary, return parsed Directive."""
        summary = state.summary()

        for config in self._model_chain:
            try:
                response = self._call_provider(config, summary)
                directive = self._parse_directive(response)
                if directive.kind in VALID_DIRECTIVE_KINDS:
                    return directive
            except Exception as e:
                logger.warning(f"Model {config.model} failed: {e}")
                continue

        # All models failed or returned invalid directives
        return Directive(kind="continue")

    def _call_provider(self, config: ModelConfig, summary: str) -> str:
        """Call a provider API. Override in subclasses or mock for testing."""
        # This method dispatches to provider-specific adapters.
        # For now, raise NotImplementedError — real adapters will be added
        # when integrating with actual APIs.
        raise NotImplementedError(f"Provider {config.provider} not yet implemented")

    def _parse_directive(self, raw: str) -> Directive:
        """Parse LLM response text into a Directive."""
        try:
            data = json.loads(raw)
            if isinstance(data, dict) and "kind" in data:
                kind = data["kind"]
                args = data.get("args", {})
                if kind in VALID_DIRECTIVE_KINDS:
                    return Directive(kind=kind, args=args)
        except (json.JSONDecodeError, TypeError, KeyError):
            pass
        return Directive(kind="continue")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/agent/test_llm_agent.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/drone/mission/tools.py src/drone/mission/llm_agent.py tests/agent/test_llm_agent.py
git commit -m "feat: LlmAgent with model chain fallback, tool definitions, directive parsing"
```

---

### Task 11: MissionLoop

**Files:**
- Create: `src/drone/mission/loop.py`
- Create: `tests/integration/test_mission_loop.py`

**Interfaces:**
- Consumes: `FlightController`, `Perception`, `MissionPlanner`, `NavigationAlgorithm`, `PriorityRule`, `Directive`, `DetectionEvent`, `NavPlan`, `Pose`, `Detection`, `MissionState`, `WaypointSequencer`, `PriorityFilter`, `DirectiveExecutor`, `FakeAgent`, `ScriptedPerception`, `FakeFlightController` from all prior tasks
- Produces: `MissionLoop`, `MissionResult`

- [ ] **Step 1: Write failing tests for MissionLoop**

```python
# tests/integration/test_mission_loop.py
"""Integration tests for MissionLoop."""
from __future__ import annotations

from drone.interfaces import Directive, Detection, Pose, NavPlan, WaterArea
from drone.fake_flight_controller import FakeFlightController
from drone.mission.state import MissionState
from drone.mission.loop import MissionLoop, MissionResult
from drone.mission.fake_agent import FakeAgent
from drone.mission.scripted_perception import ScriptedPerception
from drone.mission.priority_filter import PriorityFilter
from drone.navigation.waypoint_sequencer import WaypointSequencer
from drone.navigation.registry import NavRegistry
from drone.navigation.perimeter_sweep import PerimeterSweepAlgorithm


def _make_loop(agent: FakeAgent, perception: ScriptedPerception, heartbeat_interval: float = 5.0):
    fc = FakeFlightController()
    reg = NavRegistry()
    reg.register("perimeter_sweep", PerimeterSweepAlgorithm())
    return MissionLoop(
        fc=fc,
        perception=perception,
        agent=agent,
        algorithms=reg,
        heartbeat_interval=heartbeat_interval,
        dt=0.05,
    )


class TestMissionLoopBasicRun:
    def test_run_completes_with_land(self):
        """Mission that immediately lands should complete."""
        agent = FakeAgent(responses=[
            Directive(kind="land"),
        ])
        perception = ScriptedPerception.constant([])
        loop = _make_loop(agent, perception, heartbeat_interval=0.1)
        result = loop.run(max_duration=10.0, mission_objectives="test")
        assert isinstance(result, MissionResult)
        assert result.duration < 10.0  # landed before timeout

    def test_run_continues_until_timeout(self):
        """Mission that always continues should run until timeout."""
        agent = FakeAgent()  # always continues
        perception = ScriptedPerception.constant([])
        loop = _make_loop(agent, perception, heartbeat_interval=0.1)
        result = loop.run(max_duration=2.0, mission_objectives="test")
        assert result.duration >= 1.5  # ran for a while


class TestMissionLoopHeartbeat:
    def test_heartbeat_calls_agent(self):
        """Agent should be called at each heartbeat."""
        call_count = 0

        class CountingAgent:
            def decide(self, state: MissionState) -> Directive:
                nonlocal call_count
                call_count += 1
                return Directive(kind="continue")

        from drone.interfaces import MissionPlanner
        agent = CountingAgent()
        perception = ScriptedPerception.constant([])
        loop = _make_loop(agent, perception, heartbeat_interval=0.2)
        result = loop.run(max_duration=1.0, mission_objectives="test")
        assert call_count >= 3  # several heartbeats in 1 second


class TestMissionLoopPriorityEvent:
    def test_priority_detection_triggers_agent(self):
        """High-priority detection should trigger immediate agent call."""
        agent_calls: list[str] = []

        class TrackingAgent:
            def decide(self, state: MissionState) -> Directive:
                agent_calls.append(state.mission_objectives)
                return Directive(kind="continue")

        from drone.interfaces import MissionPlanner
        agent = TrackingAgent()
        det = Detection(label="distress", confidence=0.9, bearing=0, range=0, position=Pose(5, 5, 0, 0))
        perception = ScriptedPerception.sequential([
            [det],  # first call: priority detection
        ])
        loop = _make_loop(agent, perception, heartbeat_interval=0.1)
        loop.run(max_duration=1.0, mission_objectives="test")
        # Agent should have been called at least once
        assert len(agent_calls) >= 1


class TestMissionLoopBatteryCritical:
    def test_battery_critical_auto_lands(self):
        """Battery below 10% should auto-land without agent."""
        fc = FakeFlightController()
        # Drastically increase battery drain for this test
        fc.BATTERY_DRAIN = 0.01
        agent = FakeAgent()  # always continues
        perception = ScriptedPerception.constant([])
        reg = NavRegistry()
        reg.register("perimeter_sweep", PerimeterSweepAlgorithm())
        loop = MissionLoop(
            fc=fc,
            perception=perception,
            agent=agent,
            algorithms=reg,
            heartbeat_interval=0.1,
            dt=0.05,
        )
        result = loop.run(max_duration=5.0, mission_objectives="test")
        # Should have landed due to battery
        assert result.battery_remaining < 0.15


class TestMissionResult:
    def test_result_fields(self):
        agent = FakeAgent(responses=[Directive(kind="land")])
        perception = ScriptedPerception.constant([])
        loop = _make_loop(agent, perception, heartbeat_interval=0.1)
        result = loop.run(max_duration=5.0, mission_objectives="test")
        assert isinstance(result.final_pose, Pose)
        assert isinstance(result.battery_remaining, float)
        assert isinstance(result.duration, float)
        assert isinstance(result.action_count, int)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/integration/test_mission_loop.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'drone.mission.loop'`

- [ ] **Step 3: Implement MissionLoop**

```python
# src/drone/mission/loop.py
"""MissionLoop — the main loop tying perception, agent, and navigation together."""
from __future__ import annotations

from dataclasses import dataclass

from drone.interfaces import (
    FlightController, Perception, MissionPlanner, Directive,
    DetectionEvent, NavPlan, Pose,
)
from drone.mission.state import MissionState
from drone.mission.priority_filter import PriorityFilter
from drone.mission.directive_executor import DirectiveExecutor
from drone.navigation.waypoint_sequencer import WaypointSequencer
from drone.navigation.registry import NavRegistry


@dataclass(frozen=True)
class MissionResult:
    """Result of a completed mission."""
    final_pose: Pose
    battery_remaining: float
    objectives_status: dict[str, str]
    nav_plan_completed: bool
    duration: float
    action_count: int


class MissionLoop:
    """Main mission loop with three rhythms: tick, heartbeat, event."""

    def __init__(
        self,
        fc: FlightController,
        perception: Perception,
        agent: MissionPlanner,
        algorithms: NavRegistry,
        priority_rules: list | None = None,
        heartbeat_interval: float = 5.0,
        dt: float = 0.05,
    ) -> None:
        self._fc = fc
        self._perception = perception
        self._agent = agent
        self._algorithms = algorithms
        self._priority_filter = PriorityFilter(rules=priority_rules) if priority_rules else PriorityFilter.default()
        self._heartbeat_interval = heartbeat_interval
        self._dt = dt

        self._state: MissionState | None = None
        self._sequencer: WaypointSequencer | None = None
        self._executor: DirectiveExecutor | None = None
        self._last_heartbeat: float = 0.0

    def start(self, mission_objectives: str) -> None:
        """Arm, take off, initialize MissionState, begin mission."""
        self._state = MissionState(mission_objectives=mission_objectives)
        self._sequencer = WaypointSequencer(self._fc)
        self._executor = DirectiveExecutor(self._fc, self._sequencer, self._state)

        self._fc.arm()
        self._fc.takeoff(altitude=5.0)
        # Let the FC reach takeoff altitude
        for _ in range(200):
            self._fc.step(self._dt)
            self._state.update(
                pose=self._fc.get_pose(),
                detections=[],
                last_directive_result=None,
                dt=self._dt,
                battery=self._fc.get_battery(),
            )

        self._last_heartbeat = self._state.mission_clock

    def tick(self, dt: float) -> None:
        """Fast loop — sequencer drives FC toward current waypoint."""
        if self._sequencer is not None and not self._sequencer.is_complete():
            reached = self._sequencer.step(dt)
            if reached and self._state is not None:
                self._state.advance_waypoint()

    def heartbeat(self) -> None:
        """Slow loop — agent reviews full state, may issue Directive."""
        if self._state is None:
            return

        directive = self._agent.decide(self._state)
        result = self._execute_directive(directive)
        self._state.update(
            pose=self._fc.get_pose(),
            detections=self._state.new_detections,
            last_directive_result=result,
            dt=0,  # no time passes in heartbeat itself
            battery=self._fc.get_battery(),
        )
        self._last_heartbeat = self._state.mission_clock

    def on_event(self, event: DetectionEvent) -> None:
        """Immediate — agent preempts on high-priority detection."""
        if self._state is None:
            return

        directive = self._agent.decide(self._state)
        result = self._execute_directive(directive)
        self._state.update(
            pose=self._fc.get_pose(),
            detections=[event.detection],
            last_directive_result=result,
            dt=0,
            battery=self._fc.get_battery(),
            is_priority=True,
        )

    def run(self, max_duration: float = 300.0, mission_objectives: str = "") -> MissionResult:
        """Run the full mission until duration, battery critical, or agent lands."""
        self.start(mission_objectives)

        while self._state is not None and self._state.mission_clock < max_duration:
            self.tick(self._dt)

            # Advance time
            self._fc.step(self._dt)
            self._state.update(
                pose=self._fc.get_pose(),
                detections=[],
                last_directive_result=None,
                dt=self._dt,
                battery=self._fc.get_battery(),
            )

            # Check for priority events from new detections
            new_dets = self._perception.get_detections()
            for det in new_dets:
                event = self._priority_filter.check(det)
                if event:
                    self.on_event(event)

            # Heartbeat check
            if self._state.mission_clock - self._last_heartbeat >= self._heartbeat_interval:
                self.heartbeat()

            # Battery critical — auto-land, bypass agent
            if self._fc.get_battery() < 0.1:
                self._execute_directive(Directive(kind="land"))
                break

        nav_complete = self._sequencer.is_complete() if self._sequencer else False
        return MissionResult(
            final_pose=self._fc.get_pose(),
            battery_remaining=self._fc.get_battery(),
            objectives_status=dict(self._state.objectives_status) if self._state else {},
            nav_plan_completed=nav_complete,
            duration=self._state.mission_clock if self._state else 0,
            action_count=len(self._state.action_log) if self._state else 0,
        )

    def _execute_directive(self, directive: Directive) -> str:
        """Dispatch directive to DirectiveExecutor."""
        if self._executor is not None:
            return self._executor.execute(directive)
        return "no executor"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/integration/test_mission_loop.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/drone/mission/loop.py tests/integration/test_mission_loop.py
git commit -m "feat: MissionLoop with tick/heartbeat/event rhythms, battery auto-land"
```

---

### Task 12: Factory Gate & Project Config

**Files:**
- Modify: `pyproject.toml` — add `agent` and `sim` pytest markers, add LLM dependencies
- Modify: `scripts/gates/_proc.py` — add `AGENT_CMD`
- Modify: `scripts/gates/all.py` — add agent gate after unit

**Interfaces:**
- Consumes: nothing from prior tasks (project config only)
- Produces: pytest markers `agent`, `sim`; gate pipeline `lint → typecheck → unit → agent`

- [ ] **Step 1: Write failing test for agent marker**

```python
# tests/gates/test_all_gate.py — append this test at the end of the existing file
# (this file already exists; we add one test)

# Actually, we don't need a failing test for config changes.
# We verify by running the gate.
```

- [ ] **Step 2: Update pyproject.toml**

Add `agent` and `sim` markers and LLM dependencies:

```toml
# In [tool.pytest.ini_options], replace markers line:
markers = [
    "unit: fast deterministic tests",
    "agent: agent decision tests with mocked LLM",
    "sim: pybullet simulation tests",
]
addopts = "-m unit"
```

Add LLM SDK dependencies to `[project]` dependencies:

```toml
dependencies = [
  "jsonschema[format]>=4.21",
  "pyyaml>=6.0",
  "python-frontmatter>=1.1",
  "anthropic>=0.40",
  "google-genai>=1.0",
  "openai>=1.50",
]
```

The exact diff for `pyproject.toml`:

```diff
 markers = ["unit: fast deterministic tests"]
-markers = [
+markers = [
     "unit: fast deterministic tests",
+    "agent: agent decision tests with mocked LLM",
+    "sim: pybullet simulation tests",
 ]
```

And for dependencies:

```diff
 dependencies = [
   "jsonschema[format]>=4.21",
   "pyyaml>=6.0",
   "python-frontmatter>=1.1",
+  "anthropic>=0.40",
+  "google-genai>=1.0",
+  "openai>=1.50",
 ]
```

- [ ] **Step 3: Update gate scripts**

```python
# scripts/gates/_proc.py — add AGENT_CMD after UNIT_CMD
AGENT_CMD = ["pytest", "-m", "agent", "-q"]
```

```python
# scripts/gates/all.py — add AGENT_CMD after UNIT_CMD
import sys
from _proc import LINT_CMD, TYPECHECK_CMD, UNIT_CMD, AGENT_CMD, run_and_propagate

GATES = [LINT_CMD, TYPECHECK_CMD, UNIT_CMD, AGENT_CMD]

if __name__ == "__main__":
    for cmd in GATES:
        code = run_and_propagate(cmd)
        if code != 0:
            sys.exit(code)
    sys.exit(0)
```

- [ ] **Step 4: Run the full gate**

Run: `python scripts/gates/all.py`
Expected: exit 0 (all gates pass)

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml scripts/gates/_proc.py scripts/gates/all.py
git commit -m "feat: add agent/sim pytest markers, LLM deps, agent gate to pipeline"
```
