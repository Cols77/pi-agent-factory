"""Tests for the matplotlib post-mission report generator."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from drone.interfaces import Pose, Detection, Directive
from sim.recorder import Recorder
from sim.plotter import generate_report

pytestmark = pytest.mark.unit


class TestPlotter:
    def test_generate_report_creates_file(self):
        """generate_report should produce a valid PNG file > 1 KB."""
        recorder = Recorder(record_interval=0.0)
        recorder.record(
            0.0,
            Pose(0, 0, 5, 0),
            [],
            Directive(kind="continue"),
            {"current_idx": 0, "total": 5, "completed": 0},
        )
        recorder.record(
            1.0,
            Pose(5, 0, 5, 0),
            [],
            None,
            {"current_idx": 1, "total": 5, "completed": 1},
        )
        recorder.record(
            2.0,
            Pose(10, 0, 5, 0),
            [Detection("shark", 0.9, 45, 10, Pose(15, 5, 0, 0))],
            Directive(kind="land"),
            {"current_idx": 2, "total": 5, "completed": 2},
        )

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            path = f.name
        generate_report(recorder, path, mission_name="test-report")
        file_size = Path(path).stat().st_size
        assert file_size > 1000  # should be a real PNG
        Path(path).unlink(missing_ok=True)

    def test_generate_report_with_empty_trace_does_not_error(self):
        """generate_report with no frames should not raise."""
        recorder = Recorder(record_interval=0.0)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            path = f.name
        # Should not raise even with empty trace
        generate_report(recorder, path, mission_name="empty")
        Path(path).unlink(missing_ok=True)

    def test_generate_report_with_sea_polygon_and_zones(self):
        """generate_report should accept optional sea_polygon and zones."""
        recorder = Recorder(record_interval=0.0)
        recorder.record(
            0.0,
            Pose(0, 0, 5, 0),
            [],
            Directive(kind="continue"),
            {"current_idx": 0, "total": 3, "completed": 0},
        )
        recorder.record(
            1.0,
            Pose(5, 0, 5, 0),
            [Detection("swimmer", 0.8, 10, 5, Pose(8, 2, 0, 0))],
            Directive(kind="continue"),
            {"current_idx": 1, "total": 3, "completed": 1},
        )

        sea_polygon = [[0, 0], [100, 0], [100, 100], [0, 100]]
        zones = [
            {
                "polygon": [[10, 10], [40, 10], [40, 40], [10, 40]],
                "label": "swim_area",
            }
        ]

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            path = f.name
        generate_report(
            recorder,
            path,
            mission_name="zones-test",
            sea_polygon=sea_polygon,
            zones=zones,
        )
        file_size = Path(path).stat().st_size
        assert file_size > 1000
        Path(path).unlink(missing_ok=True)