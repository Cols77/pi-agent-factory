"""Mutable mission-state accumulator used as the agent's source of truth."""
from __future__ import annotations

from drone.interfaces import Detection, NavPlan, Pose


def _confidence_label(confidence: float) -> str:
    if confidence < 0.5:
        return "LOW"
    if confidence < 0.9:
        return "MEDIUM"
    return "HIGH"


class MissionState:
    """Accumulate mission telemetry, progress, detections, and actions."""

    def __init__(self, mission_objectives: str) -> None:
        self.mission_objectives = mission_objectives
        self.mission_clock = 0.0

        self.all_detections: list[Detection] = []
        self.new_detections: list[Detection] = []

        self.nav_plan: NavPlan | None = None
        self.current_waypoint_idx = 0
        self.waypoints_completed = 0
        self.waypoints_total = 0

        self.action_log: list[tuple[float, str]] = []
        self.objectives_status: dict[str, str] = {}

        self.current_pose = Pose()
        self.battery = 1.0

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
        """Ingest the latest telemetry and detections."""
        self.mission_clock += dt
        self.current_pose = pose
        if battery is not None:
            self.battery = battery

        self.new_detections = list(detections)
        self.all_detections.extend(detections)

        if last_directive_result is not None:
            self.action_log.append((self.mission_clock, last_directive_result))

    def summary(self) -> str:
        """Render the accumulated mission context as agent-readable text."""
        lines = [
            f"MISSION: {self.mission_objectives}",
            "",
            f"TIME ELAPSED: {self.mission_clock:.1f}s",
            "",
        ]

        if self.nav_plan is None:
            status_parts = ["No active navigation plan"]
        else:
            status_parts = [f"Following {self.nav_plan.algorithm_name} plan"]
        active_objectives = [
            objective
            for objective, status in self.objectives_status.items()
            if status == "in_progress"
        ]
        if active_objectives:
            status_parts.append(
                f"objectives in progress: {', '.join(active_objectives)}"
            )
        lines.extend([f"CURRENT STATUS: {'; '.join(status_parts)}", ""])

        lines.append("PREVIOUS ACTIONS:")
        if self.action_log:
            lines.extend(
                f"- [{clock:.1f}s] {description}"
                for clock, description in self.action_log[-10:]
            )
        else:
            lines.append("- (none)")
        lines.append("")

        lines.append("NEW DETECTIONS (since last call):")
        if self.new_detections:
            for detection in self.new_detections:
                lines.append(
                    f"- {detection.label} at bearing {detection.bearing:.0f}° "
                    f"range {detection.range:.1f}m confidence "
                    f"{detection.confidence:.2f} "
                    f"{_confidence_label(detection.confidence)}"
                )
        else:
            lines.append("- (none)")
        lines.append("")

        lines.append("DETECTION SUMMARY:")
        confidences_by_label: dict[str, list[float]] = {}
        for detection in self.all_detections:
            confidences_by_label.setdefault(detection.label, []).append(
                detection.confidence
            )
        for label, confidences in confidences_by_label.items():
            high = sum(confidence >= 0.9 for confidence in confidences)
            pending = sum(confidence < 0.5 for confidence in confidences)
            lines.append(
                f"- {len(confidences)} {label}(s) detected total, "
                f"{high} classified ≥0.90, {pending} pending"
            )
        lines.append("")

        lines.append("OBJECTIVES:")
        if self.objectives_status:
            lines.extend(
                f"- {objective}: {status}"
                for objective, status in self.objectives_status.items()
            )
        else:
            lines.append("- (none)")
        lines.append("")

        lines.append("NAV PLAN:")
        if self.nav_plan is None:
            lines.append("- [No active nav plan]")
        else:
            lines.append(
                f"{self.nav_plan.algorithm_name}, waypoints "
                f"{self.waypoints_completed}/{self.waypoints_total} complete"
            )
        lines.append("")

        battery = f"{self.battery * 100:.0f}%"
        if self.battery < 0.1:
            battery += " [CRITICAL]"
        lines.append(f"BATTERY: {battery}")
        return "\n".join(lines)

    def advance_waypoint(self) -> None:
        """Record completion of the current waypoint, when one remains."""
        if self.nav_plan is not None and self.current_waypoint_idx < self.waypoints_total:
            self.current_waypoint_idx += 1
            self.waypoints_completed += 1

    def set_nav_plan(self, plan: NavPlan) -> None:
        """Replace the navigation plan and reset waypoint progress."""
        self.nav_plan = plan
        self.current_waypoint_idx = 0
        self.waypoints_completed = 0
        self.waypoints_total = len(plan.waypoints)

    def mark_objective(self, objective_id: str, status: str) -> None:
        """Set an objective's current status."""
        self.objectives_status[objective_id] = status
