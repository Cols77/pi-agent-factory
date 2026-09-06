"""PreToolUse hook: keep planning traffic on the sanctioned adapter channel.

The adapters own run-id validation, argv-only invocation, exit-code
interpretation, and payload validation. A direct `uv run coherence plan ...`
call from the model bypasses all of it, so this hook denies those calls and
tells the model which entry point to use instead.

This is deliberately the *only* thing this hook decides. It checks the shape of
the call, never the merit of what is being planned -- a hook cannot judge
semantics, and pretending otherwise would trade real assurance for the
appearance of it.
"""

from __future__ import annotations

import json
import re
import sys

#: Planning verbs that must be reached through an adapter module.
_BACKEND_CALL = re.compile(r"coherence\s+plan\s+([a-z-]+)")

_ADAPTER_MODULES = (
    "coherence.planning.guided_entrypoint",
    "coherence.planning.guided_pipeline",
    "coherence.planning.legal_actions_adapter",
    "coherence.planning.artifact_navigator",
)

_REASON = (
    "Direct `coherence plan {verb}` calls bypass the validated adapter "
    "(run-id grammar, argv-only invocation, exit-code contract, payload "
    "validation). Use `uv run python -m coherence.planning.guided_entrypoint "
    "{verb} ...` for capture verbs or `...guided_pipeline {verb} ...` for "
    "bootstrap/check/review/handoff."
)


def decide(command: str) -> str | None:
    """Return a deny reason for `command`, or None to leave it alone."""
    if "coherence" not in command:
        return None
    if any(module in command for module in _ADAPTER_MODULES):
        return None
    match = _BACKEND_CALL.search(command)
    if match is None:
        return None
    return _REASON.format(verb=match.group(1))


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError, OSError):
        return 0  # never block because our own parsing failed
    if not isinstance(event, dict):
        return 0
    tool_input = event.get("tool_input")
    command = str((tool_input or {}).get("command", "") if isinstance(tool_input, dict) else "")
    reason = decide(command)
    if reason is None:
        return 0
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
