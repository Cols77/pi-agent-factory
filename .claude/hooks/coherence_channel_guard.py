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

A segment cannot simultaneously *be* the raw `coherence` program and *be*
`python -m <adapter>`: a single process has exactly one actually-invoked
program (`_shell_segments.program_token`, shared with
`coherence_finalize_gate.py` so the two hooks never disagree). A raw
`coherence plan <verb>` call is denied on that basis alone -- an unrelated
`-m <adapter>` token appearing later in the same segment does not corroborate
anything and is never treated as an exemption. Conversely, any `-m`/script
target that resolves under the `coherence`/`coherence.planning` namespace but
is not one of the four sanctioned adapter modules is denied by default,
rather than only recognizing one specific way of spelling the backend entry
point; and inline Python (`-c`) that mentions the `coherence` package is
denied for the same reason `coherence_finalize_gate.py` denies it for
`finalize` -- this hook cannot verify what such code actually calls.
"""

from __future__ import annotations

import json
import re
import sys

from _shell_segments import program_basename, program_name, program_start
from _shell_segments import segments as shell_segments

_ADAPTER_MODULES = (
    "coherence.planning.guided_entrypoint",
    "coherence.planning.guided_pipeline",
    "coherence.planning.legal_actions_adapter",
    "coherence.planning.artifact_navigator",
)

_VERB = re.compile(r"[a-z][a-z-]*")

_COHERENCE_MENTION = re.compile(r"\bcoherence\b")

_REASON = (
    "Direct `coherence plan {verb}` calls bypass the validated adapter "
    "(run-id grammar, argv-only invocation, exit-code contract, payload "
    "validation). Use `uv run python -m coherence.planning.guided_entrypoint "
    "{verb} ...` for capture verbs or `...guided_pipeline {verb} ...` for "
    "bootstrap/check/review/write-artifact-manifest/write-cross-artifact-review/record-sr-consent/"
    "run-planning-gates/handoff. Consent transport requires an explicit human decision."
)

_NAMESPACE_REASON = (
    "`{module}` is not one of the sanctioned adapter modules "
    "(coherence.planning.guided_entrypoint, guided_pipeline, "
    "legal_actions_adapter, artifact_navigator). A module under the "
    "coherence/coherence.planning namespace that is not explicitly "
    "allow-listed is refused by default, the same way an unrecognized "
    "`coherence` CLI spelling is."
)

_INLINE_EXEC_REASON = (
    "This runs inline Python (-c) that mentions the coherence package, which this "
    "hook cannot verify goes through a sanctioned adapter. Use `uv run python -m "
    "coherence.planning.<adapter> ...` instead."
)

_UNPARSEABLE_REASON = (
    "This command could not be parsed to confirm it avoids a direct "
    "`coherence plan` call (unbalanced quoting). Rewrite it as a single, "
    "quoting-clean invocation of the sanctioned adapter module."
)


def _backend_verb(tokens: list[str]) -> str | None:
    """The verb of a raw `coherence plan <verb>` invocation, when `coherence`
    is the actually-invoked program in `tokens` (never merely a token that
    appears somewhere in an unrelated argument, and matched by normalized
    basename so `/usr/local/bin/coherence` is recognized the same way as the
    bare `coherence` spelling), or `None`."""
    start = program_start(tokens)
    if start is None or program_basename(tokens[start]) != "coherence":
        return None
    if start + 2 < len(tokens) and tokens[start + 1] == "plan":
        verb = tokens[start + 2]
        if _VERB.fullmatch(verb):
            return verb
    return None


def _raw_module_target(tokens: list[str]) -> str | None:
    """The `-m` module target, when the actually-invoked program in `tokens`
    is a Python interpreter and `-m` immediately follows it, or `None`."""
    if program_name(tokens) not in ("python", "python3", "py"):
        return None
    for index, token in enumerate(tokens):
        if token == "-m" and index + 1 < len(tokens):
            return tokens[index + 1]
    return None


def _inline_exec_code(tokens: list[str]) -> str | None:
    """The code argument of a `-c` inline execution, when the actually-invoked
    program in `tokens` is a Python interpreter, or `None`."""
    if program_name(tokens) not in ("python", "python3", "py"):
        return None
    if "-c" not in tokens:
        return None
    code_index = tokens.index("-c") + 1
    return " ".join(tokens[code_index:])


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
        if verb is not None:
            return _REASON.format(verb=verb)

        module = _raw_module_target(tokens)
        if (
            module is not None
            and module not in _ADAPTER_MODULES
            and (module == "coherence" or module.startswith("coherence."))
        ):
            return _NAMESPACE_REASON.format(module=module)

        code = _inline_exec_code(tokens)
        if code is not None and _COHERENCE_MENTION.search(code):
            return _INLINE_EXEC_REASON
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
