"""Compile-and-handoff verbs for the guided planning entrypoint.

Where ``guided_entrypoint`` drives intent capture, this module drives what
happens to authored artifacts afterwards: ``bootstrap`` (validate the
intent/spec/plan triple and, with ``--decompose``, generate ``tasks/T-NNN.md``
from the plan), ``check`` (structural parity and task metadata), ``review``, and
``handoff``.

The division of labour matters. Authoring the spec and the plan is model work --
no backend command writes them, and none can. Deciding whether the decomposition
is *structurally* sound is backend work, and it is deterministic. This module
carries artifacts to the backend and carries findings back; it judges nothing.

Exit code 1 from these verbs means "findings present" or "blocked", which is a
result, not a failure -- callers receive the code alongside the payload so they
can tell the difference.
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

PIPELINE_VERBS = ("bootstrap", "check", "review", "handoff")

_VERB_FIELDS: dict[str, tuple[str, ...]] = {
    "bootstrap": ("intent", "spec", "plan"),
    "check": ("intent", "spec", "plan"),
    "review": (),
    "handoff": ("workflow",),
}


def build_pipeline_command(project_root: Path, run_id: str, verb: str, **fields: str) -> list[str]:
    """Build the argv-only backend invocation for one pipeline verb."""
    if verb not in _VERB_FIELDS:
        raise ValueError(f"unsupported planning pipeline verb: {verb}")
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
        command.extend([f"--{name}", fields[name]])
    if verb == "bootstrap" and fields.get("decompose") == "true":
        command.append("--decompose")
    command.append("--json")
    return command


def run_pipeline_command(
    project_root: Path, run_id: str, verb: str, **fields: str
) -> tuple[int, dict[str, Any]]:
    """Invoke one pipeline verb; return ``(exit_code, payload)``.

    Exit code 1 means the backend reported findings or a block -- real data the
    caller must act on, not a crash.
    """
    require_safe_run_id(run_id)
    code, stdout, stderr = invoke_backend(
        build_pipeline_command(project_root, run_id, verb, **fields), project_root
    )

    def _malformed() -> BackendError:
        detail = stderr.strip()
        if detail:
            return BackendError(f"invalid planning pipeline response; backend stderr: {detail[:500]}")
        return BackendError("invalid planning pipeline response")

    try:
        payload = json.loads(stdout)
    except (json.JSONDecodeError, TypeError) as exc:
        raise _malformed() from exc
    if not isinstance(payload, dict):
        raise _malformed()
    return code, payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="coherence-plan-pipeline")
    sub = parser.add_subparsers(dest="verb", required=True)
    for verb in PIPELINE_VERBS:
        command = sub.add_parser(verb)
        command.add_argument("--run-id", required=True)
        command.add_argument("--project-root", default=".", type=Path)
        if verb in ("bootstrap", "check"):
            command.add_argument("--intent", required=True)
            command.add_argument("--spec", required=True)
            command.add_argument("--plan", required=True)
        if verb == "bootstrap":
            command.add_argument("--decompose", action="store_true")
        if verb == "handoff":
            command.add_argument("--workflow", default="standard-development")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Exit 0: trustworthy payload printed. Exit 1: untrustworthy. Exit 2: usage.

    A payload reporting findings still exits 0 -- findings are content.
    """
    try:
        args = _parser().parse_args(sys.argv[1:] if argv is None else argv)
    except SystemExit:
        return 2
    fields = {name: getattr(args, name) for name in _VERB_FIELDS[args.verb]}
    if args.verb == "bootstrap":
        fields["decompose"] = "true" if args.decompose else "false"
    try:
        code, payload = run_pipeline_command(
            Path(args.project_root), args.run_id, args.verb, **fields
        )
    except BackendError as exc:
        print(json.dumps({"schema": 1, "ok": False, "error": str(exc)}, indent=2))
        return 1
    print(json.dumps({"backend_exit_code": code, **payload}, indent=2, ensure_ascii=False))
    return 0


__all__ = ["PIPELINE_VERBS", "build_pipeline_command", "main", "run_pipeline_command"]


if __name__ == "__main__":
    raise SystemExit(main())
