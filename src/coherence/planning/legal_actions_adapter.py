"""Host-neutral core for presenting Coherence's planning legal-actions projection.

This module is the single source of truth for the safety-critical logic shared
by every host-specific, read-only presentation adapter for
``coherence plan legal-actions`` (the Hermes plugin at
``.hermes/plugins/coherence-plan/plugin.py``, the final projection step of
Claude Code's ``.claude/commands/coherence-plan.md``, and any future host). It
owns:

- the safe run-id grammar, checked before a run id ever reaches a subprocess
  call;
- building the argv-only backend invocation (never a shell string);
- interpreting the backend's exit-code contract: exit 0 means "not blocked",
  exit 1 means "legitimately blocked" and still carries a structured reason on
  stdout (see ``coherence.planning.cli._session_command``), and any other
  exit code is a real failure whose stdout must never be trusted;
- validating the parsed JSON contract; and
- rendering an accepted projection to the fixed three-line text format.

Coherence remains the sole authority for planning state, hashes, gates,
DecisionFiles, consent, adoption, and the handoff. This module never starts,
resumes, or mutates a planning run -- it is read-only presentation logic,
factored out so that no host duplicates (and risks re-diverging) the
fail-closed handling it implements. See
``.hermes/plugins/coherence-plan/README.md``'s "Authority and boundaries"
section for the contract every caller of this module must preserve.

Read-only describes *this module*, not every host surface that uses it. Hermes's
``/coherence-plan`` card is read-only end to end. Claude Code's
``/coherence-plan`` drives a full guided planning run, but it reaches every
mutating verb through ``coherence.planning.guided_entrypoint`` (capture:
start/resume/status/append/resolve/finalize) and
``coherence.planning.guided_pipeline`` (bootstrap/check/review/handoff); this
module is only the projection renderer that workflow calls at the end.

Each host adapter owns only its own framing around this module: how it
receives the raw run-id text, and what usage message it shows for an unsafe
or missing run id. Everything after a run id is known to be safe belongs
here.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

#: Grammar for a safe run id: must start with an alphanumeric character and
#: contain only alphanumerics, ``.``, ``_``, or ``-`` -- no path separators,
#: whitespace, or shell metacharacters.
SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def is_safe_run_id(run_id: str) -> bool:
    """Return whether `run_id` matches the safe run-id grammar."""
    return bool(SAFE_RUN_ID.fullmatch(run_id))


def build_legal_actions_command(project_root: Path, run_id: str) -> list[str]:
    """Build the argv-only backend invocation. Never a shell string."""
    return [
        "uv",
        "run",
        "coherence",
        "plan",
        "legal-actions",
        "--project-root",
        str(project_root),
        "--run-id",
        run_id,
        "--json",
    ]


def parse_legal_actions_projection(raw: str, run_id: str) -> dict[str, Any]:
    """Parse and validate the backend's ``legal-actions --json`` contract.

    A missing, malformed, stale, contradictory, or automatically-starting
    projection raises ``ValueError`` rather than being guessed at.
    """
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("invalid planning legal-actions response") from exc

    if not isinstance(payload, dict):
        raise ValueError("invalid planning legal-actions response")
    if (
        type(payload.get("schema")) is not int
        or payload["schema"] not in {1, 2}
        or not isinstance(payload.get("run_id"), str)
        or payload["run_id"] != run_id
        or not isinstance(payload.get("blocked"), bool)
        or "reason" not in payload
        or not (payload["reason"] is None or isinstance(payload["reason"], str))
        or not isinstance(payload.get("legal_next_actions"), list)
        or len(payload["legal_next_actions"]) > 1
        or not all(isinstance(action, str) for action in payload["legal_next_actions"])
        or payload.get("starts_automatically") is not False
    ):
        raise ValueError("invalid planning legal-actions response")
    if payload["schema"] == 2:
        actions = payload["legal_next_actions"]
        registry = payload.get("action_registry")
        identity = payload.get("run_identity")
        if (
            not isinstance(payload.get("state"), str)
            or len(actions) > 1
            or not isinstance(registry, dict)
            or type(registry.get("schema")) is not int
            or registry["schema"] != 1
            or not isinstance(registry.get("legal_ids"), list)
            or not all(isinstance(action, str) for action in registry["legal_ids"])
            or len(set(registry["legal_ids"])) != len(registry["legal_ids"])
            or not isinstance(registry.get("registry_hash"), str)
            or registry["registry_hash"] != hashlib.sha256(
                "\n".join(registry["legal_ids"]).encode()
            ).hexdigest()
            or "run_identity" not in payload
            or (identity is not None and not isinstance(identity, dict))
            or (not payload["blocked"] and (
                not isinstance(identity, dict) or identity.get("run_id") != run_id
            ))
            or (not payload["blocked"] and (payload["reason"] is not None or len(actions) != 1))
            or (payload["blocked"] and (not isinstance(payload["reason"], str) or bool(actions)))
            or (actions and actions[0] not in registry["legal_ids"])
        ):
            raise ValueError("invalid planning legal-actions response")
        if isinstance(identity, dict) and (
            identity.get("run_id") != run_id
            or type(identity.get("next_sequence")) is not int
            or identity["next_sequence"] < 1
            or not isinstance(identity.get("journal_sha256"), str)
            or re.fullmatch(r"[0-9a-f]{64}", identity["journal_sha256"]) is None
        ):
            raise ValueError("invalid planning legal-actions response")
    return payload


def render_legal_actions_projection(payload: dict[str, Any]) -> str:
    """Render an accepted projection to the fixed three-line text format."""
    status = f"Planning blocked: {payload['reason'] or 'UNKNOWN'}" if payload["blocked"] else "Planning ready"
    actions = ", ".join(payload["legal_next_actions"]) or "none"
    return "\n".join(
        (
            status,
            f"Legal actions: {actions}",
            "Starts automatically: no",
        )
    )


def legal_actions_report(project_root: Path, run_id: str) -> str:
    """Invoke the backend and render its legal-actions projection as text.

    Callers MUST validate `run_id` with `is_safe_run_id` before calling this
    (each host adapter presents its own usage message for an unsafe or
    missing run id); this function still refuses to build a command for an
    unsafe run id, raising ``ValueError`` rather than running anything.

    Fails closed: a subprocess error, an exit code outside ``{0, 1}``, or a
    malformed payload all render as ``"planning blocked: ..."`` instead of
    guessing, and never trust stdout for a non-{0,1} exit code even if it
    happens to look like valid JSON.
    """
    if not is_safe_run_id(run_id):
        raise ValueError("run_id must match the safe run-id grammar")

    command = build_legal_actions_command(project_root, run_id)
    result: subprocess.CompletedProcess[str] | None = None
    try:
        result = subprocess.run(
            command,
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
            shell=False,
        )
        if result.returncode not in (0, 1):
            # Any other exit code is an unexpected/non-blocked failure: never
            # trust stdout for it, even if it happens to contain valid JSON.
            detail = (result.stderr or "backend exited unsuccessfully").strip()
            return f"planning blocked: {detail}"
        # Exit code 1 is the CLI's normal "planning is blocked" signal (see
        # coherence.planning.cli._session_command), not a backend failure --
        # the structured payload on stdout still carries the real reason.
        payload = parse_legal_actions_projection(result.stdout or "", run_id)
    except (OSError, ValueError) as exc:
        detail = (getattr(result, "stderr", "") or str(exc)).strip()
        return f"planning blocked: {detail}"
    return render_legal_actions_projection(payload)


def main(argv: list[str] | None = None) -> int:
    """Read-only CLI entry point for a host adapter to shell out to.

    Prints the same fixed three-line text (or a usage message) that every
    host adapter renders, using the current working directory as the
    project root. Exits 0 whether planning is ready or blocked -- the block
    reason is presentation content, not a process failure; a non-zero exit
    is reserved for a missing/unsafe run id.
    """
    args = sys.argv if argv is None else argv
    raw_run_id = args[1].strip() if len(args) == 2 else ""
    if not raw_run_id or not is_safe_run_id(raw_run_id):
        print("usage: coherence-plan-report <run-id>")
        return 2
    print(legal_actions_report(Path.cwd(), raw_run_id))
    return 0


__all__ = [
    "SAFE_RUN_ID",
    "build_legal_actions_command",
    "is_safe_run_id",
    "legal_actions_report",
    "main",
    "parse_legal_actions_projection",
    "render_legal_actions_projection",
]


if __name__ == "__main__":
    raise SystemExit(main())
