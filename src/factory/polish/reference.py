from __future__ import annotations

from pathlib import Path

from factory.polish.playground import PlaygroundSession


class ScenarioReplayPlayground:
    """Thin reference Playground: every ``*.json`` in ``usecases_dir`` is a use
    case. ``setup`` points the human at that file to inspect and describe issues;
    there is no live process, so ``teardown`` is a no-op. Decoupled from any
    project — good enough to prove the contract and the routing spine."""

    def __init__(self, usecases_dir: Path) -> None:
        self._dir = usecases_dir

    def list_usecases(self) -> list[str]:
        return sorted(p.stem for p in self._dir.glob("*.json"))

    def setup(self, usecase: str) -> PlaygroundSession:
        path = self._dir / f"{usecase}.json"
        if not path.exists():
            raise FileNotFoundError(f"no such use case: {usecase}")
        return PlaygroundSession(
            entrypoints=[str(path)],
            describe=f"Reference replay of '{usecase}'. Inspect {path.name} and describe any issue.",
        )
