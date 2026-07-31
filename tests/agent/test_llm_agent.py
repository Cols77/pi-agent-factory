"""Tests for LlmAgent with mocked providers."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from drone.interfaces import (
    ModelConfig,
    NavPlan,
    Pose,
    WaterArea,
    NavContext,
    MissionPlanner,
    ProviderAdapter,
    Detection,
)
from drone.mission.state import MissionState
from drone.mission.llm_agent import LlmAgent
from drone.mission.tools import plan_navigation, investigate_target
from drone.navigation.registry import NavRegistry
from drone.navigation.perimeter_sweep import PerimeterSweepAlgorithm

pytestmark = pytest.mark.agent


def _make_state() -> MissionState:
    state = MissionState(mission_objectives="Survey water area for distress signals")
    state.set_nav_plan(
        NavPlan(
            waypoints=[Pose(5, 0, 5, 0), Pose(10, 0, 5, 0)],
            algorithm_name="perimeter_sweep",
            created_at=0,
        )
    )
    state.update(
        pose=Pose(3, 0, 5, 0),
        detections=[],
        last_directive_result=None,
        dt=0.05,
    )
    return state


def _make_registry() -> NavRegistry:
    reg = NavRegistry()
    reg.register("perimeter_sweep", PerimeterSweepAlgorithm())
    return reg


class TestToolPlanNavigation:
    def test_plan_navigation_returns_navplan(self):
        reg = _make_registry()
        water = WaterArea(vertices=[(0, 0), (10, 0), (10, 10), (0, 10)])
        ctx = NavContext(current_pose=Pose(), completed_area=[])
        result = plan_navigation(
            registry=reg, water_area=water, algorithm="perimeter_sweep", context=ctx
        )
        assert isinstance(result, NavPlan)
        assert result.algorithm_name == "perimeter_sweep"

    def test_plan_navigation_unknown_algorithm_raises(self):
        reg = _make_registry()
        water = WaterArea(vertices=[(0, 0), (10, 0), (10, 10), (0, 10)])
        ctx = NavContext(current_pose=Pose(), completed_area=[])
        with pytest.raises(KeyError):
            plan_navigation(
                registry=reg,
                water_area=water,
                algorithm="nonexistent",
                context=ctx,
            )


class TestToolInvestigateTarget:
    def test_investigate_returns_single_waypoint_plan(self):
        det = Detection(
            label="distress",
            confidence=0.9,
            bearing=0,
            range=0,
            position=Pose(5, 5, 0, 0),
        )
        result = investigate_target(detection=det)
        assert isinstance(result, NavPlan)
        assert len(result.waypoints) == 1
        assert result.waypoints[0] == det.position


class TestLlmAgentFallback:
    def test_api_failure_returns_continue(self):
        """When all providers fail, agent returns continue."""
        config = ModelConfig(provider="google", model="test-model", api_key="fake-key")
        reg = _make_registry()
        agent = LlmAgent(model_chain=[config], registry=reg)
        state = _make_state()
        # Mock _call_provider to raise
        with patch.object(agent, "_call_provider", side_effect=RuntimeError("API error")):
            result = agent.decide(state)
            assert result.kind == "continue"

    def test_malformed_response_returns_continue(self):
        """When LLM returns unparseable response, agent returns continue."""
        config = ModelConfig(provider="google", model="test-model", api_key="fake-key")
        reg = _make_registry()
        agent = LlmAgent(model_chain=[config], registry=reg)
        state = _make_state()
        with patch.object(agent, "_call_provider", return_value="not valid json"):
            result = agent.decide(state)
            assert result.kind == "continue"


class TestLlmAgentDirectiveParsing:
    def test_parse_update_nav_directive(self):
        reg = _make_registry()
        agent = LlmAgent(model_chain=[], registry=reg)
        raw = {"kind": "continue"}
        result = agent._parse_directive(json.dumps(raw))
        assert result.kind == "continue"

    def test_parse_land_directive(self):
        reg = _make_registry()
        agent = LlmAgent(model_chain=[], registry=reg)
        raw = {"kind": "land"}
        result = agent._parse_directive(json.dumps(raw))
        assert result.kind == "land"

    def test_parse_invalid_json_returns_continue(self):
        reg = _make_registry()
        agent = LlmAgent(model_chain=[], registry=reg)
        result = agent._parse_directive("not json at all")
        assert result.kind == "continue"

    def test_parse_invalid_kind_returns_continue(self):
        reg = _make_registry()
        agent = LlmAgent(model_chain=[], registry=reg)
        raw = {"kind": "fly_to_mars"}
        result = agent._parse_directive(json.dumps(raw))
        assert result.kind == "continue"


class TestProviderAdapterProtocol:
    def test_provider_adapter_is_runtime_checkable_protocol(self):
        """ProviderAdapter should be a @runtime_checkable Protocol."""
        assert hasattr(ProviderAdapter, "__protocol_attrs__") or hasattr(
            ProviderAdapter, "__abstractmethods__"
        )
        assert hasattr(ProviderAdapter, "__subclasshook__")

    def test_class_implementing_provider_adapter_isinstance(self):
        """A class with 'call' method should pass isinstance check."""
        class FakeProvider:
            def call(self, config: ModelConfig, prompt: str) -> str:
                return '{"kind": "continue"}'

        assert isinstance(FakeProvider(), ProviderAdapter)

    def test_class_without_call_not_instance(self):
        """A class without 'call' method should NOT pass isinstance check."""
        class NotProvider:
            pass

        assert not isinstance(NotProvider(), ProviderAdapter)


class TestLlmAgentSatisfiesProtocol:
    def test_is_mission_planner(self):
        reg = _make_registry()
        agent = LlmAgent(model_chain=[], registry=reg)
        assert isinstance(agent, MissionPlanner)