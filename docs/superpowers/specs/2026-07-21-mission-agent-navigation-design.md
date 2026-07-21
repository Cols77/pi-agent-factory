# Mission Agent & Navigation Design Spec

> Spec for the drone mission decision agent and navigation layer.
> Simulated perception only (ScriptedPerception); real camera + telekinesis deferred to Plan A.

## 1. Purpose

Build the "brain" of a drone mission system: a stateful LLM-backed agent that receives mission context, uses tools to plan and update navigation, and issues directives that a waypoint sequencer translates into flight controller calls. The agent can be preempted by high-priority detections (e.g., distress).

This spec covers:

- Core data types and protocols (extending `src/drone/interfaces.py`)
- `MissionState` accumulator and NL summary
- `MissionLoop` with three rhythms (tick, heartbeat, event)
- `LlmAgent` with configurable model chain and tool-calling
- `FakeAgent` for deterministic testing
- `WaypointSequencer` for the fast flight loop
- `NavigationAlgorithm` registry with one concrete implementation (`PerimeterSweep`)
- `PriorityFilter` for event-driven agent preemption
- `ScriptedPerception` for deterministic simulated detections
- Factory gate updates (new `agent` pytest marker)

This spec does NOT cover:

- Real camera input or telekinesis transport (Plan A)
- PyBullet camera rendering or water segmentation (Plan A)
- Visual object detection models (Plan A)
- Real drone hardware integration (Plan A)

## 2. Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      Mission Loop                        │
│                                                          │
│  ┌──────────────┐    ┌──────────────┐    ┌────────────┐  │
│  │ Perception   │───▶│ MissionState │───▶│   Agent     │  │
│  │ (scripted)   │    │ (accumulator) │    │ (LLM/Fake) │  │
│  └──────────────┘    └──────────────┘    └─────┬──────┘  │
│        │                    ▲                 │tools     │
│        │                    │                 ▼          │
│        │             ┌──────────────┐   ┌───────────┐  │
│        │             │  Waypoint    │◀──│ NavAlgo   │  │
│        │             │  Sequencer   │   │ Registry   │  │
│        │             └──────┬───────┘   └───────────┘  │
│        │                    │                          │
│        ▼                    ▼                          │
│  ┌──────────────────────────────────────────────────┐  │
│  │             FlightController (fake)               │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

Three coexisting rhythms:

- **Fast loop** (every `dt`): `WaypointSequencer.step(dt)` → `fc.goto()` + `fc.step()`. No LLM.
- **Heartbeat** (every N seconds): agent reviews full `MissionState.summary()`, may update nav plan or issue a directive.
- **Event interrupt** (immediate): `PriorityFilter` flags a high-confidence high-priority detection → `on_event()` calls agent out of band.

The agent never drives the flight controller directly. It returns a `Directive`; the `DirectiveExecutor` translates that into `WaypointSequencer`/`FlightController` actions.

## 3. Core Data Types & Protocols

All new types extend `src/drone/interfaces.py`.

### 3.1 WaterArea

```python
@dataclass(frozen=True)
class WaterArea:
    """2D polygon representing the water boundary."""
    vertices: list[tuple[float, float]]  # [(x, y), ...] ordered, closed
```

### 3.2 NavPlan

```python
@dataclass(frozen=True)
class NavPlan:
    """Named sequence of waypoints for the sequencer to follow."""
    waypoints: list[Pose]
    algorithm_name: str
    created_at: float  # mission clock at creation time
```

### 3.3 Directive

```python
@dataclass(frozen=True)
class Directive:
    """Agent output — what the mission loop should do next."""
    kind: str  # "update_nav", "override", "continue", "land", "return_base"
    args: dict[str, object] = field(default_factory=dict)
```

Valid `kind` values:

- `update_nav`: args must contain `nav_plan: NavPlan`. Replace current navigation plan.
- `override`: args must contain `detection: Detection`. Fly to investigate a target, replacing current plan.
- `continue`: no args. Keep following the current plan.
- `land`: no args. Initiate landing.
- `return_base`: no args. Fly back to origin and land.

### 3.4 NavContext

```python
@dataclass(frozen=True)
class NavContext:
    """Context for navigation planning (drone pose, coverage history)."""
    current_pose: Pose
    completed_area: list[tuple[float, float]]  # already-visited positions
```

