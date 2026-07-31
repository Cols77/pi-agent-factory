"""Unit tests for PerimeterSweepAlgorithm."""
from __future__ import annotations

import math

import pytest
from drone.interfaces import WaterArea, NavContext, NavPlan, Pose
from drone.navigation.perimeter_sweep import PerimeterSweepAlgorithm

pytestmark = pytest.mark.unit


class TestPerimeterSweepBasic:
    def test_square_produces_waypoints(self):
        """A square water area should produce perimeter waypoints."""
        water = WaterArea(vertices=[(0, 0), (10, 0), (10, 10), (0, 10)])
        ctx = NavContext(current_pose=Pose(0, 0, 0, 0), completed_area=[])
        algo = PerimeterSweepAlgorithm(altitude=5.0, offset=1.0)
        plan = algo.plan(water, ctx)
        assert isinstance(plan, NavPlan)
        assert plan.algorithm_name == "perimeter_sweep"
        assert len(plan.waypoints) >= 4  # at least one per side
        # All waypoints at correct altitude
        for wp in plan.waypoints:
            assert wp.z == 5.0

    def test_triangle_produces_waypoints(self):
        water = WaterArea(vertices=[(0, 0), (10, 0), (5, 10)])
        ctx = NavContext(current_pose=Pose(0, 0, 0, 0), completed_area=[])
        algo = PerimeterSweepAlgorithm(altitude=5.0, offset=1.0)
        plan = algo.plan(water, ctx)
        assert len(plan.waypoints) >= 3

    def test_waypoints_start_near_current_pose(self):
        water = WaterArea(vertices=[(0, 0), (10, 0), (10, 10), (0, 10)])
        ctx = NavContext(current_pose=Pose(10, 0, 0, 0), completed_area=[])
        algo = PerimeterSweepAlgorithm(altitude=5.0, offset=1.0)
        plan = algo.plan(water, ctx)
        assert len(plan.waypoints) > 0
        first = plan.waypoints[0]
        # First waypoint should be closest to current_pose (10, 0)
        dists = [math.sqrt((wp.x - 10) ** 2 + (wp.y - 0) ** 2) for wp in plan.waypoints[:-1]]  # exclude loop-close
        assert math.sqrt((first.x - 10) ** 2 + (first.y - 0) ** 2) == min(dists)

    def test_loop_closes(self):
        """Last waypoint should be same as first (close the loop)."""
        water = WaterArea(vertices=[(0, 0), (10, 0), (10, 10), (0, 10)])
        ctx = NavContext(current_pose=Pose(0, 0, 0, 0), completed_area=[])
        algo = PerimeterSweepAlgorithm(altitude=5.0, offset=1.0)
        plan = algo.plan(water, ctx)
        assert len(plan.waypoints) >= 2
        first = plan.waypoints[0]
        last = plan.waypoints[-1]
        assert abs(first.x - last.x) < 0.1
        assert abs(first.y - last.y) < 0.1


class TestPerimeterSweepInset:
    def test_inset_waypoints_are_inside(self):
        """Inset waypoints should be inside the polygon."""
        water = WaterArea(vertices=[(0, 0), (10, 0), (10, 10), (0, 10)])
        ctx = NavContext(current_pose=Pose(0, 0, 0, 0), completed_area=[])
        algo = PerimeterSweepAlgorithm(altitude=5.0, offset=2.0)
        plan = algo.plan(water, ctx)
        for wp in plan.waypoints[:-1]:  # exclude loop-close
            assert 2.0 <= wp.x <= 8.0, f"x={wp.x} not in [2, 8]"
            assert 2.0 <= wp.y <= 8.0, f"y={wp.y} not in [2, 8]"


class TestPerimeterSweepMaxDistFromShore:
    def test_max_distance_clips_waypoints(self):
        """Large water area with max_distance_from_shore should clip inner points."""
        water = WaterArea(vertices=[(0, 0), (100, 0), (100, 100), (0, 100)])
        ctx = NavContext(current_pose=Pose(0, 0, 0, 0), completed_area=[])
        algo = PerimeterSweepAlgorithm(altitude=5.0, offset=1.0, max_distance_from_shore=5.0)
        plan = algo.plan(water, ctx)
        # All waypoints should be within 5+1=6 meters of shoreline
        for wp in plan.waypoints[:-1]:
            # Distance to nearest edge
            d = min(wp.x, wp.y, 100 - wp.x, 100 - wp.y)
            assert d <= 7.0, f"waypoint at ({wp.x},{wp.y}) is {d}m from shore"


class TestPerimeterSweepDefaultParams:
    def test_default_altitude_and_offset(self):
        water = WaterArea(vertices=[(0, 0), (10, 0), (10, 10), (0, 10)])
        ctx = NavContext(current_pose=Pose(0, 0, 0, 0), completed_area=[])
        algo = PerimeterSweepAlgorithm()
        plan = algo.plan(water, ctx)
        for wp in plan.waypoints:
            assert wp.z == 5.0  # default altitude