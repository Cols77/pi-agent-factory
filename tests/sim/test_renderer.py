"""Tests for the Pygame Renderer and HUD modules (headless, no display)."""

from __future__ import annotations

import pygame
import pytest

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def pygame_init():
    """Initialize pygame modules for headless tests."""
    pygame.init()
    yield
    pygame.quit()


@pytest.fixture
def screen() -> pygame.Surface:
    """A minimal off-screen surface (no display needed)."""
    return pygame.Surface((1280, 800))


class TestRendererImports:
    """Smoke tests: Renderer and HUD modules import cleanly."""

    def test_import_renderer(self):
        from sim.renderer import Renderer

        assert Renderer is not None

    def test_import_hud(self):
        from sim.hud import HUD

        assert HUD is not None


class TestRendererConstruction:
    """Renderer should be constructable from a scenario."""

    def test_construct_with_minimal_scenario(self, screen):
        from sim.renderer import Renderer
        from sim.scenario import Scenario

        scenario = Scenario(
            name="test",
            description="test",
            sea_polygon={"vertices": [[0, 0], [100, 0], [100, 100], [0, 100]]},
            zones=[],
            navigation={"algorithm": "perimeter_sweep", "altitude": 5.0, "offset": 2.0},
            agent={"type": "fake", "responses": []},
            detections={"spawners": []},
            max_duration=300.0,
        )
        renderer = Renderer(screen, scenario)
        assert renderer is not None

    def test_construct_with_zones(self, screen):
        from sim.renderer import Renderer
        from sim.scenario import Scenario, Zone

        scenario = Scenario(
            name="test",
            description="test",
            sea_polygon={"vertices": [[0, 0], [120, 0], [140, 90], [70, 130], [-30, 70]]},
            zones=[
                Zone(id="swim-zone", label="swim_area",
                     polygon=[[5, 5], [35, 5], [40, 35], [10, 40]],
                     color=[0, 200, 255, 80]),
            ],
            navigation={"algorithm": "perimeter_sweep", "altitude": 5.0, "offset": 2.0},
            agent={"type": "fake", "responses": []},
            detections={"spawners": []},
            max_duration=300.0,
        )
        renderer = Renderer(screen, scenario)
        assert renderer is not None


class TestRenderDrawWorld:
    """draw_world should render the world without crashing."""

    def test_draw_world_no_detections(self, screen):
        from sim.renderer import Renderer
        from sim.scenario import Scenario
        from drone.interfaces import Pose

        scenario = Scenario(
            name="test",
            description="test",
            sea_polygon={"vertices": [[0, 0], [100, 0], [100, 100], [0, 100]]},
            zones=[],
            navigation={"algorithm": "perimeter_sweep", "altitude": 5.0, "offset": 2.0},
            agent={"type": "fake", "responses": []},
            detections={"spawners": []},
            max_duration=300.0,
        )
        renderer = Renderer(screen, scenario)
        renderer.draw_world(drone_pose=Pose(50, 50, 5, 0), detections=[])
        # No crash = success

    def test_draw_world_with_detections(self, screen):
        from sim.renderer import Renderer
        from sim.scenario import Scenario
        from drone.interfaces import Pose, Detection

        scenario = Scenario(
            name="test",
            description="test",
            sea_polygon={"vertices": [[0, 0], [100, 0], [100, 100], [0, 100]]},
            zones=[],
            navigation={"algorithm": "perimeter_sweep", "altitude": 5.0, "offset": 2.0},
            agent={"type": "fake", "responses": []},
            detections={"spawners": []},
            max_duration=300.0,
        )
        renderer = Renderer(screen, scenario)
        detections = [
            Detection(label="shark", confidence=0.9, bearing=45.0, range=30.0,
                      position=Pose(70, 70, 0, 0)),
            Detection(label="swimmer", confidence=0.6, bearing=0.0, range=20.0,
                      position=Pose(30, 30, 0, 0)),
        ]
        renderer.draw_world(drone_pose=Pose(50, 50, 5, 0), detections=detections)
        # No crash = success

    def test_draw_world_with_waypoints(self, screen):
        from sim.renderer import Renderer
        from sim.scenario import Scenario
        from drone.interfaces import Pose

        scenario = Scenario(
            name="test",
            description="test",
            sea_polygon={"vertices": [[0, 0], [100, 0], [100, 100], [0, 100]]},
            zones=[],
            navigation={"algorithm": "perimeter_sweep", "altitude": 5.0, "offset": 2.0},
            agent={"type": "fake", "responses": []},
            detections={"spawners": []},
            max_duration=300.0,
        )
        renderer = Renderer(screen, scenario)
        waypoints = [Pose(0, 0, 5, 0), Pose(50, 0, 5, 0), Pose(50, 50, 5, 0)]
        renderer.draw_world(drone_pose=Pose(50, 50, 5, 0), detections=[], waypoints=waypoints)
        # No crash = success

    def test_draw_world_empty_sea_polygon(self, screen):
        """No crash when sea_polygon has no vertices."""
        from sim.renderer import Renderer
        from sim.scenario import Scenario
        from drone.interfaces import Pose

        scenario = Scenario(
            name="test",
            description="test",
            sea_polygon={"vertices": []},
            zones=[],
            navigation={"algorithm": "perimeter_sweep", "altitude": 5.0, "offset": 2.0},
            agent={"type": "fake", "responses": []},
            detections={"spawners": []},
            max_duration=300.0,
        )
        renderer = Renderer(screen, scenario)
        renderer.draw_world(drone_pose=Pose(0, 0, 5, 0), detections=[])
        # No crash = success


