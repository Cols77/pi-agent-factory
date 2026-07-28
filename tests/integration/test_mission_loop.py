"""Integration tests for MissionLoop."""
from __future__ import annotations

from drone.interfaces import Directive, Detection, Pose
from drone.fake_flight_controller import FakeFlightController
from drone.mission.state import MissionState
from drone.mission.loop import MissionLoop, MissionResult
from drone.mission.fake_agent import FakeAgent
from drone.mission.scripted_perception import ScriptedPerception
from drone.navigation.registry import NavRegistry
from drone.navigation.perimeter_sweep import PerimeterSweepAlgorithm


def _make_loop(agent, perception, heartbeat_interval: float = 5.0):
    fc = FakeFlightController()
    reg = NavRegistry()
    reg.register("perimeter_sweep", PerimeterSweepAlgorithm())
    return MissionLoop(
        fc=fc,
        perception=perception,
        agent=agent,
        algorithms=reg,
        heartbeat_interval=heartbeat_interval,
        dt=0.05,
    )


class TestMissionLoopBasicRun:
    def test_run_completes_with_land(self):
        """Mission that immediately lands should complete."""
        agent = FakeAgent(responses=[
            Directive(kind="land"),
        ])
        perception = ScriptedPerception.constant([])
        loop = _make_loop(agent, perception, heartbeat_interval=0.1)
        result = loop.run(max_duration=10.0, mission_objectives="test")
        assert isinstance(result, MissionResult)
        assert result.duration < 10.0  # landed before timeout

    def test_run_continues_until_timeout(self):
        """Mission that always continues should run until timeout."""
        agent = FakeAgent()  # always continues
        perception = ScriptedPerception.constant([])
        loop = _make_loop(agent, perception, heartbeat_interval=0.1)
        result = loop.run(max_duration=2.0, mission_objectives="test")
        assert result.duration >= 1.5  # ran for a while


class TestMissionLoopHeartbeat:
    def test_heartbeat_calls_agent(self):
        """Agent should be called at each heartbeat."""
        call_count = 0

        class CountingAgent:
            def decide(self, state: MissionState) -> Directive:
                nonlocal call_count
                call_count += 1
                return Directive(kind="continue")

        agent = CountingAgent()
        perception = ScriptedPerception.constant([])
        loop = _make_loop(agent, perception, heartbeat_interval=0.2)
        loop.run(max_duration=1.0, mission_objectives="test")
        assert call_count >= 3  # several heartbeats in 1 second


class TestMissionLoopPriorityEvent:
    def test_priority_detection_triggers_agent(self):
        """High-priority detection should trigger immediate agent call."""
        agent_calls: list[str] = []

        class TrackingAgent:
            def decide(self, state: MissionState) -> Directive:
                agent_calls.append(state.mission_objectives)
                return Directive(kind="continue")

        agent = TrackingAgent()
        det = Detection(label="distress", confidence=0.9, bearing=0, range=0, position=Pose(5, 5, 0, 0))
        perception = ScriptedPerception.sequential([
            [det],  # first call: priority detection
        ])
        loop = _make_loop(agent, perception, heartbeat_interval=0.1)
        loop.run(max_duration=1.0, mission_objectives="test")
        # Agent should have been called at least once
        assert len(agent_calls) >= 1


class TestMissionLoopBatteryCritical:
    def test_battery_critical_auto_lands(self):
        """Battery below 10% should auto-land without agent."""
        fc = FakeFlightController()
        # Drastically increase battery drain for this test
        fc.BATTERY_DRAIN = 0.01
        agent = FakeAgent()  # always continues
        perception = ScriptedPerception.constant([])
        reg = NavRegistry()
        reg.register("perimeter_sweep", PerimeterSweepAlgorithm())
        loop = MissionLoop(
            fc=fc,
            perception=perception,
            agent=agent,
            algorithms=reg,
            heartbeat_interval=0.1,
            dt=0.05,
        )
        result = loop.run(max_duration=5.0, mission_objectives="test")
        # Should have landed due to battery
        assert result.battery_remaining < 0.15


class TestMissionResult:
    def test_result_fields(self):
        agent = FakeAgent(responses=[Directive(kind="land")])
        perception = ScriptedPerception.constant([])
        loop = _make_loop(agent, perception, heartbeat_interval=0.1)
        result = loop.run(max_duration=5.0, mission_objectives="test")
        assert isinstance(result.final_pose, Pose)
        assert isinstance(result.battery_remaining, float)
        assert isinstance(result.duration, float)
        assert isinstance(result.action_count, int)
