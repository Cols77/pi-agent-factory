"""PreToolUse hook: `finalize` requires recorded review work, not a promise.

This gate enforces two *procedural* facts, both read straight from the run's
append-only journal:

1. an intent review ran and recorded its verdict (an `answer_captured` event
   whose `source` is `intent-review-agent`);
2. every `challenge_raised` has a matching `challenge_resolved`.

It deliberately does **not** evaluate whether the captured intent is any good.
That judgment belongs to the review agent and the human. What a hook can know --
and all it should claim -- is whether the required records exist. Gating on a
semantic guess (for example the keyword output of `detect_challenges` alone)
would produce false confidence, because that matcher misses any unsupported
claim phrased without its trigger words.

Detecting the finalize call itself is a hazard in its own right: the command
text is untrusted and can be phrased many equivalent ways. This module uses
`_shell_segments` to split the command into independently-run, quote-aware
segments and tokenizes each rather than substring-searching the raw text, so:

- a finalize call cannot ride along un-denied inside a compound command, a
  trailing shell comment, or behind a preceding `cd`/`pushd` that would make
  the resolved project root disagree with what the gate checked;
- an unrelated command that merely *mentions* the adapter and the word
  "finalize" in an inert argument (a commit message, an echo) is not
  mistaken for a finalize call;
- `--run-id`/`--project-root` are read using the *last* occurrence, mirroring
  argparse's `store` action -- the same value the real CLI will use -- so the
  gate and the backend can never disagree about which run is being finalized.

The run-id grammar is imported from `legal_actions_adapter.SAFE_RUN_ID`, the
single source of truth every other adapter already uses, rather than restated
here where it could silently drift.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from _shell_segments import segments as shell_segments
from coherence.planning.legal_actions_adapter import SAFE_RUN_ID

REVIEW_SOURCE = "intent-review-agent"

_ADAPTER_MODULE = "coherence.planning.guided_entrypoint"
_ADAPTER_SCRIPT_BASENAME = "guided_entrypoint.py"
_CD_LIKE = {"cd", "pushd"}

_UNPARSEABLE_REASON = (
    "This command could not be parsed to confirm the finalize call it appears to make "
    "(unbalanced quoting). Rewrite it as a single, quoting-clean invocation of "
    "`uv run python -m coherence.planning.guided_entrypoint finalize ...`."
)

_INLINE_EXEC_REASON = (
    "This runs coherence.planning.guided_entrypoint's finalize through inline Python (-c) "
    "rather than the sanctioned CLI form, which this gate cannot verify. Use `uv run python -m "
    "coherence.planning.guided_entrypoint finalize ...` instead."
)

_CD_AMBIGUOUS_REASON = (
    "A preceding `cd`/`pushd` in this command makes the project root this finalize call will "
    "actually run against ambiguous. Run finalize as its own command from the repository root, "
    "with an explicit --project-root, rather than chaining a directory change first."
)


def _program_token(tokens: list[str]) -> str | None:
    """The actually-invoked program: skip leading `VAR=value` assignments and
    a leading `uv run`."""
    index = 0
    while index < len(tokens) and _looks_like_assignment(tokens[index]):
        index += 1
    if (
        index < len(tokens)
        and tokens[index] == "uv"
        and index + 1 < len(tokens)
        and tokens[index + 1] == "run"
    ):
        index += 2
    return tokens[index] if index < len(tokens) else None


def _looks_like_assignment(token: str) -> bool:
    name, sep, _ = token.partition("=")
    return bool(sep) and (name[:1].isalpha() or name[:1] == "_") and name.replace("_", "").isalnum()


def _invokes_adapter_module(tokens: list[str]) -> bool:
    """True when `tokens` actually invoke the guided-entrypoint adapter, as
    the target of `-m` or as the script path being run -- never merely
    because its name appears somewhere in an argument."""
    for index, token in enumerate(tokens):
        if token == "-m" and index + 1 < len(tokens) and tokens[index + 1] == _ADAPTER_MODULE:
            return True
        basename = token.replace("\\", "/").rsplit("/", 1)[-1]
        if basename == _ADAPTER_SCRIPT_BASENAME:
            return True
    return False


def _last_flag_value(tokens: list[str], flag: str) -> str | None:
    """The value of the LAST `--flag value` / `--flag=value` in `tokens`,
    mirroring argparse's `store` action so this hook and the real CLI can
    never disagree on which value governs."""
    value: str | None = None
    prefix = f"{flag}="
    for index, token in enumerate(tokens):
        if token == flag and index + 1 < len(tokens):
            value = tokens[index + 1]
        elif token.startswith(prefix):
            value = token[len(prefix) :]
    return value


def _events(journal: Path) -> list[dict] | None:
    try:
        lines = journal.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return None
    events: list[dict] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            return None
        if isinstance(value, dict):
            events.append(value)
    return events


def _decide_finalize(project_root: Path, tokens: list[str]) -> str | None:
    """`tokens` is already known to be a finalize call. Return a deny reason,
    or None to allow it."""
    run_id = _last_flag_value(tokens, "--run-id")
    if run_id is None or SAFE_RUN_ID.fullmatch(run_id) is None:
        return f"finalize requires a --run-id matching {SAFE_RUN_ID.pattern}"

    root_value = _last_flag_value(tokens, "--project-root")
    root = project_root / root_value if root_value else project_root

    journal = root / ".factory" / "planning" / run_id / "capture" / "events.jsonl"
    events = _events(journal)
    if events is None:
        return (
            f"No readable capture journal for run {run_id}. Finalize is blocked until the "
            "run has been started and its capture recorded."
        )

    reviewed = any(
        event.get("kind") == "answer_captured"
        and (event.get("payload") or {}).get("source") == REVIEW_SOURCE
        for event in events
    )
    if not reviewed:
        return (
            f"Run {run_id} has no recorded intent review. Dispatch the review agent and record "
            f"its verdict with `append --source {REVIEW_SOURCE}` (record it even when the "
            "verdict is 'no findings'), then finalize."
        )

    raised = {
        (event.get("payload") or {}).get("id")
        for event in events
        if event.get("kind") == "challenge_raised"
    }
    resolved = {
        (event.get("payload") or {}).get("id")
        for event in events
        if event.get("kind") == "challenge_resolved"
    }
    outstanding = sorted(item for item in raised - resolved if item)
    if outstanding:
        return (
            "These challenges have no recorded human disposition: "
            f"{', '.join(outstanding)}. Each needs an explicit resolve/revise/defer/accept "
            "chosen by the human before finalize."
        )
    return None


def decide(project_root: Path, command: str) -> str | None:
    """Return a deny reason for a finalize `command`, or None to allow it.

    `cd_seen` is tracked across *every* segment, including ones that mention
    neither the adapter nor "finalize" -- a `cd` segment never mentions
    either, so a keyword prefilter before splitting into segments would
    silently stop noticing it."""
    parsed = shell_segments(command)
    if parsed is None:
        if "guided_entrypoint" in command and "finalize" in command:
            return _UNPARSEABLE_REASON
        return None

    cd_seen = False
    for tokens in parsed:
        if not tokens:
            continue

        program = _program_token(tokens)
        adapter_invoked = _invokes_adapter_module(tokens)
        is_finalize_call = adapter_invoked and "finalize" in tokens

        if not is_finalize_call:
            if program in ("python", "python3", "py") and "-c" in tokens:
                code_index = tokens.index("-c") + 1
                if any(
                    "guided_entrypoint" in token and "finalize" in token
                    for token in tokens[code_index:]
                ):
                    return _INLINE_EXEC_REASON
            if program in _CD_LIKE:
                cd_seen = True
            continue

        if cd_seen:
            return _CD_AMBIGUOUS_REASON

        reason = _decide_finalize(project_root, tokens)
        if reason is not None:
            return reason
    return None


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError, OSError):
        return 0
    if not isinstance(event, dict):
        return 0
    tool_input = event.get("tool_input")
    command = str((tool_input or {}).get("command", "") if isinstance(tool_input, dict) else "")
    reason = decide(Path(str(event.get("cwd") or ".")), command)
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
