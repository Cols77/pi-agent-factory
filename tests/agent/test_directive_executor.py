"""Tests for DirectiveExecutor."""
from __future__ import annotations

from drone.interfaces import Directive, NavPlan, Detection, Pose
from drone.fake_flight_controller import FakeFlightController
from drone.mission.state import MissionState
from drone.navigation.waypoint_sequencer import WaypointSequencer
from drone.mission.directive_executor import DirectiveExecutor


def _make_executor():
    fc = FakeFlightController()
    seq = WaypointSequencer(fc)
    state = MissionState(mission_objectives="test")
    return DirectiveExecutor(fc=fc, sequencer=seq, state=state), fc, seq, state


class TestDirectiveExecutorContinue:
    def test_continue_is_noop(self):
        ex, fc, seq, state = _make_executor()
        result = ex.execute(Directive(kind="continue"))
        assert "continue" in result.lower() or "no-op" in result.lower()


class TestDirectiveExecutorUpdateNav:
    def test_update_nav_sets_plan(self):
        ex, fc, seq, state = _make_executor()
        plan = NavPlan(waypoints=[Pose(5, 5, 5, 0), Pose(10, 10, 5, 0)], algorithm_name="sweep", created_at=0)
        result = ex.execute(Directive(kind="update_nav", args={"nav_plan": plan}))
        assert state.nav_plan == plan
        assert "update" in result.lower() or "nav" in result.lower()


class TestDirectiveExecutorLand:
    def test_land_calls_fc_land(self):
        ex, fc, seq, state = _make_executor()
        fc.arm()
        fc.takeoff(5.0)
        for _ in range(200):
            fc.step(0.05)
        result = ex.execute(Directive(kind="land"))
        assert "land" in result.lower()


class TestDirectiveExecutorReturnBase:
    def test_return_base_creates_home_plan(self):
        ex, fc, seq, state = _make_executor()
        result = ex.execute(Directive(kind="return_base"))
        assert state.nav_plan is not None
        # Plan should head toward origin
        assert any(abs(wp.x) < 1 and abs(wp.y) < 1 for wp in state.nav_plan.waypoints)
        assert "return" in result.lower() or "base" in result.lower()


class TestDirectiveExecutorOverride:
    def test_override_builds_investigation_plan(self):
        ex, fc, seq, state = _make_executor()
        det = Detection(label="distress", confidence=0.9, bearing=45, range=10, position=Pose(5, 5, 0, 0))
        result = ex.execute(Directive(kind="override", args={"detection": det}))
        assert state.nav_plan is not None
        assert len(state.nav_plan.waypoints) >= 1
        assert "override" in result.lower() or "investigate" in result.lower()