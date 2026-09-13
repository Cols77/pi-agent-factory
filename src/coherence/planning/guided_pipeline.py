"""Compile-and-handoff verbs for the guided planning entrypoint.

Where ``guided_entrypoint`` drives intent capture, this module drives what
happens to authored artifacts afterwards: ``bootstrap`` (validate the
intent/spec/plan triple and, with ``--decompose``, generate ``tasks/T-NNN.md``
from the plan), ``check`` (structural parity and task metadata), ``review``,
explicit artifact manifest, cross-artifact evidence and human consent transport, planning gates,
and ``handoff``.

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

PIPELINE_VERBS = (
    "bootstrap", "check", "review", "write-artifact-manifest", "write-cross-artifact-review",
    "record-sr-consent", "run-planning-gates", "handoff",
)

_VERB_FIELDS: dict[str, tuple[str, ...]] = {
    "bootstrap": ("intent", "spec", "plan"),
    "check": ("intent", "spec", "plan"),
    "review": (),
    "write-artifact-manifest": ("artifacts_json",),
    "write-cross-artifact-review": ("tasks_json",),
    "record-sr-consent": (
        "sr_id", "requirement_sha256", "decision", "reviewer", "phrase", "reason",
    ),
    "run-planning-gates": (),
    "handoff": ("workflow",),
}
_OPTIONAL_FIELDS: dict[str, tuple[str, ...]] = {
    "write-cross-artifact-review": ("workflow",),
}


def build_pipeline_command(project_root: Path, run_id: str, verb: str, **fields: str) -> list[str]:
    """Build the argv-only backend invocation for one pipeline verb."""
    if verb not in _VERB_FIELDS:
        raise ValueError(f"unsupported planning pipeline verb: {verb}")
    required = set(_VERB_FIELDS[verb])
    allowed = required | set(_OPTIONAL_FIELDS.get(verb, ())) | ({"decompose"} if verb == "bootstrap" else set())
    if (set(fields) - allowed or required - set(fields)
            or any(not isinstance(value, str) or not value.strip() for value in fields.values())):
        raise BackendError("planning pipeline fields must be explicit non-empty text")
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
    for name in _OPTIONAL_FIELDS.get(verb, ()):
        if name in fields:
            command.append(f"--{name.replace('_', '-')}={fields[name]}")
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
    if (
        not isinstance(payload, dict)
        or type(payload.get("schema")) is not int
        or payload["schema"] != 1
        or payload.get("run_id") != run_id
    ):
        raise _malformed()
    return code, payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="coherence-plan-pipeline", allow_abbrev=False)
    sub = parser.add_subparsers(dest="verb", required=True)
    for verb in PIPELINE_VERBS:
        command = sub.add_parser(verb, allow_abbrev=False)
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
        if verb == "write-cross-artifact-review":
            command.add_argument("--workflow")
        if verb in ("write-artifact-manifest", "write-cross-artifact-review", "record-sr-consent"):
            for name in _VERB_FIELDS[verb]:
                command.add_argument(f"--{name.replace('_', '-')}", required=True)
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
    for name in _OPTIONAL_FIELDS.get(args.verb, ()):
        value = getattr(args, name)
        if value is not None:
            fields[name] = value
    if args.verb == "bootstrap":
        fields["decompose"] = "true" if args.decompose else "false"
    try:
        code, payload = run_pipeline_command(
            Path(args.project_root), args.run_id, args.verb, **fields
        )
    except BackendError as exc:
        print(json.dumps({"schema": 1, "run_id": args.run_id, "ok": False, "error": str(exc)}, indent=2))
        return 1
    print(json.dumps({"backend_exit_code": code, **payload}, indent=2, ensure_ascii=False))
    return 0


__all__ = ["PIPELINE_VERBS", "build_pipeline_command", "main", "run_pipeline_command"]


if __name__ == "__main__":
    raise SystemExit(main())
