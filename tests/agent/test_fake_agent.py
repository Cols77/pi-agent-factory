"""Tests for FakeAgent."""
from __future__ import annotations

import pytest

from drone.interfaces import Directive, MissionPlanner
from drone.mission.fake_agent import FakeAgent
from drone.mission.state import MissionState

pytestmark = pytest.mark.agent


class TestFakeAgent:
    def test_returns_scripted_directives(self):
        state = MissionState(mission_objectives="test")
        agent = FakeAgent(responses=[
            Directive(kind="continue"),
            Directive(kind="land"),
        ])
        assert agent.decide(state).kind == "continue"
        assert agent.decide(state).kind == "land"

    def test_returns_continue_after_exhausted(self):
        state = MissionState(mission_objectives="test")
        agent = FakeAgent(responses=[Directive(kind="land")])
        agent.decide(state)  # consume the scripted response
        result = agent.decide(state)
        assert result.kind == "continue"

    def test_default_is_continue(self):
        state = MissionState(mission_objectives="test")
        agent = FakeAgent()  # no responses
        result = agent.decide(state)
        assert result.kind == "continue"

    def test_satisfies_mission_planner_protocol(self):
        agent = FakeAgent()
        assert isinstance(agent, MissionPlanner)