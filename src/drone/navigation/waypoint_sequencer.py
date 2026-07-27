"""WaypointSequencer — ticks the flight controller toward the current waypoint."""

from __future__ import annotations

import math

from drone.interfaces import FlightController, NavPlan


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
            raise RuntimeError("no nav plan set — call set_plan() before step()")

        if self._current_idx >= len(self._plan.waypoints):
            return False

        wp = self._plan.waypoints[self._current_idx]
        self._fc.goto(wp.x, wp.y, wp.z)
        self._fc.step(dt)

        pose = self._fc.get_pose()
        dist = math.sqrt(
            (pose.x - wp.x) ** 2 + (pose.y - wp.y) ** 2 + (pose.z - wp.z) ** 2
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
        """Return status dict with current_idx, total, completed, plan_name."""
        total = len(self._plan.waypoints) if self._plan is not None else 0
        name = self._plan.algorithm_name if self._plan is not None else ""
        return {
            "current_idx": self._current_idx,
            "total": total,
            "completed": self._completed,
            "plan_name": name,
        }