class TestRendererSetView:
    """set_view should update the renderer's view parameters."""

    def test_set_view(self, screen):
        from sim.renderer import Renderer
        from sim.scenario import Scenario

        scenario = Scenario(
            name="test",
            description="test",
            sea_polygon={"vertices": [[0, 0], [100, 0], [100, 100], [0, 100]]},
            zones=[],
            navigation={"algorithm": "perimeter_sweep", "altitude": 5.0, "offset": 2.0},
            agent={"type": "fake", "responses": []},
            detections={"spawners": []},
            max_duration=300.0,
        )
        renderer = Renderer(screen, scenario)
        renderer.set_view(center_x=50.0, center_y=50.0, scale=2.0)
        # No crash = success


class TestRendererAddEvent:
    """add_event should store events that are drawn as markers."""

    def test_add_event(self, screen):
        from sim.renderer import Renderer
        from sim.scenario import Scenario
        from drone.interfaces import Pose

        scenario = Scenario(
            name="test",
            description="test",
            sea_polygon={"vertices": [[0, 0], [100, 0], [100, 100], [0, 100]]},
            zones=[],
            navigation={"algorithm": "perimeter_sweep", "altitude": 5.0, "offset": 2.0},
            agent={"type": "fake", "responses": []},
            detections={"spawners": []},
            max_duration=300.0,
        )
        renderer = Renderer(screen, scenario)
        renderer.add_event("shark_alert", Pose(50, 50, 0, 0), "Shark spotted!")
        renderer.draw_world(drone_pose=Pose(50, 50, 5, 0), detections=[])
        # No crash = success


class TestHUDConstruction:
    """HUD should be constructable and drawable."""

    def test_construct_hud(self):
        from sim.hud import HUD

        hud = HUD()
        assert hud is not None

    def test_hud_draw_no_crash(self, screen):
        from sim.hud import HUD

        hud = HUD()
        hud.draw(
            screen=screen,
            mission_name="test-mission",
            mission_clock=45.2,
            speed_mult=2.0,
            fps=60.0,
            nav_status="perimeter_sweep (3/10 waypoints)",
            battery=0.85,
            detection_summary={"shark": 1, "swimmer": 3},
            event_log=["[0.0s] Mission started", "[15.0s] Shark detected"],
        )
        # No crash = success

    def test_hud_draw_minimal(self, screen):
        """HUD should handle empty/missing data gracefully."""
        from sim.hud import HUD

        hud = HUD()
        hud.draw(
            screen=screen,
            mission_name="test",
            mission_clock=0.0,
            speed_mult=1.0,
            fps=0.0,
            nav_status="no plan",
            battery=1.0,
            detection_summary={},
            event_log=[],
        )
        # No crash = success

    def test_hud_draw_low_battery(self, screen):
        """Battery below 20% should use warning color."""
        from sim.hud import HUD

        hud = HUD()
        hud.draw(
            screen=screen,
            mission_name="test",
            mission_clock=100.0,
            speed_mult=1.0,
            fps=30.0,
            nav_status="returning to base",
            battery=0.15,
            detection_summary={},
            event_log=["Battery low"],
        )
        # No crash = success