"""Capture-stage verbs for the guided planning entrypoint.

``legal_actions_adapter`` *renders* the read-only projection; this module
*drives* the capture session. It exposes only the six verbs ``session.py``
actually implements, and validates every response against the contract in
``cli.py::_session_command`` before a host sees it.

Semantic work is deliberately absent here. Which question to ask, whether an
answer is adequate, and which resolution applies are host/model and human
decisions; this module transports them and refuses malformed traffic. It never
originates a planning decision and never mints consent (SR-044).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from coherence.planning.adapter_backend import (
    BackendError,
    invoke_backend,
    require_safe_run_id,
)

SESSION_VERBS = ("start", "resume", "status", "append", "propose-challenge", "resolve", "finalize")

_VERB_FIELDS: dict[str, tuple[str, ...]] = {
    "start": ("prompt",),
    "resume": (),
    "status": (),
    "append": ("answer_id", "question", "text", "source"),
    "propose-challenge": ("id", "kind", "claim", "rationale", "evidence_needed", "provenance"),
    "resolve": ("challenge_id", "resolution", "response", "provenance"),
    "finalize": ("status",),
}

#: The only states ``session.py::_project`` can produce. A payload claiming any
#: other state means backend drift; fail closed rather than let a host render
#: invented progress through stages that have no implementation.
_SESSION_STATES = frozenset({"capture", "intent_provisional", "blocked"})

_CHALLENGE_FIELDS = (
    "id",
    "kind",
    "claim",
    "rationale",
    "provenance",
    "evidence_needed",
    "status",
    "response",
    "response_provenance",
)


def build_session_command(project_root: Path, run_id: str, verb: str, **fields: str) -> list[str]:
    """Build the argv-only backend invocation for one session verb."""
    if verb not in _VERB_FIELDS:
        raise ValueError(f"unsupported planning session verb: {verb}")
    if verb == "propose-challenge":
        required = set(_VERB_FIELDS[verb])
        if set(fields) != required:
            raise ValueError("semantic challenge proposal must contain exactly its proposal fields")
        if any(not isinstance(fields[name], str) or not fields[name] for name in required):
            raise ValueError("semantic challenge proposal fields must be non-empty text")
        if not fields["provenance"].startswith("host:"):
            raise ValueError("semantic challenge proposal requires host provenance")
    command = [
        "uv",
        "run",
        "coherence",
        "plan",
        verb,
        "--project-root",
        str(project_root),
        "--run-id",
        run_id,
    ]
    for name in _VERB_FIELDS[verb]:
        command.append(f"--{name.replace('_', '-')}={fields[name]}")
    command.append("--json")
    return command


def parse_session_response(raw: str, run_id: str) -> dict[str, Any]:
    """Validate one session verb's JSON response for both outcomes.

    ``ok: true`` (the verb succeeded) and ``ok: false`` (it failed for a real
    reason the host must relay) are both returned. Anything malformed,
    run-id-mismatched, or off-contract raises ``ValueError``.
    """
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("invalid planning session response") from exc

    if (
        not isinstance(payload, dict)
        or type(payload.get("schema")) is not int
        or payload["schema"] != 1
        or payload.get("run_id") != run_id
        or not isinstance(payload.get("ok"), bool)
    ):
        raise ValueError("invalid planning session response")

    if payload["ok"] is False:
        if not isinstance(payload.get("error"), str) or not payload["error"]:
            raise ValueError("invalid planning session response")
        return payload

    if (
        payload.get("state") not in _SESSION_STATES
        or type(payload.get("next_sequence")) is not int
        or payload["next_sequence"] < 1
        or not isinstance(payload.get("journal_sha256"), str)
        or not payload["journal_sha256"]
        or not isinstance(payload.get("challenges"), list)
    ):
        raise ValueError("invalid planning session response")

    for item in payload["challenges"]:
        if not isinstance(item, dict) or not all(
            isinstance(item.get(field), str) for field in _CHALLENGE_FIELDS
        ):
            raise ValueError("invalid planning session response")
    return payload


def run_session_command(
    project_root: Path, run_id: str, verb: str, **fields: str
) -> dict[str, Any]:
    """Invoke one session verb and return its validated payload."""
    require_safe_run_id(run_id)
    try:
        command = build_session_command(project_root, run_id, verb, **fields)
    except ValueError as exc:
        raise BackendError(str(exc)) from exc
    _, stdout, stderr = invoke_backend(command, project_root)
    try:
        return parse_session_response(stdout, run_id)
    except ValueError as exc:
        detail = stderr.strip()
        if detail:
            raise BackendError(f"{exc}; backend stderr: {detail[:500]}") from exc
        raise BackendError(str(exc)) from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="coherence-plan-guided", allow_abbrev=False)
    sub = parser.add_subparsers(dest="verb", required=True)
    for verb in SESSION_VERBS:
        command = sub.add_parser(verb, allow_abbrev=False)
        command.add_argument("--run-id", required=True)
        command.add_argument("--project-root", default=".", type=Path)
        if verb == "start":
            command.add_argument("--prompt", required=True)
        elif verb == "append":
            command.add_argument("--answer-id", required=True)
            command.add_argument("--question", required=True)
            command.add_argument("--text", required=True)
            command.add_argument("--source", default="user")
        elif verb == "propose-challenge":
            command.add_argument("--id", required=True)
            command.add_argument("--kind", required=True)
            command.add_argument("--claim", required=True)
            command.add_argument("--rationale", required=True)
            command.add_argument("--evidence-needed", required=True)
            command.add_argument("--provenance", required=True)
        elif verb == "resolve":
            command.add_argument("--challenge-id", required=True)
            command.add_argument(
                "--resolution", required=True, choices=("resolve", "revise", "defer", "accept")
            )
            command.add_argument("--response", required=True)
            command.add_argument("--provenance", default="user")
        elif verb == "finalize":
            command.add_argument(
                "--status", required=True, choices=("provisional", "cancelled", "needs_user")
            )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Exit 0: the printed JSON is trustworthy -- read ``ok`` to decide what is next.

    Exit 1: nothing trustworthy was obtained. Exit 2: usage error.
    """
    try:
        args = _parser().parse_args(sys.argv[1:] if argv is None else argv)
    except SystemExit:
        return 2
    fields = {name: getattr(args, name) for name in _VERB_FIELDS[args.verb]}
    try:
        payload = run_session_command(Path(args.project_root), args.run_id, args.verb, **fields)
    except BackendError as exc:
        print(json.dumps({"schema": 1, "run_id": args.run_id, "ok": False, "error": str(exc)}, indent=2))
        return 1
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


__all__ = [
    "SESSION_VERBS",
    "build_session_command",
    "main",
    "parse_session_response",
    "run_session_command",
]


if __name__ == "__main__":
    raise SystemExit(main())