### 3.5 MissionPlanner Protocol

```python
@runtime_checkable
class MissionPlanner(Protocol):
    """Stateful agent — called with full mission context."""
    def decide(self, state: MissionState) -> Directive: ...
```

The existing `Planner` protocol (`decide(pose, detections) -> Command`) remains for simple reactive agents. `MissionPlanner` is the stateful entry point for the LLM agent.

### 3.6 NavigationAlgorithm Protocol

```python
@runtime_checkable
class NavigationAlgorithm(Protocol):
    """Generates a NavPlan from a water area and current context."""
    def plan(self, water: WaterArea, context: NavContext) -> NavPlan: ...
```

### 3.7 PriorityRule

```python
@dataclass(frozen=True)
class PriorityRule:
    """Rule for detecting high-priority events from detections."""
    label: str             # match detection label (exact)
    min_confidence: float  # minimum confidence to trigger
    reason_template: str   # e.g. "possible {label}"
```

### 3.8 DetectionEvent

```python
@dataclass(frozen=True)
class DetectionEvent:
    """A detection that triggered a priority rule."""
    detection: Detection
    reason: str  # e.g. "possible distress"
```

## 4. MissionState

File: `src/drone/mission/state.py`

Mutable accumulator — the single source of truth the agent reads.

### 4.1 Fields

```python
class MissionState:
    # Identity
    mission_objectives: str          # NL string, set once at mission start
    mission_clock: float             # elapsed simulation time in seconds

    # Perception log
    all_detections: list[Detection]  # full detection history
    new_detections: list[Detection]  # detections since last agent call

    # Navigation
    nav_plan: NavPlan | None         # active navigation plan (or None)
    current_waypoint_idx: int        # index of next waypoint to reach
    waypoints_completed: int         # waypoints already reached
    waypoints_total: int             # total waypoints in current plan

    # Action history
    action_log: list[tuple[float, Directive]]  # (mission_clock, directive) pairs

    # Objective tracking
    objectives_status: dict[str, str]  # {"survey_water": "in_progress", ...}
    # Valid status values: "pending", "in_progress", "complete", "failed"

    # Drone state
    current_pose: Pose
    battery: float
```

### 4.2 Methods

```python
def update(self, pose: Pose, detections: list[Detection], last_directive_result: str | None, *, is_priority: bool = False) -> None:
    """Ingest new data. Advances mission clock, accumulates detections,
    clears new_detections for next call."""

def summary(self) -> str:
    """Produce NL text for the LLM agent. Format specified in §4.3."""

def advance_waypoint(self) -> None:
    """Called by sequencer when a waypoint is reached. Increments idx, updates status."""

def set_nav_plan(self, plan: NavPlan) -> None:
    """Replace the active navigation plan. Resets waypoint tracking."""

def mark_objective(self, objective_id: str, status: str) -> None:
    """Update an objective's status."""
```

### 4.3 Summary format

`summary()` produces structured NL text:

```
MISSION: <mission_objectives>

TIME ELAPSED: <mission_clock>s

CURRENT STATUS: <narrative status derived from nav plan and objectives>

PREVIOUS ACTIONS:
- [<time>s] <directive.kind> → <brief description>

NEW DETECTIONS (since last call):
- <label> at bearing <X>° range <Y>m confidence <Z> [LOW | MEDIUM | HIGH] [PRIORITY]

DETECTION SUMMARY:
- <count> <label>s detected total, <N> classified ≥0.90, <M> pending

OBJECTIVES:
- <objective_id>: <status> [<progress detail>]

NAV PLAN: <algorithm_name>, waypoints <completed>/<total> complete
- [No active nav plan] (if nav_plan is None)

BATTERY: <level>% [CRITICAL if < 10%]
```

Confidence levels in summary: `< 0.5` = LOW, `0.5–0.9` = MEDIUM, `≥ 0.9` = HIGH.

## 5. MissionLoop

File: `src/drone/mission/loop.py`

### 5.1 Constructor

