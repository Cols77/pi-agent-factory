"""The single fail-closed call path from a host adapter to the Coherence CLI.

Every guided-planning adapter routes its subprocess work through this module so
the safety-critical rules exist once:

- a run id outside the shared safe grammar never reaches a subprocess;
- invocations are argv lists, never shell strings;
- the exit-code contract is interpreted in exactly one place. Exit codes 0 and 1
  both carry trustworthy JSON -- 1 means "blocked", "not ok", or "findings
  present", which is *data* the host must relay, not a crash. Any other exit
  code means stdout is untrustworthy and is refused even when it parses.

This module holds no planning authority: it starts nothing, decides nothing, and
knows nothing about what the payloads mean.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from coherence.planning.legal_actions_adapter import is_safe_run_id

#: Exit codes whose stdout the backend guarantees is a structured payload.
TRUSTED_EXIT_CODES = (0, 1)


class BackendError(RuntimeError):
    """A backend invocation could not be run, or its output cannot be trusted."""


def require_safe_run_id(run_id: str) -> None:
    """Raise unless `run_id` matches the shared safe run-id grammar."""
    if not is_safe_run_id(run_id):
        raise BackendError("run_id must match the safe run-id grammar")


def invoke_backend(command: list[str], project_root: Path) -> tuple[int, str]:
    """Run an argv-only backend command and return `(exit_code, stdout)`.

    Raises ``BackendError`` on a launch failure or an exit code outside
    ``TRUSTED_EXIT_CODES``; in the latter case stdout is discarded unread.
    """
    try:
        result = subprocess.run(
            command,
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
            shell=False,
        )
    except OSError as exc:
        raise BackendError(str(exc)) from exc

    if result.returncode not in TRUSTED_EXIT_CODES:
        raise BackendError((result.stderr or "backend exited unsuccessfully").strip())
    return result.returncode, result.stdout or ""


__all__ = ["TRUSTED_EXIT_CODES", "BackendError", "invoke_backend", "require_safe_run_id"]
