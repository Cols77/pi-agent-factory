"""`python -m factory.system` CLI: `brief`, `matrix`, `timeline`, and `scope`.

`guide` (Task 5) is registered by a later task -- it is not stubbed here
(design SS5.1).

JSON is emitted on stdout only when `--json` is passed; a human-readable
rendering is printed otherwise. Errors always go to stderr as a structured
JSON object, with a non-zero exit code, regardless of `--json`.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from factory.system.models import to_dict
from factory.system.queries import (
    ScopeError,
    list_bundle_errors,
    list_scopes,
    parse_scope_ref,
    query_brief,
    query_matrix,
    query_timeline,
)


def _print_error(exc: Exception) -> None:
    print(json.dumps({"error": str(exc), "kind": type(exc).__name__}), file=sys.stderr)


def cmd_brief(repo_root: Path, scope_raw: str) -> dict:
    scope = parse_scope_ref(scope_raw)
    return query_brief(repo_root, scope)


def cmd_matrix(repo_root: Path, scope_raw: str) -> dict:
    scope = parse_scope_ref(scope_raw)
    return query_matrix(repo_root, scope)


def cmd_timeline(repo_root: Path, scope_raw: str) -> dict:
    scope = parse_scope_ref(scope_raw)
    return query_timeline(repo_root, scope)


def cmd_scope(repo_root: Path) -> dict:
    # A bundle that fails to load is not a scope, but it must still be
    # visible -- an operator who typos a bundle file gets feedback here
    # instead of the file just disappearing from the listing (design SS8).
    return {
        "scopes": [to_dict(s) for s in list_scopes(repo_root)],
        "errors": list_bundle_errors(repo_root),
    }


def _render_brief(result: dict) -> str:
    lines = [f"scope: {result['scope']['ref']}"]
    for claim in result["claims"]:
        lines.append(f"  [{claim['kind']}] ({claim['freshness']['state']}) {claim['text']}")
    return "\n".join(lines)


def _render_matrix(result: dict) -> str:
    lines = [f"scope: {result['scope']['ref']}"]
    for row in result["rows"]:
        lines.append(
            f"  {row['subject']['ref']}: {row['status']} "
            f"({row['freshness']['state']}) {row['summary']}"
        )
    return "\n".join(lines)


def _render_timeline(result: dict) -> str:
    lines = [f"scope: {result['scope']['ref']}"]
    if result["degraded"]:
        lines.append(
            "  ! degraded: some entries are missing a recorded actor, and/or some "
            "evidence could not be read -- see each event's freshness for detail"
        )
    for event in result["events"]:
        when = event["at"] or f"sequence={event['sequence']}"
        lines.append(
            f"  [{when}] {event['actor']} {event['action']} {event['subject']['ref']} "
            f"({event['freshness']['state']})"
        )
    if not result["events"]:
        lines.append("  no recorded decisions")
    return "\n".join(lines)


def _render_scope(result: dict) -> str:
    scopes = result["scopes"]
    lines = [s["ref"] for s in scopes] if scopes else ["no scopes declared"]
    for err in result["errors"]:
        lines.append(f"  ! bundle load failed: {err['bundle_id']} ({err['path']}): {err['error']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="factory-system")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # Shared parent so --repo-root/--json are accepted AFTER the subcommand,
    # matching factory.requirements.cli's convention.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--repo-root", default=Path("."), type=Path)
    common.add_argument("--json", action="store_true")

    p_brief = sub.add_parser("brief", parents=[common])
    p_brief.add_argument("--scope", required=True)

    p_matrix = sub.add_parser("matrix", parents=[common])
    p_matrix.add_argument("--scope", required=True)

    p_timeline = sub.add_parser("timeline", parents=[common])
    p_timeline.add_argument("--scope", required=True)

    sub.add_parser("scope", parents=[common])

    args = parser.parse_args(argv)

    try:
        if args.cmd == "brief":
            result = cmd_brief(args.repo_root, args.scope)
            rendered = _render_brief(result)
        elif args.cmd == "matrix":
            result = cmd_matrix(args.repo_root, args.scope)
            rendered = _render_matrix(result)
        elif args.cmd == "timeline":
            result = cmd_timeline(args.repo_root, args.scope)
            rendered = _render_timeline(result)
        else:
            result = cmd_scope(args.repo_root)
            rendered = _render_scope(result)
    except ScopeError as exc:
        _print_error(exc)
        return 1
    except (FileNotFoundError, ValueError) as exc:
        _print_error(exc)
        return 1

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(rendered)
    return 0