```python
class MissionLoop:
    def __init__(
        self,
        fc: FlightController,
        perception: Perception,
        agent: MissionPlanner,
        algorithms: dict[str, NavigationAlgorithm],
        priority_rules: list[PriorityRule] | None = None,
        heartbeat_interval: float = 5.0,  # seconds between heartbeats
        dt: float = 0.05,                   # fast-loop timestep
    ): ...
```

### 5.2 Methods

```python
def start(self, mission_objectives: str) -> None:
    """Arm, take off, initialize MissionState, begin mission."""

def tick(self, dt: float) -> None:
    """Fast loop — sequencer drives FC toward current waypoint.
    Called every dt. No LLM call."""

def heartbeat(self) -> None:
    """Slow loop — agent reviews full state, may issue Directive.
    Called every heartbeat_interval seconds."""

def on_event(self, event: DetectionEvent) -> None:
    """Immediate — agent preempts on high-priority detection.
    Calls agent.decide() with updated state."""

def run(self, max_duration: float = 300.0) -> MissionResult:
    """Run the full mission: tick + heartbeat loop until duration expires,
    battery critical, or agent issues land/return_base."""

def _execute_directive(self, directive: Directive) -> None:
    """Dispatch directive to DirectiveExecutor."""
```

### 5.3 Main loop logic

```python
def run(self, max_duration):
    self.start(...)
    while self.state.mission_clock < max_duration:
        self.tick(self.dt)

        # Check for priority events from new detections
        new_dets = self.perception.get_detections()
        for det in new_dets:
            event = self.priority_filter.check(det)
            if event:
                self.on_event(event)

        # Heartbeat check
        if self.state.mission_clock - self._last_heartbeat >= self.heartbeat_interval:
            self.heartbeat()

        # Battery critical — auto-land, bypass agent
        if self.fc.get_battery() < 0.1:
            self._execute_directive(Directive(kind="land"))
            break
```

### 5.4 MissionResult

```python
@dataclass(frozen=True)
class MissionResult:
    final_pose: Pose
    battery_remaining: float
    objectives_status: dict[str, str]
    nav_plan_completed: bool
    duration: float
    action_count: int
```

## 6. PriorityFilter

File: `src/drone/mission/priority_filter.py`

```python
class PriorityFilter:
    def __init__(self, rules: list[PriorityRule] | None = None): ...

    def check(self, detection: Detection) -> DetectionEvent | None:
        """Return a DetectionEvent if any rule matches, else None.
        A rule matches when detection.label == rule.label
        AND detection.confidence >= rule.min_confidence."""

    @classmethod
    def default(cls) -> PriorityFilter:
        """Default rules: distress at ≥0.8 confidence."""
        return cls(rules=[
            PriorityRule(label="distress", min_confidence=0.8, reason_template="possible {label}"),
        ])
```

## 7. WaypointSequencer

File: `src/drone/navigation/waypoint_sequencer.py`

```python
class WaypointSequencer:
    """Ticks the flight controller toward the current waypoint."""

    WAYPOINT_REACH_THRESHOLD = 0.5  # meters — close enough = reached

    def __init__(self, fc: FlightController): ...

    def set_plan(self, plan: NavPlan) -> None:
        """Set or replace the active nav plan. Resets to waypoint 0."""

    def step(self, dt: float) -> bool:
        """Advance toward current waypoint. Returns True if waypoint was reached this step.
        Calls fc.goto(current_waypoint.x, .y, .z) then fc.step(dt).
        If distance to waypoint < WAYPOINT_REACH_THRESHOLD, advance idx."""

    def is_complete(self) -> bool:
        """All waypoints reached."""

    def status(self) -> dict:
        """{"current_idx": N, "total": M, "completed": K, "plan_name": str}"""
```

## 8. NavigationAlgorithm Registry

File: `src/drone/navigation/registry.py`

```python
class NavRegistry:
    """Registry of named NavigationAlgorithm implementations."""

    def register(self, name: str, algorithm: NavigationAlgorithm) -> None: ...
    def lookup(self, name: str) -> NavigationAlgorithm: ...
    def list_algorithms(self) -> list[str]: ...
```

Raises `KeyError` on lookup for unregistered name.

## 9. PerimeterSweepAlgorithm

File: `src/drone/navigation/perimeter_sweep.py`

Traces the water polygon perimeter at a fixed inward offset and constant altitude, with a maximum distance from shore constraint for sea/large water bodies.

