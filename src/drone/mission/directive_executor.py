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