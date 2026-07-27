"""Sim-level tests for FakeFlightController — verifies flight controller integration
without pybullet, using the deterministic fake."""
from __future__ import annotations

import pytest

from drone.interfaces import FlightController, Pose
from drone.fake_flight_controller import FakeFlightController

pytestmark = pytest.mark.sim


class TestFakeFlightControllerSim:
    """Sim-level: full arm→takeoff→goto→land cycle."""

    def test_full_flight_cycle(self):
        fc = FakeFlightController()
        assert isinstance(fc, FlightController)

        # Arm & takeoff
        fc.arm()
        assert fc.is_armed() is True
        fc.takeoff(altitude=10.0)
        for _ in range(300):
            fc.step(0.05)
        assert fc.get_pose().z > 8.0, "Should reach takeoff altitude"

        # Goto waypoint
        fc.goto(20.0, 20.0, 10.0)
        for _ in range(400):
            fc.step(0.05)
        pose = fc.get_pose()
        assert abs(pose.x - 20.0) < 1.5, f"x={pose.x}, expected ~20"
        assert abs(pose.y - 20.0) < 1.5, f"y={pose.y}, expected ~20"

        # Land
        fc.land()
        for _ in range(300):
            fc.step(0.05)
        assert fc.get_pose().z < 0.5, "Should land"

        # Battery should have drained
        assert fc.get_battery() < 1.0, "Battery should drain during flight"

    def test_goto_multiple_waypoints(self):
        fc = FakeFlightController()
        fc.arm()
        fc.takeoff(altitude=5.0)
        for _ in range(200):
            fc.step(0.05)

        waypoints = [(5, 5, 5), (10, 0, 5), (5, -5, 5)]
        for wx, wy, wz in waypoints:
            fc.goto(float(wx), float(wy), float(wz))
            for _ in range(200):
                fc.step(0.05)
            pose = fc.get_pose()
            assert abs(pose.x - wx) < 2.0, f"x={pose.x}, expected ~{wx}"
            assert abs(pose.y - wy) < 2.0, f"y={pose.y}, expected ~{wy}"

    def test_takeoff_without_arm_raises(self):
        fc = FakeFlightController()
        with pytest.raises(RuntimeError, match="not armed"):
            fc.takeoff(altitude=5.0)

    def test_step_without_arm_is_noop(self):
        fc = FakeFlightController()
        fc.step(0.1)
        assert fc.get_pose() == Pose(x=0, y=0, z=0, heading=0)
