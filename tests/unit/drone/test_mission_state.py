"""Unit tests for MissionState."""
from __future__ import annotations

import pytest

from drone.interfaces import Detection, NavPlan, Pose
from drone.mission.state import MissionState

pytestmark = pytest.mark.unit


class TestMissionStateConstruction:
    def test_default_construction(self):
        state = MissionState(mission_objectives="Survey water area")
        assert state.mission_objectives == "Survey water area"
        assert state.mission_clock == 0.0
        assert state.nav_plan is None
        assert state.current_waypoint_idx == 0
        assert state.waypoints_completed == 0
        assert state.waypoints_total == 0
        assert state.battery == 1.0
        assert state.action_log == []
        assert state.all_detections == []
        assert state.new_detections == []


class TestMissionStateUpdate:
    def test_update_advances_clock(self):
        state = MissionState(mission_objectives="test")
        state.update(pose=Pose(1, 2, 3, 0), detections=[], last_directive_result=None, dt=0.05)
        assert state.mission_clock == 0.05

    def test_update_accumulates_detections(self):
        state = MissionState(mission_objectives="test")
        det = Detection(label="boat", confidence=0.9, bearing=45, range=10, position=Pose())
        state.update(pose=Pose(), detections=[det], last_directive_result=None, dt=0.05)
        assert len(state.all_detections) == 1
        assert len(state.new_detections) == 1

    def test_update_clears_new_detections_on_next_call(self):
        state = MissionState(mission_objectives="test")
        det1 = Detection(label="boat", confidence=0.9, bearing=0, range=0, position=Pose())
        det2 = Detection(label="ship", confidence=0.8, bearing=0, range=0, position=Pose())
        state.update(pose=Pose(), detections=[det1], last_directive_result=None, dt=0.05)
        assert len(state.new_detections) == 1
        state.update(pose=Pose(), detections=[det2], last_directive_result=None, dt=0.05)
        assert len(state.new_detections) == 1
        assert len(state.all_detections) == 2

    def test_update_records_pose_and_battery(self):
        state = MissionState(mission_objectives="test")
        state.update(pose=Pose(5, 5, 5, 90), detections=[], last_directive_result=None, battery=0.8, dt=0.05)
        assert state.current_pose == Pose(5, 5, 5, 90)
        assert state.battery == 0.8

    def test_update_logs_directive_result(self):
        state = MissionState(mission_objectives="test")
        state.update(pose=Pose(), detections=[], last_directive_result="no-op", dt=0.05)
        assert state.action_log == [(0.05, "no-op")]


class TestMissionStateSummary:
    def test_basic_summary(self):
        state = MissionState(mission_objectives="Survey water")
        summary = state.summary()
        assert "MISSION: Survey water" in summary
        assert "TIME ELAPSED:" in summary
        assert "BATTERY:" in summary

    def test_summary_with_detections(self):
        state = MissionState(mission_objectives="test")
        det = Detection(label="distress", confidence=0.95, bearing=90, range=20, position=Pose())
        state.update(pose=Pose(), detections=[det], last_directive_result=None, dt=0.05)
        summary = state.summary()
        assert "distress" in summary
        assert "HIGH" in summary

    def test_summary_low_confidence(self):
        state = MissionState(mission_objectives="test")
        det = Detection(label="bird", confidence=0.3, bearing=0, range=0, position=Pose())
        state.update(pose=Pose(), detections=[det], last_directive_result=None, dt=0.05)
        assert "LOW" in state.summary()

    def test_summary_medium_confidence(self):
        state = MissionState(mission_objectives="test")
        det = Detection(label="boat", confidence=0.7, bearing=0, range=0, position=Pose())
        state.update(pose=Pose(), detections=[det], last_directive_result=None, dt=0.05)
        assert "MEDIUM" in state.summary()

    def test_summary_battery_critical(self):
        state = MissionState(mission_objectives="test")
        state.update(pose=Pose(), detections=[], last_directive_result=None, battery=0.05, dt=0.05)
        assert "CRITICAL" in state.summary()

    def test_summary_nav_plan(self):
        state = MissionState(mission_objectives="test")
        plan = NavPlan(
            waypoints=[Pose(1, 0, 5, 0), Pose(2, 0, 5, 0)],
            algorithm_name="perimeter_sweep",
            created_at=0,
        )
        state.set_nav_plan(plan)
        summary = state.summary()
        assert "perimeter_sweep" in summary
        assert "0/2" in summary

    def test_summary_no_nav_plan(self):
        state = MissionState(mission_objectives="test")
        assert "No active nav plan" in state.summary()

    def test_summary_objectives(self):
        state = MissionState(mission_objectives="test")
        state.mark_objective("survey_water", "in_progress")
        summary = state.summary()
        assert "survey_water" in summary
        assert "in_progress" in summary


class TestAdvanceWaypoint:
    def test_advance(self):
        state = MissionState(mission_objectives="test")
        plan = NavPlan(
            waypoints=[Pose(1, 0, 5, 0), Pose(2, 0, 5, 0), Pose(3, 0, 5, 0)],
            algorithm_name="test",
            created_at=0,
        )
        state.set_nav_plan(plan)
        state.advance_waypoint()
        assert state.current_waypoint_idx == 1
        assert state.waypoints_completed == 1

    def test_advance_beyond_end_stays_at_last(self):
        state = MissionState(mission_objectives="test")
        plan = NavPlan(waypoints=[Pose(1, 0, 5, 0)], algorithm_name="test", created_at=0)
        state.set_nav_plan(plan)
        state.advance_waypoint()
        assert state.current_waypoint_idx == 1
        assert state.waypoints_completed == 1


class TestSetNavPlan:
    def test_set_resets_tracking(self):
        state = MissionState(mission_objectives="test")
        plan1 = NavPlan(
            waypoints=[Pose(1, 0, 5, 0), Pose(2, 0, 5, 0)],
            algorithm_name="a",
            created_at=0,
        )
        state.set_nav_plan(plan1)
        state.advance_waypoint()
        plan2 = NavPlan(waypoints=[Pose(5, 5, 5, 0)], algorithm_name="b", created_at=1.0)
        state.set_nav_plan(plan2)
        assert state.current_waypoint_idx == 0
        assert state.waypoints_completed == 0
        assert state.waypoints_total == 1
        assert state.nav_plan == plan2


class TestMarkObjective:
    def test_mark(self):
        state = MissionState(mission_objectives="test")
        state.mark_objective("survey_water", "in_progress")
        assert state.objectives_status["survey_water"] == "in_progress"
        state.mark_objective("survey_water", "complete")
        assert state.objectives_status["survey_water"] == "complete"
