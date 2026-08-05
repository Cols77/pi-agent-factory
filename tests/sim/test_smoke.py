"""Smoke tests for the sim testbench package.

Verifies that all modules import cleanly and all scenario YAML files load.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.sim


class TestSimSmoke:
    """Smoke tests that verify the full sim testbench can initialize."""

    def test_import_all_modules(self) -> None:
        """All sim modules import without error."""
        from sim import scenario  # noqa: F401
        from sim import detection_spawner  # noqa: F401
        from sim import recorder  # noqa: F401
        from sim import text_input  # noqa: F401
        from sim import renderer  # noqa: F401
        from sim import hud  # noqa: F401
        from sim import testbench  # noqa: F401
        from sim import injector  # noqa: F401
        from sim import bug_capture  # noqa: F401
        from sim import plotter  # noqa: F401
        from sim import bug_to_task  # noqa: F401

    def test_load_all_scenarios(self) -> None:
        """All scenario YAML files load correctly."""
        from sim.scenario import Scenario
        from pathlib import Path

        scenario_dir = Path("scenarios")
        yaml_files = list(scenario_dir.glob("*.yaml"))
        assert len(yaml_files) >= 5, (
            f"Expected at least 5 scenario YAML files, found {len(yaml_files)}"
        )
        for path in sorted(yaml_files):
            scenario = Scenario.load(str(path))
            assert scenario.name, f"Scenario missing name: {path.name}"
            assert scenario.sea_polygon, f"Scenario missing sea_polygon: {path.name}"
            assert scenario.sea_polygon.get("vertices"), (
                f"Scenario missing sea_polygon vertices: {path.name}"
            )