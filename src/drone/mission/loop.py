"""MissionLoop — the main loop tying perception, agent, and navigation together."""
from __future__ import annotations

from dataclasses import dataclass

from drone.interfaces import (
    DetectionEvent,
    Directive,
    FlightController,
    MissionPlanner,
    Perception,
    Pose,
)
from drone.mission.state import MissionState
from drone.mission.priority_filter import PriorityFilter
from drone.mission.directive_executor import DirectiveExecutor
from drone.navigation.waypoint_sequencer import WaypointSequencer


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
        priority_rules: list | None = None,
        heartbeat_interval: float = 5.0,
        dt: float = 0.05,
    ) -> None:
        self._fc = fc
        self._perception = perception
        self._agent = agent
        self._priority_filter = (
            PriorityFilter(rules=priority_rules)
            if priority_rules
            else PriorityFilter.default()
        )
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
        # Step the FC until takeoff altitude is reached
        # Use dt=0 for state updates so the mission clock doesn't
        # advance during the initialization phase
        for _ in range(200):
            self._fc.step(self._dt)
            if self._fc.get_pose().z >= 4.9:
                break

        # Initialize state with takeoff pose but zero clock time
        self._state.update(
            pose=self._fc.get_pose(),
            detections=[],
            last_directive_result=None,
            dt=0,
            battery=self._fc.get_battery(),
        )

        self._last_heartbeat = 0.0

    def tick(self, dt: float) -> None:
        """Fast loop — sequencer drives FC toward current waypoint."""
        if self._sequencer is None:
            return
        status = self._sequencer.status()
        if not status["plan_name"]:
            return  # no nav plan set yet
        if status["current_idx"] >= status["total"]:
            return  # all waypoints complete

        reached = self._sequencer.step(dt)
        if reached and self._state is not None:
            self._state.advance_waypoint()

    def heartbeat(self) -> Directive | None:
        """Slow loop — agent reviews full state, may issue Directive.

        Returns the directive so the caller can check for termination.
        """
        if self._state is None:
            return None

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
        return directive

    def on_event(self, event: DetectionEvent) -> Directive | None:
        """Immediate — agent preempts on high-priority detection.

        Returns the directive so the caller can check for termination.
        """
        if self._state is None:
            return None

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
        return directive

    def run(
        self, max_duration: float = 300.0, mission_objectives: str = ""
    ) -> MissionResult:
        """Run the full mission until duration, battery critical, or agent lands."""
        self.start(mission_objectives)

        while (
            self._state is not None
            and self._state.mission_clock < max_duration
        ):
            self._tick_advance()

            if self._handle_priority_events():
                break
            if self._handle_heartbeat():
                break
            if self._handle_battery_critical():
                break

        nav_complete = (
            self._sequencer.is_complete() if self._sequencer else False
        )
        return MissionResult(
            final_pose=self._fc.get_pose(),
            battery_remaining=self._fc.get_battery(),
            objectives_status=dict(self._state.objectives_status)
            if self._state
            else {},
            nav_plan_completed=nav_complete,
            duration=self._state.mission_clock if self._state else 0,
            action_count=len(self._state.action_log) if self._state else 0,
        )

    # ── helpers ──────────────────────────────────────────────────────────

    def _tick_advance(self) -> None:
        """Run the fast-loop tick then advance simulation time.

        When a nav plan is active, ``tick()`` already steps the FC through
        the sequencer (``sequencer.step()`` -> ``fc.step()``).  We must NOT
        step the FC again here, otherwise the drone moves at 2× speed.
        """
        self.tick(self._dt)

        # Only step the FC directly when no sequencer plan is active.
        # When a plan IS active, tick() already stepped the FC via
        # sequencer.step().
        has_active_plan = (
            self._sequencer is not None
            and self._sequencer.status()["plan_name"]
            and self._sequencer.status()["current_idx"]
            < self._sequencer.status()["total"]
        )
        if not has_active_plan:
            self._fc.step(self._dt)

        if self._state is not None:
            self._state.update(
                pose=self._fc.get_pose(),
                detections=[],
                last_directive_result=None,
                dt=self._dt,
                battery=self._fc.get_battery(),
            )

    def _handle_priority_events(self) -> bool:
        """Check detections for priority events. Returns True if mission should end."""
        if self._state is None:
            return False
        for det in self._perception.get_detections():
            event = self._priority_filter.check(det)
            if event:
                directive = self.on_event(event)
                if directive is not None and directive.kind == "land":
                    return True
        return False

    def _handle_heartbeat(self) -> bool:
        """Run heartbeat if interval elapsed. Returns True if mission should end."""
        if self._state is None:
            return False
        elapsed = self._state.mission_clock - self._last_heartbeat
        if elapsed >= self._heartbeat_interval:
            directive = self.heartbeat()
            if directive is not None and directive.kind == "land":
                return True
        return False

    def _handle_battery_critical(self) -> bool:
        """Auto-land when battery is critical. Returns True if mission should end."""
        if self._fc.get_battery() < 0.1:
            self._execute_directive(Directive(kind="land"))
            return True
        return False

    def _execute_directive(self, directive: Directive) -> str:
        """Dispatch directive to DirectiveExecutor."""
        if self._executor is not None:
            return self._executor.execute(directive)
        return "no executor"