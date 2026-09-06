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
import re
import sys
from pathlib import Path

from _shell_segments import program_basename, program_name, program_start
from _shell_segments import segments as shell_segments
from coherence.planning.legal_actions_adapter import SAFE_RUN_ID
from coherence.planning.paths import safe_resolve, safe_root

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
    "This reaches the coherence planning backend's finalize through inline Python (-c) "
    "rather than the sanctioned CLI form, which this gate cannot verify. Use `uv run python -m "
    "coherence.planning.guided_entrypoint finalize ...` instead."
)

_COHERENCE_MENTION = re.compile(r"\bcoherence\b")

_CD_AMBIGUOUS_REASON = (
    "A preceding `cd`/`pushd` in this command makes the project root this finalize call will "
    "actually run against ambiguous. Run finalize as its own command from the repository root, "
    "with an explicit --project-root, rather than chaining a directory change first."
)


def _adapter_invocation_end(tokens: list[str]) -> int | None:
    """Index of the token immediately *after* the guided-entrypoint adapter
    invocation, when the adapter is the actual program being run -- as the
    target of `-m`, or as the script path itself -- never merely because its
    name appears somewhere else in the segment (a grep pattern, a file
    argument to an unrelated command). `None` if this segment does not invoke
    it. Callers check whether the token at that index is the subcommand they
    care about, the same way argparse would see it."""
    start = program_start(tokens)
    if start is None:
        return None
    basename = program_basename(tokens[start])
    if basename == _ADAPTER_SCRIPT_BASENAME:
        # The adapter script is itself the invoked program (e.g. run directly
        # as an executable), with no `python` prefix of its own.
        return start + 1
    if basename in ("python", "python3", "py") and start + 1 < len(tokens):
        next_token = tokens[start + 1]
        if next_token == "-m" and start + 2 < len(tokens) and tokens[start + 2] == _ADAPTER_MODULE:
            return start + 3
        next_basename = program_basename(next_token)
        if next_basename == _ADAPTER_SCRIPT_BASENAME:
            return start + 2
    return None


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


def _payload(event: dict) -> dict:
    """`event["payload"]` if it is a dict, else `{}`.

    The journal parser (`_events`) only guarantees each *event* line is a
    JSON object; the `payload` value inside it is untrusted and can be
    anything JSON allows (a string, a number, a list, `true`, `null`) -- a
    plain `(event.get("payload") or {}).get(...)` crashes with an
    `AttributeError` on any non-dict *truthy* payload, which `main()` does
    not catch, turning an intended deny into a non-blocking hook error that
    Claude Code does not treat as a block. Every payload read must go
    through here instead."""
    payload = event.get("payload")
    return payload if isinstance(payload, dict) else {}


def _is_review(event: dict) -> bool:
    return _payload(event).get("source") == REVIEW_SOURCE


def _sequence(event: dict) -> int | None:
    value = event.get("sequence")
    return value if isinstance(value, int) else None


def _resolve_project_root(project_root: Path, root_value: str | None) -> Path | None:
    """Resolve `--project-root` the same way every other consumer of a
    project root in this codebase does (see `intent.py::_safe_project_root`,
    `bootstrap.py`, `cli.py::_safe_root`, ...): through `safe_root`/
    `safe_resolve`, never a bare `Path` join. A bare join lets an absolute
    `--project-root` value replace `project_root` outright, or a
    `..`-laden relative value escape it, so the gate would validate
    review/challenge state against a journal the command author fully
    controls rather than the real run's journal. `None` if the resolved
    root is unsafe (a symlink/junction component, or a path that does not
    stay under `project_root`)."""
    safe_project_root = safe_root(project_root)
    if safe_project_root is None:
        return None
    if not root_value:
        return safe_project_root
    return safe_resolve(safe_project_root, safe_project_root / root_value)


