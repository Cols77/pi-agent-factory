from __future__ import annotations

import shlex
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from factory.config import GateStep
from factory.orchestrator.types import AgentRole
from substrate.agents.model import AgentResult
from substrate.kb.signatures import redact_secrets


class AgentBackend(Protocol):
    def run(
        self,
        role: AgentRole,
        prompt: str,
        on_snippet: Callable[[str], None] | None = None,
        on_session_id: Callable[[str], None] | None = None,
    ) -> AgentResult: ...


@dataclass
class GateRun:
    """The structured result of one gate execution -- everything `run(name)`'s
    bare returncode throws away: the captured stdout+stderr (so a caller can
    derive canonical failure signatures without re-running the gate), the
    commands actually executed, and where the log landed (if anywhere).

    `applicable` mirrors GATE_NOT_APPLICABLE's existing semantics (an
    undeclared gate is absent, not a fabricated failure) as a proper bool
    instead of a magic returncode a caller has to remember to compare against.
    """

    name: str
    returncode: int
    output: str
    applicable: bool
    commands: tuple[str, ...] = ()
    log_path: Path | None = None

    # Bound on the `output` text that reaches to_dict() -- and from there the
    # durable session record (NodeEvent.extra["gate_detail"]). Real failing
    # suites routinely produce tens to hundreds of KB of stdout+stderr; only
    # the tail (where the actual failure/traceback lives) is worth keeping,
    # and `events` accumulates this across every dev/validation/review cycle
    # in a task.
    _OUTPUT_DICT_MAX_CHARS = 8000
    _TRUNCATION_MARKER = "…truncated…\n"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "returncode": self.returncode,
            "output": self._redacted_truncated_output(),
            "applicable": self.applicable,
            "commands": list(self.commands),
            "log_path": str(self.log_path) if self.log_path is not None else None,
        }

    def _redacted_truncated_output(self) -> str:
        """`output` as it may safely be persisted into a durable session
        record: secrets redacted the same way KB signature extraction
        redacts them (so a credential scrubbed from `gate_signatures` isn't
        left intact one key over in `gate_detail`), then capped to a bounded
        tail. `self.output` itself is left untouched -- it stays the full,
        unredacted, in-memory text for any caller (e.g. signature
        extraction) that needs it."""
        text = redact_secrets(self.output)
        if len(text) > self._OUTPUT_DICT_MAX_CHARS:
            text = self._TRUNCATION_MARKER + text[-self._OUTPUT_DICT_MAX_CHARS:]
        return text


class GateRunner(Protocol):
    def run(self, name: str) -> int: ...
    def run_detail(self, name: str) -> GateRun: ...


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
    """Test double for GateRunner. Each queued item may be a plain int
    (returncode only -- wrapped into a GateRun with empty output, matching
    the pre-GateRun scripting style every existing test uses) or a scripted
    GateRun (when a test needs to control output/applicable/commands too,
    e.g. to drive canonical-signature extraction from a fake gate)."""

    def __init__(self, results: dict[str, list[int | GateRun]] | None = None) -> None:
        self._results = {k: list(v) for k, v in (results or {}).items()}

    def run(self, name: str) -> int:
        return self.run_detail(name).returncode

    def run_detail(self, name: str) -> GateRun:
        queue = self._results.get(name)
        if queue:
            item = queue.pop(0)
            if isinstance(item, GateRun):
                return item
            return GateRun(
                name=name,
                returncode=item,
                output="",
                applicable=item != GATE_NOT_APPLICABLE,
            )
        return GateRun(name=name, returncode=0, output="", applicable=True)


# A gate the project does not provide. Distinct from 0 (ran, passed) and from any
# positive code (ran, failed) -- absence must never be reported as failure, or a
# repo without a sim suite fails every task at the validation node.
GATE_NOT_APPLICABLE = -1

# pytest's exit code for "no tests were collected". For a gate that means the
# project has no such suite, not that the suite failed.
PYTEST_NO_TESTS_COLLECTED = 5


def _is_pytest_command(argv: Sequence[str]) -> bool:
    """Return whether parsed argv contains an exact ``pytest`` token.

    This aligns the orchestrator with Task 3's workflow contract: exit 5 is
    normalized only for commands invoking pytest, including ``pytest ...`` and
    ``python -m pytest ...``, not for tokens such as ``pytest-config``.
    """
    return "pytest" in argv


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


