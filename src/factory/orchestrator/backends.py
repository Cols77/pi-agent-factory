from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from factory.orchestrator.types import AgentResult, AgentRole


class AgentBackend(Protocol):
    def run(
        self,
        role: AgentRole,
        prompt: str,
        on_snippet: Callable[[str], None] | None = None,
        on_session_id: Callable[[str], None] | None = None,
    ) -> AgentResult: ...


class GateRunner(Protocol):
    def run(self, name: str) -> int: ...


class FakeAgentBackend:
    def __init__(self, scripts: dict[AgentRole, list[AgentResult]]) -> None:
        self._scripts = {k: list(v) for k, v in scripts.items()}
        # Recorded so tests can assert what a role was actually told, not just
        # what it returned.
        self.prompts: list[tuple[AgentRole, str]] = []

    def run(
        self,
        role: AgentRole,
        prompt: str,
        on_snippet: Callable[[str], None] | None = None,
        on_session_id: Callable[[str], None] | None = None,
    ) -> AgentResult:
        self.prompts.append((role, prompt))
        queue = self._scripts.get(role)
        assert queue, f"FakeAgentBackend: no scripted result for {role}"
        return queue.pop(0)


class FakeGateRunner:
    def __init__(self, results: dict[str, list[int]] | None = None) -> None:
        self._results = {k: list(v) for k, v in (results or {}).items()}

    def run(self, name: str) -> int:
        queue = self._results.get(name)
        if queue:
            return queue.pop(0)
        return 0


# A gate the project does not provide. Distinct from 0 (ran, passed) and from any
# positive code (ran, failed) -- absence must never be reported as failure, or a
# repo without a sim suite fails every task at the validation node.
GATE_NOT_APPLICABLE = -1

# pytest's exit code for "no tests were collected". For a gate that means the
# project has no such suite, not that the suite failed.
PYTEST_NO_TESTS_COLLECTED = 5


def _translate(code: int) -> int:
    return GATE_NOT_APPLICABLE if code == PYTEST_NO_TESTS_COLLECTED else code


class SubprocessGateRunner:
    _SCRIPTS = {
        "unit": "scripts/gates/unit.py",
        "sim": "scripts/gates/sim_smoke.py",
        "full": "scripts/gates/all.py",
        "integration": None,  # handled inline in run()
    }

    def __init__(self, repo_root: Path, log_dir: Path | None = None) -> None:
        self._repo_root = repo_root
        self._log_dir = log_dir

    def run(self, name: str) -> int:
        script = self._SCRIPTS[name]
        if name == "integration":
            if not (self._repo_root / "tests" / "integration").is_dir():
                return GATE_NOT_APPLICABLE
            cmd = [sys.executable, "-m", "pytest", "tests/integration/", "-q", "-m", "integration"]
        else:
            if not (self._repo_root / script).is_file():
                return GATE_NOT_APPLICABLE
            cmd = [sys.executable, script]
        if self._log_dir is None:
            return _translate(subprocess.run(cmd, cwd=self._repo_root).returncode)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        log_path = self._log_dir / f"{name}-gate.log"
        proc = subprocess.run(
            cmd, cwd=self._repo_root,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        log_path.write_text((proc.stdout or "") + (proc.stderr or ""), encoding="utf-8")
        return _translate(proc.returncode)