def _decide_finalize(project_root: Path, tokens: list[str]) -> str | None:
    """`tokens` is already known to be a finalize call. Return a deny reason,
    or None to allow it."""
    run_id = _last_flag_value(tokens, "--run-id")
    if run_id is None or SAFE_RUN_ID.fullmatch(run_id) is None:
        return f"finalize requires a --run-id matching {SAFE_RUN_ID.pattern}"

    root_value = _last_flag_value(tokens, "--project-root")
    root = _resolve_project_root(project_root, root_value)
    if root is None:
        return (
            f"--project-root {root_value!r} does not resolve to a safe path under the "
            "project root this hook is running in. Finalize is blocked until the project "
            "root can be verified."
        )

    journal = root / ".factory" / "planning" / run_id / "capture" / "events.jsonl"
    events = _events(journal)
    if events is None:
        return (
            f"No readable capture journal for run {run_id}. Finalize is blocked until the "
            "run has been started and its capture recorded."
        )

    answer_events = [event for event in events if event.get("kind") == "answer_captured"]
    review_sequences = [
        seq
        for seq in (_sequence(event) for event in answer_events if _is_review(event))
        if seq is not None
    ]
    if not review_sequences:
        return (
            f"Run {run_id} has no recorded intent review. Dispatch the review agent and record "
            f"its verdict with `append --source {REVIEW_SOURCE}` (record it even when the "
            "verdict is 'no findings'), then finalize."
        )

    latest_review = max(review_sequences)
    other_sequences = [
        seq
        for seq in (_sequence(event) for event in answer_events if not _is_review(event))
        if seq is not None
    ]
    if other_sequences and max(other_sequences) > latest_review:
        return (
            f"Run {run_id} has answers captured after the most recent recorded intent review "
            "(the review is not the most recent capture content). Dispatch the review agent "
            f"again and record its verdict with `append --source {REVIEW_SOURCE}` before finalize."
        )

    raised: set[str] = set()
    resolved: set[str] = set()
    for event in events:
        kind = event.get("kind")
        if kind not in ("challenge_raised", "challenge_resolved"):
            continue
        challenge_id = _payload(event).get("id")
        if not isinstance(challenge_id, str) or not challenge_id:
            # A challenge record this gate cannot identify is exactly the
            # kind of anomaly it must fail toward denying on, mirroring the
            # `_events() is None` fail-closed path -- an id-less challenge
            # can never be confirmed dispositioned, so it must never be
            # silently dropped from `raised`/`resolved` and treated as if it
            # were never raised at all.
            return (
                f"Run {run_id}'s capture journal has a {kind} event with a missing or "
                "malformed id. Finalize is blocked until the journal is corrected -- a "
                "challenge that cannot be identified cannot be confirmed as dispositioned."
            )
        (raised if kind == "challenge_raised" else resolved).add(challenge_id)
    outstanding = sorted(raised - resolved)
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
        if "finalize" in command and ("guided_entrypoint" in command or "coherence" in command):
            return _UNPARSEABLE_REASON
        return None

    cd_seen = False
    for tokens in parsed:
        if not tokens:
            continue

        program = program_name(tokens)
        end = _adapter_invocation_end(tokens)
        is_finalize_call = end is not None and end < len(tokens) and tokens[end] == "finalize"

        if not is_finalize_call:
            if program in ("python", "python3", "py") and "-c" in tokens:
                code_index = tokens.index("-c") + 1
                code = " ".join(tokens[code_index:])
                if "finalize" in code and _COHERENCE_MENTION.search(code):
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
    try:
        reason = decide(Path(str(event.get("cwd") or ".")), command)
    except Exception:
        # `decide` should never raise -- every payload read goes through
        # `_payload` and every project-root read through `_resolve_project_root`
        # precisely so a malformed journal or an unsafe path produces a deny
        # reason, not an exception. But per Claude Code's PreToolUse contract
        # only exit code 2 blocks a tool call; any other non-zero exit here
        # (an unhandled exception's traceback and exit 1) is non-blocking, so
        # an exception this fails to anticipate must still fail toward deny
        # rather than silently letting the call through.
        reason = (
            "This finalize call could not be safety-checked (the capture journal or "
            "the command could not be fully verified). Inspect the run's journal for "
            "malformed content, then retry."
        )
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
