"""FakeAgent — deterministic MissionPlanner for testing."""
from __future__ import annotations

from drone.interfaces import Directive
from drone.mission.state import MissionState


class FakeAgent:
    """Deterministic MissionPlanner for testing."""

    def __init__(self, responses: list[Directive] | None = None) -> None:
        self._responses = list(responses) if responses is not None else []
        self._idx: int = 0

    def decide(self, state: MissionState) -> Directive:
        """Return next scripted directive. Returns continue after script exhausted."""
        if self._idx < len(self._responses):
            result = self._responses[self._idx]
            self._idx += 1
            return result
        return Directive(kind="continue")