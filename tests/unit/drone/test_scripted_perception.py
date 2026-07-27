"""Unit tests for ScriptedPerception."""
from __future__ import annotations

import pytest

from drone.interfaces import Detection, Pose
from drone.mission.scripted_perception import ScriptedPerception

pytestmark = pytest.mark.unit


def _det(label: str) -> Detection:
    return Detection(label=label, confidence=0.9, bearing=0, range=0, position=Pose())


class TestScriptedPerceptionSequential:
    def test_sequential_returns_steps(self):
        sp = ScriptedPerception.sequential([
            [_det("a")],
            [_det("b"), _det("c")],
        ])
        assert len(sp.get_detections()) == 1
        assert len(sp.get_detections()) == 2

    def test_sequential_returns_empty_after_exhausted(self):
        sp = ScriptedPerception.sequential([[_det("x")]])
        sp.get_detections()  # step 0
        result = sp.get_detections()  # step 1 — exhausted
        assert result == []
        result2 = sp.get_detections()  # still empty
        assert result2 == []


class TestScriptedPerceptionConstant:
    def test_constant_repeats_forever(self):
        dets = [_det("a"), _det("b")]
        sp = ScriptedPerception.constant(dets)
        for _ in range(10):
            result = sp.get_detections()
            assert len(result) == 2
            assert result[0].label == "a"


class TestScriptedPerceptionRaw:
    def test_raw_script(self):
        sp = ScriptedPerception(script=[[_det("x")], []])
        assert len(sp.get_detections()) == 1
        assert sp.get_detections() == []
        assert sp.get_detections() == []