### 9.1 Constructor

```python
class PerimeterSweepAlgorithm:
    def __init__(
        self,
        altitude: float = 5.0,
        offset: float = 2.0,
        max_distance_from_shore: float | None = None,
    ): ...
```

- `altitude`: flight height in meters.
- `offset`: inward offset from the water polygon boundary in meters.
- `max_distance_from_shore`: if set, only includes waypoints within this distance of the nearest shoreline point. `None` means no limit (full sweep).

### 9.2 plan()

```python
def plan(self, water: WaterArea, context: NavContext) -> NavPlan:
    # 1. Inset the polygon by `offset` (move each edge inward along its
    #    normal, intersect adjacent offset edges to get new vertices)
    # 2. If max_distance_from_shore is set, clip vertices that are farther
    #    than max_distance_from_shore from any original polygon edge
    # 3. Generate Pose waypoints at each remaining vertex, at `altitude`
    # 4. Order waypoints starting from the vertex closest to
    #    context.current_pose, proceeding clockwise
    # 5. Close the loop (append first waypoint at end)
    # 6. Return NavPlan(waypoints=..., algorithm_name="perimeter_sweep")
```

### 9.3 Inset algorithm (simplified)

For each edge of the polygon, compute the inward-pointing unit normal. Offset each edge by `offset` meters along its normal. Intersect adjacent offset edges to produce new vertices. If adjacent offset edges are parallel (no intersection), use the midpoint of the two offset edge endpoints.

## 10. ScriptedPerception

File: `src/drone/mission/scripted_perception.py`

```python
class ScriptedPerception:
    """Deterministic Perception implementation for testing.

    Returns predetermined detections per call, following a script."""
    def __init__(self, script: list[list[Detection]]): ...

    def get_detections(self) -> list[Detection]:
        """Return next scripted detection list. Returns empty list after script exhausted."""
```

Also provides convenience builders:

```python
@classmethod
def constant(cls, detections: list[Detection]) -> ScriptedPerception:
    """Returns the same detections every call (infinite repeat)."""

@classmethod
def sequential(cls, steps: list[list[Detection]]) -> ScriptedPerception:
    """Returns steps[0], steps[1], ..., then empty lists."""
```

## 11. FakeAgent

File: `src/drone/mission/fake_agent.py`

For testing only. Not used in production.

```python
class FakeAgent:
    """Deterministic MissionPlanner for testing."""

    def __init__(self, responses: list[Directive] | None = None): ...

    def decide(self, state: MissionState) -> Directive:
        """Return next scripted directive. Returns Directive(kind="continue") after script exhausted."""
```

## 12. LlmAgent

File: `src/drone/mission/llm_agent.py`

Real LLM-backed `MissionPlanner`. Configurable model chain with automatic fallback.

### 12.1 Model chain config

```python
@dataclass(frozen=True)
class ModelConfig:
    provider: str   # "google" | "anthropic" | "openrouter" | "openai_compat"
    model: str      # e.g. "gemini-robotics-er-1.6"
    api_key: str     # resolved from env var at construction time, never stored as raw env name
```

```python
class LlmAgent:
    def __init__(
        self,
        model_chain: list[ModelConfig],
        tools: list[ToolDef],
    ): ...
```

The agent tries models in chain order. If a model fails (API error, timeout), it falls back to the next in the chain.

### 12.2 Model chain examples

| Priority | Model | Provider |
|----------|-------|---------|
| 1 | Gemini Robotics-ER 1.6 | Google |
| 2 | Gemini 3.1 Flash-Lite | Google |
| 3 | Qwen2.5-VL-7B | OpenRouter |
| 4 | Cosmos-Reason2-8B | OpenRouter (availability-dependent) |

### 12.3 Provider adapters

Each provider has a thin adapter that translates the same tool schemas + Directive parse into each API's format:

- `google` adapter: uses `google-genai` SDK, function-calling format
- `anthropic` adapter: uses `anthropic` SDK, tool-use blocks
- `openrouter` / `openai_compat` adapter: uses `openai` SDK (OpenRouter is OpenAI-compatible)

All adapters implement the same internal interface:

```python
class ProviderAdapter(Protocol):
    def create(self, model: str, system: str, messages: list, tools: list[ToolDef]) -> ProviderResponse: ...
```

