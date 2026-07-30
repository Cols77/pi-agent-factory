"""Scenario dataclass and YAML I/O for simulation testbench."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import yaml


@dataclass
class Zone:
    """A named polygonal zone in the simulation world."""
    id: str
    label: str
    polygon: list[list[float]]
    color: list[int]  # RGBA


@dataclass
class SpawnerRule:
    """Rule for spawning detection entities."""
    label: str
    pool: str
    count: int
    start_time: float
    interval: float
    speed: float


@dataclass
class Scenario:
    """Complete simulation scenario definition."""
    name: str
    description: str
    sea_polygon: dict
    zones: list[Zone]
    navigation: dict
    agent: dict
    detections: dict
    priority_rules: list[dict] | None = None
    max_duration: float = 300.0

    @classmethod
    def load(cls, path: str | Path) -> Scenario:
        """Load a Scenario from a YAML file."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Scenario file not found: {path}")
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls._from_dict(data)

    def save(self, path: str | Path) -> None:
        """Save this Scenario to a YAML file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            yaml.dump(self._to_dict(), f, default_flow_style=False)

    @classmethod
    def _from_dict(cls, data: dict) -> Scenario:
        """Build a Scenario from a deserialized YAML dict."""
        zones = [Zone(**z) for z in data.get("zones", [])]
        spawners = [SpawnerRule(**s) for s in data.get("detections", {}).get("spawners", [])]
        detections = {"spawners": spawners}
        return cls(
            name=data["name"],
            description=data["description"],
            sea_polygon=data["sea_polygon"],
            zones=zones,
            navigation=data["navigation"],
            agent=data["agent"],
            detections=detections,
            priority_rules=data.get("priority_rules"),
            max_duration=data.get("max_duration", 300.0),
        )

    def _to_dict(self) -> dict:
        """Serialize this Scenario to a plain dict for YAML dumping."""
        return {
            "name": self.name,
            "description": self.description,
            "sea_polygon": self.sea_polygon,
            "zones": [asdict(z) for z in self.zones],
            "navigation": self.navigation,
            "agent": self.agent,
            "detections": {
                "spawners": [asdict(s) for s in self.detections["spawners"]],
            },
            "priority_rules": self.priority_rules,
            "max_duration": self.max_duration,
        }