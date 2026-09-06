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
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_FINALIZE = re.compile(r"coherence\.planning\.guided_entrypoint\s+finalize\b")
_RUN_ID = re.compile(r"--run-id[= ]+(\S+)")
_PROJECT_ROOT = re.compile(r"--project-root[= ]+(\S+)")
_SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

REVIEW_SOURCE = "intent-review-agent"


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


def decide(project_root: Path, command: str) -> str | None:
    """Return a deny reason for a finalize `command`, or None to allow it."""
    if _FINALIZE.search(command) is None:
        return None

    run_match = _RUN_ID.search(command)
    if run_match is None or _SAFE_RUN_ID.fullmatch(run_match.group(1)) is None:
        return "finalize requires a --run-id matching ^[A-Za-z0-9][A-Za-z0-9._-]*$"
    run_id = run_match.group(1)

    root_match = _PROJECT_ROOT.search(command)
    root = project_root / root_match.group(1) if root_match else project_root

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
