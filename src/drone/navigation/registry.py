"""NavRegistry — registry of named NavigationAlgorithm implementations."""
from __future__ import annotations

from drone.interfaces import NavigationAlgorithm


class NavRegistry:
    """Registry of named NavigationAlgorithm implementations."""

    def __init__(self) -> None:
        self._algorithms: dict[str, NavigationAlgorithm] = {}

    def register(self, name: str, algorithm: NavigationAlgorithm) -> None:
        """Register a navigation algorithm under a name."""
        self._algorithms[name] = algorithm

    def lookup(self, name: str) -> NavigationAlgorithm:
        """Look up a registered algorithm by name. Raises KeyError if not found."""
        if name not in self._algorithms:
            raise KeyError(f"No algorithm registered with name '{name}'")
        return self._algorithms[name]

    def list_algorithms(self) -> list[str]:
        """Return list of registered algorithm names."""
        return list(self._algorithms.keys())