def _target_python(repo_root: Path) -> str:
    """The interpreter a gate should run under: the TARGET repo's, not ours.

    `sys.executable` is whatever runs the orchestrator. On a cross-repo run
    (`--repo <other>`) that is the factory's own venv, which does not have the
    target project installed -- so every gate executed in the wrong
    environment. In cool_physical_ai_project this surfaced as 33 collection
    errors (`ModuleNotFoundError: No module named 'drone'`) and escalated T-059
    as "unit tests red", even though the package imported fine under the
    target's own venv.

    This mirrors the inverse lesson already recorded in `__main__`: the
    scope-guard extension ships with the FACTORY and must not be derived from
    --repo. Ownership decides the source -- the interpreter belongs to the
    target, the extension belongs to us.

    Falls back to `sys.executable` when the target has no `.venv`, which is the
    common case of the factory running against itself.
    """
    parts = ("Scripts", "python.exe") if sys.platform == "win32" else ("bin", "python")
    candidate = repo_root.joinpath(".venv", *parts)
    try:
        if candidate.is_file():
            return str(candidate)
    except OSError:
        pass
    return sys.executable


class ConfigGateRunner:
    """Runs the gate steps a project declares in .factory/factory.yaml.

    An undeclared gate reports GATE_NOT_APPLICABLE and is recorded in .skipped:
    a webapp has no 'sim', and forcing it to invent one invites `exit 0` stubs,
    which are worse than an honest skip. Not-applicable is deliberately distinct
    from 0 -- run_validation treats both as non-failing, but only 0 means a suite
    actually ran and passed. Skipped gates are logged so a typo'd key reads as
    'not declared' rather than vanishing.
    """

    def __init__(self, repo_root: Path, gates: dict[str, list[GateStep]],
                 log_dir: Path | None = None) -> None:
        self._repo_root = repo_root
        self._gates = gates
        self._log_dir = log_dir
        self.skipped: list[str] = []

    def run(self, name: str) -> int:
        return self.run_detail(name).returncode

    def run_detail(self, name: str) -> GateRun:
        """The one execution per call: both the returncode AND the captured
        output come from this single subprocess pass -- a caller (e.g. the
        runner extracting canonical failure signatures) never has to re-run
        the gate to see what it printed."""
        steps = self._gates.get(name)
        if not steps:
            if name not in self.skipped:
                self.skipped.append(name)
            text = f"gate {name!r} is not declared in .factory/factory.yaml; skipped\n"
            self._write_log(name, text)
            return GateRun(
                name=name, returncode=GATE_NOT_APPLICABLE, output=text, applicable=False,
                log_path=self._log_path(name),
            )

        chunks: list[str] = []
        commands: list[str] = []
        for step in steps:
            cmd = step.cmd.replace("{python}", _quote_for_shell(_target_python(self._repo_root)))
            commands.append(cmd)
            cwd = self._repo_root / step.cwd if step.cwd else self._repo_root
            proc = subprocess.run(
                cmd, shell=True, cwd=str(cwd), check=False,
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            chunks.append(f"$ {cmd}\n{proc.stdout or ''}{proc.stderr or ''}")
            rc = proc.returncode
            if rc == PYTEST_NO_TESTS_COLLECTED and _is_pytest_command(shlex.split(cmd)):
                chunks.append(f"[gate] step matched nothing (exit 5), treated as pass: {cmd}\n")
                continue
            if rc != 0:
                output = "".join(chunks)
                self._write_log(name, output)
                return GateRun(
                    name=name, returncode=rc, output=output, applicable=True,
                    commands=tuple(commands), log_path=self._log_path(name),
                )
        output = "".join(chunks)
        self._write_log(name, output)
        return GateRun(
            name=name, returncode=0, output=output, applicable=True,
            commands=tuple(commands), log_path=self._log_path(name),
        )

    def _log_path(self, name: str) -> Path | None:
        return (self._log_dir / f"{name}-gate.log") if self._log_dir is not None else None

    def _write_log(self, name: str, text: str) -> None:
        if self._log_dir is None:
            # No log_dir configured -- echo to stdout so captured gate output
            # (the same combined stdout+stderr text that would otherwise be
            # written to <name>-gate.log) is still visible somewhere, rather
            # than silently discarded.
            print(text, end="")
            return
        self._log_dir.mkdir(parents=True, exist_ok=True)
        (self._log_dir / f"{name}-gate.log").write_text(text, encoding="utf-8")