### 12.4 Tool-calling flow

The agent constructs a prompt from `MissionState.summary()`, offers a fixed set of tools, and returns the `Directive` parsed from the LLM's final response.

**Tool-calling loop** (LLM may call multiple tools before returning a Directive):

1. Send `state.summary()` as user message + system prompt + tool schemas
2. If LLM returns tool_use blocks, execute each tool, feed results back, get next response
3. If LLM returns end_turn with a Directive, parse it
4. If Directive parsing fails, return `Directive(kind="continue")` as safe fallback

### 12.5 Agent tools

| Tool | Parameters | Returns | Purpose |
|------|-----------|---------|--------|
| `plan_navigation` | `water_area: WaterArea, algorithm: str, max_distance_from_shore: float | None` | `NavPlan` | Generate waypoints for a named algorithm |
| `update_navigation` | `nav_plan: NavPlan` | `NavPlan` | Replace current nav plan mid-flight |
| `abort_navigation` | — | — | Cancel current nav, hover in place |
| `investigate_target` | `detection: Detection` | `NavPlan` | Single-waypoint plan to fly to a detection |
| `get_mission_status` | — | `str` | Read current state (no side effect) |
| `mark_objective` | `objective_id: str, status: str` | — | Update objective tracking |

Tool implementations are pure functions — no side effects until the mission loop acts on the `Directive`.

- `plan_navigation` delegates to the `NavRegistry` to look up the named algorithm and call its `plan()` method
- `investigate_target` builds a single-waypoint `NavPlan` pointing at the detection's position
- `get_mission_status` returns `MissionState.summary()` again
- `mark_objective` returns nothing but the tool result confirms the update was noted

### 12.6 System prompt

```
You are a drone mission controller. You receive a mission status summary
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
  Valid kinds: update_nav, override, continue, land, return_base.
```

## 13. DirectiveExecutor

File: `src/drone/mission/directive_executor.py`

Translates a `Directive` into concrete actions on the `WaypointSequencer` and `FlightController`.

```python
class DirectiveExecutor:
    def __init__(self, fc: FlightController, sequencer: WaypointSequencer, state: MissionState): ...

    def execute(self, directive: Directive) -> str:
        """Execute a directive. Returns a result description for the next MissionState.update()."""
```

Directive dispatch:

| Directive kind | Action |
|---------------|--------|
| `update_nav` | `sequencer.set_plan(directive.args["nav_plan"])`, `state.set_nav_plan(...)` |
| `override` | Build investigation NavPlan from detection, `sequencer.set_plan(...)`, `state.set_nav_plan(...)` |
| `continue` | No-op |
| `land` | `fc.land()` |
| `return_base` | Build NavPlan to Pose(0,0,0,0), `sequencer.set_plan(...)`, `fc.land()` when sequencer complete |

## 14. Error Handling

| Failure | Detection | Recovery |
|---------|-----------|----------|
| LLM API timeout/error | `except (APIError, Timeout)` | Return `Directive(kind="continue")` — keep current plan |
| Malformed Directive JSON | `_parse_directive` fails | Return `Directive(kind="continue")` |
| Tool execution error | Exception in tool implementation | Return error string as tool_result, let LLM retry |
| No nav plan set, agent returns `continue` | MissionLoop detects no active plan | Force a `plan_navigation` tool call on next heartbeat |
| Waypoint sequencer stuck (no progress) | Same pose for N consecutive ticks | Inject a "stuck" status into MissionState.summary(), agent must decide |
| Battery critical (<10%) | `fc.get_battery() < 0.1` | MissionLoop auto-issues `Directive(kind="land")`, bypasses agent |

## 15. Testing Strategy

### 15.1 Test pyramid

```
        ┌─────────────────┐
        │  Integration     │  mission_loop test with FakeAgent + FakeFC
        │  (few, slow)     │  + ScriptedPerception
        ├─────────────────┤
        │  Functional      │  agent scenarios: given mission state X →
        │  (moderate)      │  expect directive Y (mocked LLM)
        ├─────────────────┤
        │  Unit (many,     │  MissionState, WaypointSequencer, PriorityFilter,
        │  fast)           │  NavPlan, Directive, PerimeterSweep, summary()
        └─────────────────┘
```

