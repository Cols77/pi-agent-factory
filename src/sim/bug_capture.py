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