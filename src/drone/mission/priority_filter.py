"""Check detections against mission priority rules."""
from __future__ import annotations

from drone.interfaces import Detection, DetectionEvent, PriorityRule


class PriorityFilter:
    """Match detections against an ordered set of priority rules."""

    def __init__(self, rules: list[PriorityRule] | None = None) -> None:
        self._rules = rules if rules is not None else []

    def check(self, detection: Detection) -> DetectionEvent | None:
        """Return an event for the first matching rule, or ``None``."""
        for rule in self._rules:
            if (
                detection.label == rule.label
                and detection.confidence >= rule.min_confidence
            ):
                return DetectionEvent(
                    detection=detection,
                    reason=rule.reason_template.format(label=rule.label),
                )
        return None

    @classmethod
    def default(cls) -> PriorityFilter:
        """Create a filter that prioritizes likely distress detections."""
        return cls(
            rules=[
                PriorityRule(
                    label="distress",
                    min_confidence=0.8,
                    reason_template="possible {label}",
                )
            ]
        )
