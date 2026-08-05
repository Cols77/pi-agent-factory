from __future__ import annotations

import shlex
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


def _quote_for_shell(path: str) -> str:
    """Quote an interpreter path for safe interpolation into a `shell=True`
    command string. cmd.exe and POSIX shells disagree on quoting rules, so
    this picks the platform-correct call rather than hardcoding either --
    an unquoted path containing a space (e.g. under 'C:\\Users\\First Last\\'
    or 'C:\\Program Files\\...') would otherwise split into two tokens and
    fail every gate.
    """
    if sys.platform == "win32":
        return subprocess.list2cmdline([path])
    return shlex.quote(path)


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
            cmd = step.cmd.replace("{python}", _quote_for_shell(sys.executable))
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
