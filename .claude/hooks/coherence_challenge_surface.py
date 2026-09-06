"""PostToolUse hook: make raised challenges impossible to quietly skip.

After an `append` or `resolve`, the backend returns the run's full challenge
list. Relying on the model to notice an `unresolved` entry buried in JSON is
exactly the kind of "it usually remembers" assumption this design avoids, so
this hook re-reads the payload and injects the outstanding items as context.

Surfacing only. The hook does not block and does not judge -- whether a
challenge matters, and how to dispose of it, stays with the human.
"""

from __future__ import annotations

import json
import sys
from typing import Any

_FIELDS = ("kind", "claim", "rationale", "evidence_needed")


def summarize(payload: dict[str, Any]) -> str | None:
    """Render unresolved challenges as context text, or None when there are none."""
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        return None
    challenges = payload.get("challenges")
    if not isinstance(challenges, list):
        return None

    lines: list[str] = []
    for item in challenges:
        if not isinstance(item, dict) or item.get("status") != "unresolved":
            continue
        detail = "; ".join(f"{field}: {item.get(field)}" for field in _FIELDS)
        lines.append(f"- {item.get('id')} -- {detail}")
    if not lines:
        return None
    return (
        "Coherence raised challenges that are still unresolved. Present each one to the human "
        "verbatim and ask them to choose resolve/revise/defer/accept plus a response. Do not "
        "choose on their behalf, and do not finalize until each is dispositioned:\n"
    ) + "\n".join(lines)


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError, OSError):
        return 0
    response = event.get("tool_response") or {}
    raw = response.get("stdout") if isinstance(response, dict) else None
    if not isinstance(raw, str):
        return 0
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return 0
    text = summarize(payload)
    if text is None:
        return 0
    print(
        json.dumps(
            {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": text}}
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
