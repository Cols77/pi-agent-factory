from __future__ import annotations

import warnings
from collections.abc import Callable, Iterable
from pathlib import Path

from factory.orchestrator.roles import ROLE_SCOPE
from factory.orchestrator.types import AgentRole
from substrate.agents.backend import (
    SUBAGENT_DEPTH_ENV,
    _CMDLINE_PROMPT_LIMIT,
    _CONTEXT_ERROR_MARKERS,
    _CONTEXT_STOP_REASONS,
    _DEFAULT_IDLE_TIMEOUT_S,
    _DEFAULT_LIVENESS_DIRS,
    _DEFAULT_TOTAL_TIMEOUT_S,
    _IDLE_GRACE_BREACHES,
    _JSON_START,
    _KILL_GRACE_STEP_S,
    _KILL_GRACE_TOTAL_S,
    _KILL_POLL_BUDGET,
    _LIVENESS_DEPTH,
    _MAX_OUTPUT_LINE_CAP_CHARS,
    _MAX_OUTPUT_RETAINED_CHARS,
    _MAX_OUTPUT_TOTAL_CHARS,
    _NC_FLAGS,
    _SIG_KILL,
    _SIG_TERM,
    _SPAWN_BACKOFF_S,
    _SPAWN_RETRIES,
    _SUBAGENT_DEPTH_LIMIT,
    _IdleKeeper,
    _assistant_text_blocks,
    _build_command,
    _child_reaped,
    _drain_lines,
    _extract_snippet,
    _has_json_events_without_text_field,
    _kill_process_tree,
    _output_truncated_note,
    _pid_is_alive,
    _probe_dir,
    _probe_file_heartbeat,
    _retain_line_capped,
    _retry_launch,
    _session_id_in_line,
    classify_interruption,
    parse_pi_json,
    parse_session_id,
)
from substrate.agents.backend import PiAgentBackend as _SubstratePiAgentBackend
from substrate.agents.model import AgentResult, InterruptionReason

# This module is a warning composition wrapper (T-030 / Coherence Increment
# 1B, Task 3): the neutral agent-subprocess backend now lives at
# substrate.agents.backend, with role-catalogue composition (ROLE_SCOPE, the
# AgentRole-typed public signature) supplied here. PiAgentBackend below keeps
# accepting role: AgentRole -- its public constructor/run() signature is
# unchanged for this release -- but internally constructs the substrate class
# with scope_for=lambda role: ROLE_SCOPE[AgentRole(role)]. Every helper,
# constant, and pure function below is re-exported unchanged from substrate so
# existing callers/tests of this module keep working.
warnings.warn(
    "factory.orchestrator.pi_backend is deprecated; import substrate.agents.backend "
    "and compose scope_for from factory.orchestrator.roles.ROLE_SCOPE",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "PiAgentBackend",
    "AgentResult",
    "InterruptionReason",
    "SUBAGENT_DEPTH_ENV",
    "_CMDLINE_PROMPT_LIMIT",
    "_CONTEXT_ERROR_MARKERS",
    "_CONTEXT_STOP_REASONS",
    "_DEFAULT_IDLE_TIMEOUT_S",
    "_DEFAULT_LIVENESS_DIRS",
    "_DEFAULT_TOTAL_TIMEOUT_S",
    "_IDLE_GRACE_BREACHES",
    "_JSON_START",
    "_KILL_GRACE_STEP_S",
    "_KILL_GRACE_TOTAL_S",
    "_KILL_POLL_BUDGET",
    "_LIVENESS_DEPTH",
    "_MAX_OUTPUT_LINE_CAP_CHARS",
    "_MAX_OUTPUT_RETAINED_CHARS",
    "_MAX_OUTPUT_TOTAL_CHARS",
    "_NC_FLAGS",
    "_SIG_KILL",
    "_SIG_TERM",
    "_SPAWN_BACKOFF_S",
    "_SPAWN_RETRIES",
    "_SUBAGENT_DEPTH_LIMIT",
    "_IdleKeeper",
    "_assistant_text_blocks",
    "_build_command",
    "_child_reaped",
    "_drain_lines",
    "_extract_snippet",
    "_has_json_events_without_text_field",
    "_kill_process_tree",
    "_output_truncated_note",
    "_pid_is_alive",
    "_probe_dir",
    "_probe_file_heartbeat",
    "_retain_line_capped",
    "_retry_launch",
    "_session_id_in_line",
    "classify_interruption",
    "parse_pi_json",
    "parse_session_id",
]


class PiAgentBackend:
    """Thin AgentRole-typed wrapper around substrate.agents.backend.PiAgentBackend.

    Role catalogues, prompts, and execution orchestration remain factory's:
    this class only translates an AgentRole to the plain-string role the
    substrate backend deals in, and injects ROLE_SCOPE as the scope_for
    lookup.
    """

    def __init__(
        self,
        repo_root: Path,
        extension_path: Path,
        provider: str | None = None,
        model: str | None = None,
        idle_timeout_s: float = _DEFAULT_IDLE_TIMEOUT_S,
        total_timeout_s: float = _DEFAULT_TOTAL_TIMEOUT_S,
        idle_grace: int = _IDLE_GRACE_BREACHES,
        liveness_root: Path | None = None,
        liveness_dirs: Iterable[str] = _DEFAULT_LIVENESS_DIRS,
        liveness_probe: Callable[[float], object] | None = None,
    ) -> None:
        self._impl = _SubstratePiAgentBackend(
            repo_root,
            extension_path,
            scope_for=lambda role: ROLE_SCOPE[AgentRole(role)],
            provider=provider,
            model=model,
            idle_timeout_s=idle_timeout_s,
            total_timeout_s=total_timeout_s,
            idle_grace=idle_grace,
            liveness_root=liveness_root,
            liveness_dirs=liveness_dirs,
            liveness_probe=liveness_probe,
        )

    def run(
        self,
        role: AgentRole,
        prompt: str,
        on_snippet: Callable[[str], None] | None = None,
        on_session_id: Callable[[str], None] | None = None,
    ) -> AgentResult:
        return self._impl.run(
            role.value,
            prompt,
            on_snippet=on_snippet,
            on_session_id=on_session_id,
        )
