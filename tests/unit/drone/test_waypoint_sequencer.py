"""Unit tests for WaypointSequencer."""

from __future__ import annotations

import pytest

from drone.interfaces import NavPlan, Pose
from drone.fake_flight_controller import FakeFlightController
from drone.navigation.waypoint_sequencer import WaypointSequencer

pytestmark = pytest.mark.unit


class TestWaypointSequencerSetPlan:
    def test_set_plan_resets(self):
        fc = FakeFlightController()
        seq = WaypointSequencer(fc)
        plan = NavPlan(
            waypoints=[Pose(5, 0, 5, 0), Pose(10, 0, 5, 0)],
            algorithm_name="test",
            created_at=0,
        )
        seq.set_plan(plan)
        s = seq.status()
        assert s["current_idx"] == 0
        assert s["total"] == 2
        assert s["plan_name"] == "test"

    def test_replace_plan_resets(self):
        fc = FakeFlightController()
        seq = WaypointSequencer(fc)
        plan1 = NavPlan(
            waypoints=[Pose(5, 0, 5, 0)], algorithm_name="a", created_at=0
        )
        seq.set_plan(plan1)
        # Step a few times to advance
        fc.arm()
        fc.takeoff(5.0)
        for _ in range(200):
            fc.step(0.05)
        for _ in range(200):
            seq.step(0.05)
        plan2 = NavPlan(
            waypoints=[Pose(20, 0, 5, 0)], algorithm_name="b", created_at=1.0
        )
        seq.set_plan(plan2)
        assert seq.status()["current_idx"] == 0
        assert seq.status()["plan_name"] == "b"


class TestWaypointSequencerStep:
    def test_step_advances_toward_waypoint(self):
        fc = FakeFlightController()
        seq = WaypointSequencer(fc)
        plan = NavPlan(
            waypoints=[Pose(3, 0, 5, 0)], algorithm_name="test", created_at=0
        )
        seq.set_plan(plan)
        fc.arm()
        fc.takeoff(5.0)
        for _ in range(200):
            fc.step(0.05)
        # Now step sequencer toward waypoint
        for _ in range(200):
            seq.step(0.05)
        pose = fc.get_pose()
        assert abs(pose.x - 3.0) < 1.0

    def test_step_returns_true_when_reached(self):
        fc = FakeFlightController()
        seq = WaypointSequencer(fc)
        plan = NavPlan(
            waypoints=[Pose(0, 0, 5, 0)], algorithm_name="test", created_at=0
        )
        seq.set_plan(plan)
        fc.arm()
        fc.takeoff(5.0)
        for _ in range(200):
            fc.step(0.05)
        # Already near first waypoint (x=0, y=0, z=5)
        reached = False
        for _ in range(100):
            if seq.step(0.05):
                reached = True
                break
        assert reached

    def test_step_returns_false_when_not_reached(self):
        fc = FakeFlightController()
        seq = WaypointSequencer(fc)
        plan = NavPlan(
            waypoints=[Pose(100, 100, 5, 0)], algorithm_name="test", created_at=0
        )
        seq.set_plan(plan)
        fc.arm()
        fc.takeoff(5.0)
        for _ in range(200):
            fc.step(0.05)
        result = seq.step(0.05)
        assert result is False


class TestWaypointSequencerComplete:
    def test_not_complete_initially(self):
        fc = FakeFlightController()
        seq = WaypointSequencer(fc)
        plan = NavPlan(
            waypoints=[Pose(5, 0, 5, 0)], algorithm_name="test", created_at=0
        )
        seq.set_plan(plan)
        assert seq.is_complete() is False

    def test_complete_after_all_waypoints(self):
        fc = FakeFlightController()
        seq = WaypointSequencer(fc)
        plan = NavPlan(
            waypoints=[Pose(0, 0, 5, 0)], algorithm_name="test", created_at=0
        )
        seq.set_plan(plan)
        fc.arm()
        fc.takeoff(5.0)
        for _ in range(200):
            fc.step(0.05)
        # Reach the waypoint
        for _ in range(200):
            seq.step(0.05)
        assert seq.is_complete() is True


class TestWaypointSequencerStatus:
    def test_status_format(self):
        fc = FakeFlightController()
        seq = WaypointSequencer(fc)
        plan = NavPlan(
            waypoints=[Pose(1, 0, 5, 0), Pose(2, 0, 5, 0), Pose(3, 0, 5, 0)],
            algorithm_name="sweep",
            created_at=0,
        )
        seq.set_plan(plan)
        s = seq.status()
        assert s == {
            "current_idx": 0,
            "total": 3,
            "completed": 0,
            "plan_name": "sweep",
        }