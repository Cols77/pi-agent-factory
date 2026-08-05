from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from factory.config import GateStep
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

    def run(
        self,
        role: AgentRole,
        prompt: str,
        on_snippet: Callable[[str], None] | None = None,
        on_session_id: Callable[[str], None] | None = None,
    ) -> AgentResult:
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
            cmd = [sys.executable, "-m", "pytest", "tests/integration/", "-q", "-m", "integration"]
        else:
            cmd = [sys.executable, script]
        if self._log_dir is None:
            return subprocess.run(cmd, cwd=self._repo_root).returncode
        self._log_dir.mkdir(parents=True, exist_ok=True)
        log_path = self._log_dir / f"{name}-gate.log"
        proc = subprocess.run(
            cmd, cwd=self._repo_root,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        log_path.write_text((proc.stdout or "") + (proc.stderr or ""), encoding="utf-8")
        return proc.returncode


class ConfigGateRunner:
    """Runs the gate steps a project declares in .factory/factory.yaml.

    An undeclared gate passes and is recorded in .skipped: a webapp has no
    'sim', and forcing it to invent one invites `exit 0` stubs, which are worse
    than an honest skip. Skipped gates are logged so a typo'd key reads as
    'not declared' rather than vanishing.
    """

    # pytest's "no tests collected". A declared gate that matches nothing is a
    # false red -- and it fires the moment a repo split moves tests out.
    _NO_TESTS_COLLECTED = 5

    def __init__(self, repo_root: Path, gates: dict[str, list[GateStep]],
                 log_dir: Path | None = None) -> None:
        self._repo_root = repo_root
        self._gates = gates
        self._log_dir = log_dir
        self.skipped: list[str] = []

    def run(self, name: str) -> int:
        steps = self._gates.get(name)
        if not steps:
            if name not in self.skipped:
                self.skipped.append(name)
            self._write_log(name, f"gate {name!r} is not declared in .factory/factory.yaml; skipped\n")
            return 0

        chunks: list[str] = []
        for step in steps:
            cmd = step.cmd.replace("{python}", sys.executable)
            cwd = self._repo_root / step.cwd if step.cwd else self._repo_root
            if self._log_dir is None:
                rc = subprocess.run(cmd, shell=True, cwd=str(cwd), check=False).returncode
            else:
                proc = subprocess.run(
                    cmd, shell=True, cwd=str(cwd), check=False,
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                )
                chunks.append(f"$ {cmd}\n{proc.stdout or ''}{proc.stderr or ''}")
                rc = proc.returncode
            if rc == self._NO_TESTS_COLLECTED:
                chunks.append(f"[gate] step matched nothing (exit 5), treated as pass: {cmd}\n")
                continue
            if rc != 0:
                self._write_log(name, "".join(chunks))
                return rc
        self._write_log(name, "".join(chunks))
        return 0

    def _write_log(self, name: str, text: str) -> None:
        if self._log_dir is None:
            return
        self._log_dir.mkdir(parents=True, exist_ok=True)
        (self._log_dir / f"{name}-gate.log").write_text(text, encoding="utf-8")
