"""Recorder — captures mission trace frames for replay and analysis."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from drone.interfaces import Pose, Detection, Directive


@dataclass
class Frame:
    """A single recorded frame in a mission trace."""

    mission_clock: float
    drone_pose: Pose
    detections: list[Detection]
    active_directive: Directive | None
    waypoint_status: dict[str, Any]


class Recorder:
    """Records mission trace frames for replay and analysis.

    Frames can be recorded at a configurable interval (default 0.5 s).
    The full trace can be retrieved with ``trace()``, and persisted to /
    restored from YAML with ``save()`` / ``load()``.
    """

    def __init__(self, record_interval: float = 0.5) -> None:
        self._record_interval = record_interval
        self._frames: list[Frame] = []
        self._last_recorded: float = -999.0

    # ── Public API ───────────────────────────────────────────────────────

    def record(
        self,
        mission_clock: float,
        drone_pose: Pose,
        detections: list[Detection],
        active_directive: Directive | None,
        waypoint_status: dict[str, Any],
    ) -> None:
        """Record a frame if enough time has elapsed since the last one."""
        if mission_clock - self._last_recorded < self._record_interval:
            return
        self._frames.append(
            Frame(
                mission_clock=mission_clock,
                drone_pose=drone_pose,
                detections=detections,
                active_directive=active_directive,
                waypoint_status=waypoint_status,
            )
        )
        self._last_recorded = mission_clock

    def trace(self) -> list[Frame]:
        """Return a copy of all recorded frames."""
        return list(self._frames)

    def save(self, path: str | Path) -> None:
        """Persist the trace to a YAML file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = []
        for frame in self._frames:
            record = {
                "mission_clock": frame.mission_clock,
                "drone_pose": {
                    "x": frame.drone_pose.x,
                    "y": frame.drone_pose.y,
                    "z": frame.drone_pose.z,
                    "heading": frame.drone_pose.heading,
                },
                "detections": [
                    {
                        "label": d.label,
                        "confidence": d.confidence,
                        "bearing": d.bearing,
                        "range": d.range,
                        "position": {
                            "x": d.position.x,
                            "y": d.position.y,
                            "z": d.position.z,
                            "heading": d.position.heading,
                        },
                    }
                    for d in frame.detections
                ],
                "active_directive": (
                    {
                        "kind": frame.active_directive.kind,
                        "args": dict(frame.active_directive.args),
                    }
                    if frame.active_directive
                    else None
                ),
                "waypoint_status": frame.waypoint_status,
            }
            data.append(record)
        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False)

    @classmethod
    def load(cls, path: str | Path) -> Recorder:
        """Load a trace from a YAML file and return a new Recorder."""
        with open(path) as f:
            data = yaml.safe_load(f)
        recorder = cls(record_interval=0.0)
        for item in data:
            dp = item["drone_pose"]
            pose = Pose(x=dp["x"], y=dp["y"], z=dp["z"], heading=dp["heading"])
            dets = []
            for d in item["detections"]:
                p = d["position"]
                dets.append(
                    Detection(
                        label=d["label"],
                        confidence=d["confidence"],
                        bearing=d["bearing"],
                        range=d["range"],
                        position=Pose(x=p["x"], y=p["y"], z=p["z"], heading=p["heading"]),
                    )
                )
            directive = None
            if item["active_directive"]:
                ad = item["active_directive"]
                directive = Directive(kind=ad["kind"], args=ad["args"])
            recorder._frames.append(
                Frame(
                    mission_clock=item["mission_clock"],
                    drone_pose=pose,
                    detections=dets,
                    active_directive=directive,
                    waypoint_status=item["waypoint_status"],
                )
            )
        return recorder