### 15.2 Unit tests (marker: `unit`)

Pure Python, no LLM calls, no sim:

- `MissionState` construction, `update()`, `summary()` formatting, `advance_waypoint()`, `set_nav_plan()`, `mark_objective()`
- `WaypointSequencer` step logic with `FakeFlightController`
- `PerimeterSweepAlgorithm.plan()` given a `WaterArea` polygon → correct `NavPlan`
- `PriorityFilter` rule matching (hit and miss cases)
- `Directive` kind/args validation
- `NavContext` / `WaterArea` construction
- `NavRegistry` register, lookup, KeyError on unknown

### 15.3 Functional tests (marker: `agent`)

Mock the LLM API call, test agent decision logic:

- `FakeAgent` returns scripted directives
- Scenario: nav plan at waypoint 5, new high-confidence distress detection → expect `Directive(kind="override")`
- Scenario: all waypoints complete, all objectives met → expect `Directive(kind="land")`
- Scenario: first heartbeat, no nav plan yet → expect `Directive(kind="update_nav")`
- Scenario: LLM API fails → fallback `Directive(kind="continue")`

### 15.4 Integration tests

Full `MissionLoop` with `FakeAgent` + `FakeFlightController` + `ScriptedPerception`:

- Run N ticks + heartbeats, assert final pose, nav plan status, objectives
- Inject a priority detection at tick M, assert the agent was called out-of-band
- Battery critical → auto-land without agent call

No dedicated pytest marker — runs in CI or locally, not in the standard gate.

## 16. Factory Gate Updates

### 16.1 New pytest marker

```toml
[tool.pytest.ini_options]
markers = [
    "unit: fast deterministic tests",
    "agent: agent decision tests with mocked LLM",
    "sim: pybullet simulation tests",
]
addopts = "-m unit"
```

### 16.2 Gate script change

`scripts/gates/all.py` adds `pytest -m agent` after the unit gate, before sim:

```
ruff check → pyright → pytest -m unit → pytest -m agent → pytest -m sim
```

### 16.3 New test directories

```
tests/
  unit/
    test_mission_state.py
    test_waypoint_sequencer.py
    test_perimeter_sweep.py
    test_priority_filter.py
    test_directive.py
    test_nav_registry.py
    test_water_area.py
  agent/
    test_fake_agent.py
    test_agent_scenarios.py
    test_llm_agent.py
    test_directive_executor.py
  integration/
    test_mission_loop.py
```

## 17. Dependencies

### 17.1 Added to `pyproject.toml`

```toml
dependencies = [
    # existing...
    "anthropic>=0.40",
    "google-genai>=1.0",
    "openai>=1.50",
]
```

### 17.2 Deferred

- `telekinesis>=0.1.97` — not needed until Plan A (real camera transport)

## 18. File Structure Summary

```
src/drone/
  interfaces.py              # MODIFIED: add WaterArea, NavPlan, Directive, MissionPlanner, NavigationAlgorithm, NavContext, PriorityRule, DetectionEvent, ModelConfig
  fake_flight_controller.py  # existing, unchanged
  pybullet_flight_controller.py  # existing, unchanged
  scenarios/
    takeoff_hover_land.py    # existing, unchanged
  mission/
    __init__.py
    state.py                 # MissionState
    loop.py                   # MissionLoop + MissionResult
    priority_filter.py       # PriorityFilter
    scripted_perception.py    # ScriptedPerception
    fake_agent.py            # FakeAgent
    llm_agent.py             # LlmAgent + ProviderAdapter + tool schemas
    tools.py                 # Tool implementations
    directive_executor.py    # DirectiveExecutor
  navigation/
    __init__.py
    waypoint_sequencer.py    # WaypointSequencer
    registry.py              # NavRegistry
    perimeter_sweep.py       # PerimeterSweepAlgorithm

tests/
  unit/
    test_mission_state.py
    test_waypoint_sequencer.py
    test_perimeter_sweep.py
    test_priority_filter.py
    test_directive.py
    test_nav_registry.py
    test_water_area.py
  agent/
    test_fake_agent.py
    test_agent_scenarios.py
    test_llm_agent.py
    test_directive_executor.py
  integration/
    test_mission_loop.py
```