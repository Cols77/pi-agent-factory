"""Tests for the matplotlib post-mission report generator."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from drone.interfaces import Pose, Detection, Directive
from sim.recorder import Recorder
from sim.plotter import generate_report

pytestmark = pytest.mark.unit


class TestPlotterLint:
    """Lint-quality checks on the plotter module source."""

    PLOTTER_PATH = Path("src/sim/plotter.py")

    def test_no_unused_color_variable_in_panel2(self):
        """The `color = label_colors.get(label, "gray")` in panel 2 should be
        removed because it is assigned but never used (ruff F841)."""
        source = self.PLOTTER_PATH.read_text()
        # The variable `color` is assigned from label_colors.get but never
        # passed to the scatter call; it should be removed entirely.
        assert 'color = label_colors.get(label, "gray")' not in source, (
            "Panel 2 assigns `color = label_colors.get(label, 'gray')` "
            "but the variable is never passed to ax2.scatter() — remove it."
        )

    def test_imports_before_matplotlib_use(self):
        """All imports must appear before the `matplotlib.use("Agg")` call
        (ruff E402)."""
        source = self.PLOTTER_PATH.read_text()
        lines = source.splitlines()

        # Find the line with matplotlib.use("Agg")
        use_line_idx = None
        for i, line in enumerate(lines):
            if 'matplotlib.use("Agg")' in line:
                use_line_idx = i
                break

        assert use_line_idx is not None, "Could not find matplotlib.use('Agg')"

        # Find any `import` or `from ... import` after the use() line
        # without a `# noqa: E402` annotation.
        for i in range(use_line_idx + 1, len(lines)):
            stripped = lines[i].strip()
            if stripped.startswith(("import ", "from ")):
                # Allow imports with `# noqa: E402` (required because
                # matplotlib.use("Agg") must be called before importing pyplot).
                if "# noqa: E402" not in stripped:
                    pytest.fail(
                        f"Import at line {i + 1} is after matplotlib.use(\"Agg\") "
                        f"on line {use_line_idx + 1}: {stripped}\n"
                        "All imports must be at the top of the file. Add "
                        "# noqa: E402 if this is intentional (matplotlib "
                        "backend must be set before importing pyplot)."
                    )


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