"""Unit tests for NavRegistry."""
from __future__ import annotations

import pytest
from drone.interfaces import NavPlan, NavContext, WaterArea, Pose
from drone.navigation.registry import NavRegistry


class _DummyAlgo:
    """Trivial NavigationAlgorithm for testing."""
    def plan(self, water: WaterArea, context: NavContext) -> NavPlan:
        return NavPlan(
            waypoints=[Pose(0, 0, 5, 0)],
            algorithm_name="dummy",
            created_at=0.0,
        )


@pytest.mark.unit
class TestNavRegistry:
    def test_register_and_lookup(self):
        reg = NavRegistry()
        algo = _DummyAlgo()
        reg.register("dummy", algo)
        found = reg.lookup("dummy")
        assert found is algo

    def test_lookup_unknown_raises(self):
        reg = NavRegistry()
        with pytest.raises(KeyError):
            reg.lookup("nonexistent")

    def test_list_algorithms(self):
        reg = NavRegistry()
        reg.register("alpha", _DummyAlgo())
        reg.register("beta", _DummyAlgo())
        names = reg.list_algorithms()
        assert "alpha" in names
        assert "beta" in names

    def test_list_empty(self):
        reg = NavRegistry()
        assert reg.list_algorithms() == []

    def test_register_replaces(self):
        reg = NavRegistry()
        algo1 = _DummyAlgo()
        algo2 = _DummyAlgo()
        reg.register("same", algo1)
        reg.register("same", algo2)
        assert reg.lookup("same") is algo2
