from __future__ import annotations

import pytest
import tempfile
from pathlib import Path

from sim.bug_capture import BugSnapshot

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