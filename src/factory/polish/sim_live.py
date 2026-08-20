"""SimLivePlayground: launch a live sim testbench window for one scenario.

Mirror of DevServerPlayground, but the "service" is a desktop sim process:
setup() spawns the configured run command with the resolved scenario path
appended and the child opens the real pygame window; teardown kills the child
process tree. Nothing project-specific -- the scenario directory and run
command come from config.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from factory.polish.devserver import _kill
from factory.polish.playground import PlaygroundSession


class SimLivePlayground:
    """Config-driven playground: spawn a live sim window for one scenario.

    Purpose: let a factory polish session play-test a scenario in the live
    sim window; the child writes bug snapshots (B key) and the session routes
    findings to tasks. The scenario directory and run command are
    config-supplied so no project specifics leak into the factory.
    """

    def __init__(
        self, scenarios_dir: Path, run_cmd: list[str], *, project_root: Path
    ) -> None:
        """Store the scenario dir, run command, and project root.

        Purpose: hold the configuration for this playground.

        Args:
            scenarios_dir: directory (already resolved against the project
                root) whose ``**/*.yaml`` files are the use cases.
            run_cmd: the command that launches the sim; the resolved scenario
                path is appended before spawning.
            project_root: the product repo root; the child runs here so
                ``scenarios/bugs`` snapshots land in the repo.

        Returns:
            None.

        Raises:
            None.
        """
        self._scenarios_dir = scenarios_dir
        self._run_cmd = run_cmd
        self._root = project_root

    @classmethod
    def from_config(cls, params: dict, project_root: Path) -> "SimLivePlayground":
        """Build a playground from a ``playgrounds: sim-live:`` config block.

        Purpose: deserialize the factory.yaml block; ``scenarios_dir`` is
        resolved against the project root and ``run_command`` is kept as the
        argv list (the scenario path is appended at setup time).

        Args:
            params: the config block, e.g. ``{"scenarios_dir":
                "scenarios/reference", "run_command": ["uv", "run",
                "python", "-m", "sim"]}``.
            project_root: the product repo root.

        Returns:
            A configured SimLivePlayground.

        Raises:
            None.
        """
        return cls(
            project_root / Path(params["scenarios_dir"]),
            list(params["run_command"]),
            project_root=project_root,
        )

    def list_usecases(self) -> list[str]:
        """List scenario stems under the scenarios directory.

        Purpose: return the playable use cases, one per ``**/*.yaml``.

        Returns:
            Sorted stems of every ``*.yaml`` under the scenarios directory
            (recursively); non-YAML files are ignored.

        Raises:
            None.
        """
        return sorted(p.stem for p in self._scenarios_dir.glob("**/*.yaml"))

    def setup(self, usecase: str) -> PlaygroundSession:
        """Spawn the live sim window for one scenario.

        Args:
            usecase: a scenario stem from ``list_usecases()``.

        Returns:
            A PlaygroundSession with the scenario path as the single
            entrypoint and an on_teardown that kills the child.

        Raises:
            FileNotFoundError: if no ``<usecase>.yaml`` exists.
        """
        path = self._scenarios_dir / f"{usecase}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"no such scenario: {path}")
        proc = subprocess.Popen([*self._run_cmd, str(path)], cwd=str(self._root))

        def _teardown() -> None:
            _kill(proc)

        return PlaygroundSession(
            entrypoints=[str(path)],
            describe=(
                f"Use case '{usecase}': live sim window running {path.name}; "
                "play the scenario and press B to capture a bug snapshot."
            ),
            on_teardown=_teardown,
        )