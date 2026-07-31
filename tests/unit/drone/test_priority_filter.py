"""Unit tests for PriorityFilter."""
from __future__ import annotations

import pytest

from drone.interfaces import Detection, Pose, PriorityRule
from drone.mission.priority_filter import PriorityFilter

pytestmark = pytest.mark.unit


class TestPriorityFilterCheck:
    def test_match(self):
        rule = PriorityRule(label="distress", min_confidence=0.8, reason_template="possible {label}")
        pf = PriorityFilter(rules=[rule])
        det = Detection(label="distress", confidence=0.9, bearing=0, range=0, position=Pose())
        result = pf.check(det)
        assert result is not None
        assert result.reason == "possible distress"
        assert result.detection == det

    def test_no_match_label(self):
        rule = PriorityRule(label="distress", min_confidence=0.8, reason_template="possible {label}")
        pf = PriorityFilter(rules=[rule])
        det = Detection(label="boat", confidence=0.9, bearing=0, range=0, position=Pose())
        result = pf.check(det)
        assert result is None

    def test_no_match_confidence_below_threshold(self):
        rule = PriorityRule(label="distress", min_confidence=0.8, reason_template="possible {label}")
        pf = PriorityFilter(rules=[rule])
        det = Detection(label="distress", confidence=0.5, bearing=0, range=0, position=Pose())
        result = pf.check(det)
        assert result is None

    def test_match_exact_confidence(self):
        rule = PriorityRule(label="distress", min_confidence=0.8, reason_template="possible {label}")
        pf = PriorityFilter(rules=[rule])
        det = Detection(label="distress", confidence=0.8, bearing=0, range=0, position=Pose())
        result = pf.check(det)
        assert result is not None

    def test_multiple_rules_first_match(self):
        r1 = PriorityRule(label="distress", min_confidence=0.8, reason_template="possible {label}")
        r2 = PriorityRule(label="fire", min_confidence=0.7, reason_template="detected {label}")
        pf = PriorityFilter(rules=[r1, r2])
        det = Detection(label="fire", confidence=0.8, bearing=0, range=0, position=Pose())
        result = pf.check(det)
        assert result is not None
        assert result.reason == "detected fire"

    def test_no_rules_returns_none(self):
        pf = PriorityFilter(rules=[])
        det = Detection(label="distress", confidence=0.99, bearing=0, range=0, position=Pose())
        result = pf.check(det)
        assert result is None


class TestPriorityFilterDefault:
    def test_default_has_distress_rule(self):
        pf = PriorityFilter.default()
        det = Detection(label="distress", confidence=0.85, bearing=0, range=0, position=Pose())
        result = pf.check(det)
        assert result is not None
        assert "distress" in result.reason

    def test_default_ignores_low_confidence(self):
        pf = PriorityFilter.default()
        det = Detection(label="distress", confidence=0.3, bearing=0, range=0, position=Pose())
        result = pf.check(det)
        assert result is None
