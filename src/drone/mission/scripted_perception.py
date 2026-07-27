"""ScriptedPerception — deterministic Perception implementation for testing."""
from __future__ import annotations

from drone.interfaces import Detection


class ScriptedPerception:
    """Deterministic Perception implementation for testing.

    Provides a scripted sequence of detection lists, useful for
    testing mission logic without real perception hardware.
    """

    def __init__(self, script: list[list[Detection]]) -> None:
        self._script = script
        self._idx: int = 0

    def get_detections(self) -> list[Detection]:
        """Return the next scripted detection list.

        Returns an empty list once the script is exhausted.
        Subsequent calls continue to return empty lists.
        """
        if self._idx >= len(self._script):
            return []
        result = self._script[self._idx]
        self._idx += 1
        return result

    @classmethod
    def constant(cls, detections: list[Detection]) -> ScriptedPerception:
        """Return the same detections on every call (infinite repeat)."""
        return _ConstantPerception(detections)

    @classmethod
    def sequential(cls, steps: list[list[Detection]]) -> ScriptedPerception:
        """Return steps[0], steps[1], ..., then empty lists."""
        return cls(script=steps)


class _ConstantPerception(ScriptedPerception):
    """A ScriptedPerception that always returns the same detections."""

    def __init__(self, detections: list[Detection]) -> None:
        super().__init__(script=[detections])

    def get_detections(self) -> list[Detection]:
        # Always return the first step without advancing the index
        return self._script[0]