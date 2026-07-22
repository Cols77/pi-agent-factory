"""Core data types and protocols for the drone mission system."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable, TYPE_CHECKING


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


if TYPE_CHECKING:
    from drone.mission.state import MissionState  # pyright: ignore[reportMissingImports]


@runtime_checkable
class NavigationAlgorithm(Protocol):
    """Generates a NavPlan from a water area and current context."""
    def plan(self, water: WaterArea, context: NavContext) -> NavPlan: ...
