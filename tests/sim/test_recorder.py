"""Tests for Recorder — mission trace recording, save, and load."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from drone.interfaces import Pose, Detection, Directive

pytestmark = pytest.mark.unit


class TestRecorder:
    """Recorder should capture Frame objects and persist them to YAML."""

    def test_record_and_trace(self):
        from sim.recorder import Recorder

        recorder = Recorder(record_interval=0.0)  # record every call
        recorder.record(
            mission_clock=0.0,
            drone_pose=Pose(0, 0, 5, 0),
            detections=[
                Detection(
                    label="swimmer",
                    confidence=0.9,
                    bearing=0,
                    range=10,
                    position=Pose(10, 0, 0, 0),
                )
            ],
            active_directive=Directive(kind="continue"),
            waypoint_status={"current_idx": 0, "total": 10, "completed": 0},
        )
        recorder.record(
            mission_clock=1.0,
            drone_pose=Pose(5, 0, 5, 0),
            detections=[],
            active_directive=None,
            waypoint_status={"current_idx": 2, "total": 10, "completed": 2},
        )
        trace = recorder.trace()
        assert len(trace) == 2
        assert trace[0].mission_clock == 0.0
        assert trace[1].mission_clock == 1.0
        assert len(trace[0].detections) == 1
        assert trace[0].detections[0].label == "swimmer"

    def test_save_and_load(self):
        from sim.recorder import Recorder

        recorder = Recorder(record_interval=0.0)
        recorder.record(
            mission_clock=0.0,
            drone_pose=Pose(5, 5, 5, 0),
            detections=[],
            active_directive=Directive(kind="continue"),
            waypoint_status={"current_idx": 0, "total": 5, "completed": 0},
        )
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False, mode="w") as f:
            path = f.name
            recorder.save(f.name)
        loaded = Recorder.load(path)
        assert len(loaded.trace()) == 1
        assert loaded.trace()[0].drone_pose.x == 5.0
        Path(path).unlink()