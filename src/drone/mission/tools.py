"""Tool implementations — pure functions, no side effects."""
from __future__ import annotations

from drone.interfaces import WaterArea, NavContext, NavPlan, Detection
from drone.navigation.registry import NavRegistry


def plan_navigation(
    registry: NavRegistry,
    water_area: WaterArea,
    algorithm: str,
    context: NavContext,
) -> NavPlan:
    """Generate waypoints for a named algorithm."""
    algo = registry.lookup(algorithm)
    return algo.plan(water_area, context)


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
