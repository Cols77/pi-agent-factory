"""Tests for Scenario dataclass and YAML I/O."""

from __future__ import annotations

import pytest
import tempfile
from pathlib import Path

pytestmark = pytest.mark.unit


class TestScenarioRoundTrip:
    def test_minimal_scenario_round_trip(self):
        from sim.scenario import Scenario

        scenario = Scenario(
            name="test-scenario",
            description="A test scenario",
            sea_polygon={"vertices": [[0, 0], [100, 0], [100, 100], [0, 100]]},
            zones=[],
            navigation={"algorithm": "perimeter_sweep", "altitude": 5.0, "offset": 2.0},
            agent={"type": "fake", "responses": []},
            detections={"spawners": []},
            max_duration=300.0,
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            path = f.name
            scenario.save(path)
        loaded = Scenario.load(path)
        assert loaded.name == scenario.name
        assert loaded.sea_polygon == scenario.sea_polygon
        assert loaded.navigation == scenario.navigation
        Path(path).unlink()

    def test_scenario_with_zones_and_spawners(self):
        from sim.scenario import Scenario, Zone, SpawnerRule

        scenario = Scenario(
            name="full-scenario",
            description="Scenario with zones and spawners",
            sea_polygon={"vertices": [[0, 0], [50, 0], [50, 50], [0, 50]]},
            zones=[
                Zone(
                    id="swim-zone",
                    label="swim_area",
                    polygon=[[5, 5], [20, 5], [20, 20], [5, 20]],
                    color=[0, 200, 255, 80],
                ),
            ],
            navigation={"algorithm": "perimeter_sweep", "altitude": 5.0, "offset": 2.0},
            agent={"type": "fake", "responses": []},
            detections={
                "spawners": [
                    SpawnerRule(
                        label="swimmer",
                        pool="inside_zone(swim-zone)",
                        count=3,
                        start_time=0.0,
                        interval=5.0,
                        speed=0.5,
                    ),
                ]
            },
            priority_rules=[{"label": "shark", "min_confidence": 0.7, "reason": "shark detected"}],
            max_duration=300.0,
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            path = f.name
            scenario.save(path)
        loaded = Scenario.load(path)
        assert len(loaded.zones) == 1
        assert loaded.zones[0].id == "swim-zone"
        assert len(loaded.detections["spawners"]) == 1
        assert loaded.detections["spawners"][0].label == "swimmer"
        Path(path).unlink()

    def test_load_nonexistent_raises(self):
        from sim.scenario import Scenario

        with pytest.raises(FileNotFoundError):
            Scenario.load("/nonexistent/path.yaml")
