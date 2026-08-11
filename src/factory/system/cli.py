"""`python -m factory.system` CLI: `brief`, `matrix`, `timeline`, `story`,
`reverse`, `guide`, `scope`, and `coverage`.

JSON is emitted on stdout only when `--json` is passed; a human-readable
rendering is printed otherwise. Errors always go to stderr as a structured
JSON object, with a non-zero exit code, regardless of `--json`.

`guide` additionally accepts `--export <path>`, the single write path this
package has (design SS4.5). Without it, the guide is computed and printed,
never written -- guides are otherwise ephemeral.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from factory.system.coverage import bundle_coverage
from factory.system.guide import export_guide
from factory.system.models import to_dict
from factory.system.queries import (
    ScopeError,
    list_bundle_errors,
    list_scopes,
    parse_scope_ref,
    query_brief,
    query_guide,
    query_matrix,
    query_timeline,
)
from factory.system.reverse import query_reverse
from factory.system.story import query_story


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


def cmd_story(repo_root: Path, scope_raw: str) -> dict:
    scope = parse_scope_ref(scope_raw)
    return query_story(repo_root, scope)


def cmd_reverse(repo_root: Path, scope_raw: str) -> dict:
    scope = parse_scope_ref(scope_raw)
    return query_reverse(repo_root, scope)


def cmd_guide(repo_root: Path, scope_raw: str, export_raw: str | None) -> dict:
    scope = parse_scope_ref(scope_raw)
    result = query_guide(repo_root, scope)
    if export_raw is not None:
        written = export_guide(repo_root, scope, Path(export_raw))
        # Confirmation goes to stderr, never stdout: stdout is the guide
        # payload (JSON when --json, rendered text otherwise) and must stay
        # exactly that -- printing here would corrupt `--json` output for any
        # caller doing `json.loads(stdout)`. `written` is the resolved,
        # confined path (`_confine_export_path`'s output), which can differ
        # from the raw `--export` argument, so this is the one place the
        # user actually learns where the file landed (review round 1,
        # finding: `cmd_guide` previously discarded this return value).
        print(f"guide exported to: {written}", file=sys.stderr)
    return result


def cmd_coverage(repo_root: Path) -> dict:
    return to_dict(bundle_coverage(repo_root))


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
        lines.append("  ! degraded:")
        for reason in result["degraded_reasons"]:
            lines.append(f"    - {reason}")
    for event in result["events"]:
        when = event["at"] or f"sequence={event['sequence']}"
        lines.append(
            f"  [{when}] {event['actor']} {event['action']} {event['subject']['ref']} "
            f"({event['freshness']['state']})"
        )
    if not result["events"]:
        lines.append("  no recorded decisions")
    return "\n".join(lines)


def _render_story(result: dict) -> str:
    task = result["task"]
    lines = [
        f"scope: {result['scope']['ref']}",
        f"  task: {task['id']} ({task['status']}) {task['title']}",
    ]
    if result["degraded"]:
        lines.append("  ! degraded:")
        for reason in result["degraded_reasons"]:
            lines.append(f"    - {reason}")
    lines.append(
        "  requirements: " + (", ".join(result["requirements"]) if result["requirements"] else "none recorded")
    )
    if not result["runs"]:
        lines.append("  no recorded runs")
    for run in result["runs"]:
        when = run["started_at"] or "unknown start"
        lines.append(
            f"  [{when}] {run['source']} run {run['run_id']}: {run['outcome']} "
            f"({run['implementation']['kind']})"
        )
    return "\n".join(lines)


def _render_reverse(result: dict) -> str:
    lines = [f"scope: {result['scope']['ref']}"]
    if result["degraded"]:
        lines.append("  ! degraded:")
        for reason in result["degraded_reasons"]:
            lines.append(f"    - {reason}")
    if not result["paths"]:
        lines.append("  no recorded path from this file")
    for path in result["paths"]:
        task = path["task"]["id"] if path["task"] else "(unresolved)"
        reqs = ", ".join(path["requirements"]) if path["requirements"] else "none recorded"
        stops_at = f" [stops at: {path['stops_at']}]" if path["stops_at"] else ""
        lines.append(f"  run {path['run']['run_id']} -> task {task} -> {reqs}{stops_at}")
    return "\n".join(lines)


def _render_guide(result: dict) -> str:
    lines = [f"scope: {result['scope']['ref']}"]
    for section in result["sections"]:
        lines.append(f"  [{section['kind']}] ({section['freshness']['state']})")
        for line in section["text"].split("\n"):
            lines.append(f"    {line}")
    return "\n".join(lines)


def _render_coverage(result: dict) -> str:
    lines = [f"bundle coverage: {result['bundled']}/{result['total']} artifacts"]
    for kind in result["kinds"]:
        lines.append(f"  {kind['kind']:<6} {kind['bundled']}/{kind['total']}")
    if result["unbundled"]:
        lines.append(f"unbundled ({len(result['unbundled'])}):")
        lines.extend(f"  - {ref}" for ref in result["unbundled"])
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

    p_story = sub.add_parser("story", parents=[common])
    p_story.add_argument("--scope", required=True)

    p_reverse = sub.add_parser("reverse", parents=[common])
    p_reverse.add_argument("--scope", required=True)

    p_guide = sub.add_parser("guide", parents=[common])
    p_guide.add_argument("--scope", required=True)
    p_guide.add_argument("--export", default=None)

    sub.add_parser("scope", parents=[common])

    p_coverage = sub.add_parser("coverage", parents=[common])
    p_coverage.add_argument(
        "--gate",
        action="store_true",
        help="exit non-zero when any artifact belongs to no bundle",
    )
    p_coverage.add_argument(
        "--force",
        action="store_true",
        help="with --gate, report the failure but exit zero anyway",
    )

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
        elif args.cmd == "story":
            result = cmd_story(args.repo_root, args.scope)
            rendered = _render_story(result)
        elif args.cmd == "reverse":
            result = cmd_reverse(args.repo_root, args.scope)
            rendered = _render_reverse(result)
        elif args.cmd == "guide":
            result = cmd_guide(args.repo_root, args.scope, args.export)
            rendered = _render_guide(result)
        elif args.cmd == "coverage":
            result = cmd_coverage(args.repo_root)
            rendered = _render_coverage(result)
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

    # The gate runs after rendering so a failure still shows what failed.
    # `--force` is for manual invocation only: `.factory/factory.yaml` never
    # passes it, so a pipeline run cannot be silently forced.
    if args.cmd == "coverage" and args.gate and result["unbundled"]:
        if args.force:
            # stderr, not stdout: a `--json` consumer must not see this note
            # in the payload it parses.
            print(
                f"forced: suppressed {len(result['unbundled'])} unbundled artifact(s) listed above",
                file=sys.stderr,
            )
            return 0
        return 2
    return 0
