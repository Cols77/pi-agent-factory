"""CLI tool: convert a bug snapshot to a factory task."""
from __future__ import annotations

import sys
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


def _extract_task_name(snapshot_data: dict[str, Any]) -> str:
    """Derive a safe filename slug from the snapshot name."""
    return str(snapshot_data.get("name", "bug-fix")).replace(" ", "-")


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
    task_name = _extract_task_name(snapshot)

    tasks_dir = Path("tasks")
    tasks_dir.mkdir(exist_ok=True)
    task_path = tasks_dir / f"T-{task_name}.md"

    with open(task_path, "w") as f:
        f.write(description)

    print(f"Task created: {task_path}")
    print("  To register it in the factory ledger, run plan_to_tasks on the")
    print("  source plan or add the task to the ledger manually.")
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