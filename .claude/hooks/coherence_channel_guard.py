"""PreToolUse hook: keep planning traffic on the sanctioned adapter channel.

The adapters own run-id validation, argv-only invocation, exit-code
interpretation, and payload validation. A direct `uv run coherence plan ...`
call from the model bypasses all of it, so this hook denies those calls and
tells the model which entry point to use instead.

This is deliberately the *only* thing this hook decides. It checks the shape of
the call, never the merit of what is being planned -- a hook cannot judge
semantics, and pretending otherwise would trade real assurance for the
appearance of it.

The check is evaluated per shell segment (see `_shell_segments`, which splits
quote-aware on `;`, `&&`, `||`, `|`, `&`, and newline) so a raw backend call
cannot ride along un-denied inside a compound command or behind a trailing
comment, and per segment it is token-based rather than a substring search
over the segment text, so a raw backend call cannot be exempted just because
an adapter module's name happens to appear elsewhere in the same segment --
inside an unrelated argument such as a quoted prompt string.
"""

from __future__ import annotations

import json
import re
import sys

from _shell_segments import segments as shell_segments

_ADAPTER_MODULES = (
    "coherence.planning.guided_entrypoint",
    "coherence.planning.guided_pipeline",
    "coherence.planning.legal_actions_adapter",
    "coherence.planning.artifact_navigator",
)

_VERB = re.compile(r"[a-z][a-z-]*")

_REASON = (
    "Direct `coherence plan {verb}` calls bypass the validated adapter "
    "(run-id grammar, argv-only invocation, exit-code contract, payload "
    "validation). Use `uv run python -m coherence.planning.guided_entrypoint "
    "{verb} ...` for capture verbs or `...guided_pipeline {verb} ...` for "
    "bootstrap/check/review/handoff."
)

_UNPARSEABLE_REASON = (
    "This command could not be parsed to confirm it avoids a direct "
    "`coherence plan` call (unbalanced quoting). Rewrite it as a single, "
    "quoting-clean invocation of the sanctioned adapter module."
)


def _invokes_adapter(tokens: list[str]) -> bool:
    """True when `tokens` actually invoke one of the sanctioned adapters --
    as the target of `-m`, never merely as text appearing somewhere in an
    argument."""
    for index, token in enumerate(tokens):
        if token == "-m" and index + 1 < len(tokens) and tokens[index + 1] in _ADAPTER_MODULES:
            return True
    return False


def _backend_verb(tokens: list[str]) -> str | None:
    """The verb of a raw `coherence plan <verb>` invocation among `tokens`,
    matched positionally (real adjacent argv tokens), or `None`."""
    for index in range(len(tokens) - 2):
        if tokens[index] == "coherence" and tokens[index + 1] == "plan":
            verb = tokens[index + 2]
            if _VERB.fullmatch(verb):
                return verb
    return None


def decide(command: str) -> str | None:
    """Return a deny reason for `command`, or None to leave it alone."""
    if "coherence" not in command:
        return None

    parsed = shell_segments(command)
    if parsed is None:
        # `command` already contains "coherence" here (checked above); if it
        # also looks like it names the raw `plan` subcommand, fail toward
        # denying rather than silently trusting text we could not verify.
        return _UNPARSEABLE_REASON if "plan" in command else None

    for tokens in parsed:
        verb = _backend_verb(tokens)
        if verb is None:
            continue
        if _invokes_adapter(tokens):
            continue
        return _REASON.format(verb=verb)
    return None


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
