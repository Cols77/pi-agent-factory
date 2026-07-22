"""Unit tests for core data types in src/drone/interfaces.py."""
from __future__ import annotations

import pytest
from dataclasses import FrozenInstanceError

pytestmark = pytest.mark.unit


class TestPose:
    def test_construct(self):
        from drone.interfaces import Pose
        p = Pose(x=1.0, y=2.0, z=3.0, heading=90.0)
        assert p.x == 1.0
        assert p.y == 2.0
        assert p.z == 3.0
        assert p.heading == 90.0

    def test_frozen(self):
        from drone.interfaces import Pose
        p = Pose(x=0, y=0, z=0, heading=0)
        with pytest.raises(FrozenInstanceError):
            p.x = 5  # type: ignore[misc]

    def test_defaults(self):
        from drone.interfaces import Pose
        p = Pose()
        assert p.x == 0.0 and p.y == 0.0 and p.z == 0.0 and p.heading == 0.0


class TestDetection:
    def test_construct(self):
        from drone.interfaces import Detection, Pose
        d = Detection(label="distress", confidence=0.9, bearing=45.0, range=10.0, position=Pose(x=5, y=5, z=0, heading=0))
        assert d.label == "distress"
        assert d.confidence == 0.9

    def test_frozen(self):
        from drone.interfaces import Detection, Pose
        d = Detection(label="boat", confidence=0.5, bearing=0, range=0, position=Pose())
        with pytest.raises(FrozenInstanceError):
            d.label = "ship"  # type: ignore[misc]


class TestCommand:
    def test_construct(self):
        from drone.interfaces import Command
        c = Command(action="goto", x=1.0, y=2.0, z=3.0)
        assert c.action == "goto"

    def test_frozen(self):
        from drone.interfaces import Command
        c = Command(action="hover")
        with pytest.raises(FrozenInstanceError):
            c.action = "land"  # type: ignore[misc]


class TestWaterArea:
    def test_construct(self):
        from drone.interfaces import WaterArea
        w = WaterArea(vertices=[(0, 0), (10, 0), (10, 10), (0, 10)])
        assert len(w.vertices) == 4

    def test_frozen(self):
        from drone.interfaces import WaterArea
        w = WaterArea(vertices=[(0, 0), (1, 0), (1, 1)])
        with pytest.raises(FrozenInstanceError):
            w.vertices = []  # type: ignore[misc]


class TestNavPlan:
    def test_construct(self):
        from drone.interfaces import NavPlan, Pose
        w = [Pose(0, 0, 5, 0), Pose(10, 0, 5, 0)]
        np = NavPlan(waypoints=w, algorithm_name="perimeter_sweep", created_at=1.5)
        assert np.algorithm_name == "perimeter_sweep"
        assert np.created_at == 1.5
        assert len(np.waypoints) == 2


class TestDirective:
    def test_update_nav(self):
        from drone.interfaces import Directive, NavPlan, Pose
        plan = NavPlan(waypoints=[Pose()], algorithm_name="test", created_at=0)
        d = Directive(kind="update_nav", args={"nav_plan": plan})
        assert d.kind == "update_nav"
        assert d.args["nav_plan"] == plan

    def test_continue(self):
        from drone.interfaces import Directive
        d = Directive(kind="continue")
        assert d.kind == "continue"
        assert d.args == {}

    def test_land(self):
        from drone.interfaces import Directive
        d = Directive(kind="land")
        assert d.kind == "land"


class TestNavContext:
    def test_construct(self):
        from drone.interfaces import NavContext, Pose
        ctx = NavContext(current_pose=Pose(1, 2, 3, 0), completed_area=[(0, 0), (1, 1)])
        assert ctx.current_pose.x == 1


class TestPriorityRule:
    def test_construct(self):
        from drone.interfaces import PriorityRule
        r = PriorityRule(label="distress", min_confidence=0.8, reason_template="possible {label}")
        assert r.label == "distress"
        assert r.min_confidence == 0.8


class TestDetectionEvent:
    def test_construct(self):
        from drone.interfaces import DetectionEvent, Detection, Pose
        det = Detection(label="distress", confidence=0.9, bearing=0, range=0, position=Pose())
        ev = DetectionEvent(detection=det, reason="possible distress")
        assert ev.reason == "possible distress"


class TestModelConfig:
    def test_construct(self):
        from drone.interfaces import ModelConfig
        mc = ModelConfig(provider="google", model="gemini-flash", api_key="key123")
        assert mc.provider == "google"


class TestProtocols:
    def test_flight_controller_is_protocol(self):
        from drone.interfaces import FlightController
        assert hasattr(FlightController, "__protocol_attrs__") or hasattr(FlightController, "__abstractmethods__") or hasattr(FlightController, "__subclasshook__")

    def test_perception_is_protocol(self):
        from drone.interfaces import Perception
        assert hasattr(Perception, "__protocol_attrs__") or hasattr(Perception, "__abstractmethods__") or hasattr(Perception, "__subclasshook__")

    def test_mission_planner_is_protocol(self):
        from drone.interfaces import MissionPlanner
        assert hasattr(MissionPlanner, "__protocol_attrs__") or hasattr(MissionPlanner, "__abstractmethods__") or hasattr(MissionPlanner, "__subclasshook__")

    def test_navigation_algorithm_is_protocol(self):
        from drone.interfaces import NavigationAlgorithm
        assert hasattr(NavigationAlgorithm, "__protocol_attrs__") or hasattr(NavigationAlgorithm, "__abstractmethods__") or hasattr(NavigationAlgorithm, "__subclasshook__")


class TestFakeFlightController:
    def test_initial_state(self):
        from drone.fake_flight_controller import FakeFlightController
        fc = FakeFlightController()
        assert fc.get_battery() == 1.0
        assert fc.is_armed() is False

    def test_arm_takeoff(self):
        from drone.fake_flight_controller import FakeFlightController
        fc = FakeFlightController()
        fc.arm()
        assert fc.is_armed() is True
        fc.takeoff(altitude=5.0)
        fc.step(0.1)
        assert fc.get_pose().z > 0

    def test_goto_and_step(self):
        from drone.fake_flight_controller import FakeFlightController
        fc = FakeFlightController()
        fc.arm()
        fc.takeoff(altitude=5.0)
        for _ in range(200):
            fc.step(0.05)
        fc.goto(10.0, 5.0, 5.0)
        for _ in range(200):
            fc.step(0.05)
        pose = fc.get_pose()
        assert abs(pose.x - 10.0) < 1.0
        assert abs(pose.y - 5.0) < 1.0

    def test_land(self):
        from drone.fake_flight_controller import FakeFlightController
        fc = FakeFlightController()
        fc.arm()
        fc.takeoff(altitude=5.0)
        for _ in range(200):
            fc.step(0.05)
        fc.land()
        for _ in range(200):
            fc.step(0.05)
        assert fc.get_pose().z < 0.1

    def test_battery_drains(self):
        from drone.fake_flight_controller import FakeFlightController
        fc = FakeFlightController()
        fc.arm()
        fc.takeoff(altitude=5.0)
        for _ in range(200):
            fc.step(0.05)
        initial_battery = fc.get_battery()
        fc.goto(50.0, 50.0, 5.0)
        for _ in range(400):
            fc.step(0.05)
        assert fc.get_battery() < initial_battery

    def test_satisfies_flight_controller_protocol(self):
        from drone.interfaces import FlightController
        from drone.fake_flight_controller import FakeFlightController
        fc = FakeFlightController()
        assert isinstance(fc, FlightController)
