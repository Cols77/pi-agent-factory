from __future__ import annotations

import pytest
import tempfile
from pathlib import Path

from sim.bug_capture import BugSnapshot, capture_bug, BUGS_DIR

pytestmark = pytest.mark.unit


class TestBugSnapshot:
    def test_snapshot_creation(self):
        snapshot = BugSnapshot(
            name="test-bug",
            captured_at=45.2,
            user_description="The drone didn't react",
            requirements=[],
            scenario={"sea_polygon": {"vertices": [[0, 0], [10, 0]]}, "zones": []},
            drone_pose={"x": 5, "y": 5, "z": 5},
            mission_state={"mission_clock": 45.2, "waypoints_completed": 12},
        )
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False, mode="w") as f:
            path = f.name
            snapshot.save(path)
        loaded = BugSnapshot.load(path)
        assert loaded.name == "test-bug"
        assert loaded.captured_at == 45.2
        assert loaded.user_description == "The drone didn't react"
        Path(path).unlink()


class TestCaptureBug:
    def test_capture_bug_creates_yaml_snapshot(self):
        """capture_bug() writes a YAML file to scenarios/bugs/ and returns its path."""
        from drone.interfaces import Pose
        from sim.scenario import Zone, SpawnerRule

        class MockState:
            mission_clock = 45.2
            waypoints_completed = 12
            waypoints_total = 20
            battery = 0.8

        class MockLoop:
            _state = MockState()

        class MockFC:
            def get_pose(self):
                return Pose(x=5.0, y=10.0, z=3.0, heading=90.0)

        scenario_mock = type(
            "ScenarioMock",
            (),
            {
                "sea_polygon": {"vertices": [[0, 0], [100, 0], [100, 100], [0, 100]]},
                "zones": [
                    Zone(id="swim-zone", label="swim_area",
                         polygon=[[5, 5], [20, 5], [20, 20], [5, 20]],
                         color=[0, 200, 255, 80]),
                ],
                "detections": {
                    "spawners": [
                        SpawnerRule(label="swimmer", pool="inside_zone(swim-zone)",
                                    count=3, start_time=0.0, interval=5.0, speed=0.5),
                    ]
                },
            },
        )()

        class MockTestbench:
            _loop = MockLoop()
            _scenario = scenario_mock
            _event_log: list[str] = []

            @property
            def fc(self):
                return MockFC()

        tb = MockTestbench()
        path = capture_bug(tb, "drone not reacting to shark")

        assert Path(path).exists()
        assert "drone-not-reacting" in path
        assert path.startswith(str(BUGS_DIR))

        # Clean up
        Path(path).unlink()

    def test_capture_bug_handles_no_state(self):
        """capture_bug() handles testbench with no loop state gracefully."""
        from drone.interfaces import Pose

        class MockLoop:
            _state = None

        class MockFC:
            def get_pose(self):
                return Pose(x=0.0, y=0.0, z=0.0, heading=0.0)

        scenario_mock = type(
            "ScenarioMock",
            (),
            {
                "sea_polygon": {"vertices": [[0, 0], [10, 0], [10, 10], [0, 10]]},
                "zones": [],
                "detections": {"spawners": []},
            },
        )()

        class MockTestbench:
            _loop = MockLoop()
            _scenario = scenario_mock
            _event_log: list[str] = []

            @property
            def fc(self):
                return MockFC()

        tb = MockTestbench()
        path = capture_bug(tb, "no loop state")

        assert Path(path).exists()

        # Clean up
        Path(path).unlink()