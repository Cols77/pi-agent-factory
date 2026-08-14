"""`python -m factory.system` CLI: `brief`, `matrix`, `timeline`, `story`,
`reverse`, `guide`, `vcycle`, `scope`, and `coverage`.

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

from factory.system import bundles as bundles_module
from factory.system import health as health_module
from factory.system import labels as labels_module
from factory.system import vocabulary as vocabulary_module
from factory.system.bundles import list_bundles
from factory.system.coverage import bundle_coverage, member_target
from factory.system.guide import export_guide
from factory.system.models import to_dict
from factory.system.queries import (
    ScopeError,
    list_bundle_errors,
    list_scopes,
    parse_scope_ref,
    query_brief,
    query_feature_context,
    query_guide,
    query_matrix,
    query_timeline,
    query_traversal,
    query_vcycle,
)
from factory.system.reverse import query_reverse
from factory.system.story import query_story


def _print_error(exc: Exception) -> None:
    print(json.dumps({"error": str(exc), "kind": type(exc).__name__}), file=sys.stderr)


def cmd_brief(repo_root: Path, scope_raw: str) -> dict:
    scope = parse_scope_ref(scope_raw)
    if scope.kind == "feat":
        # The feature dossier is the `brief` for a `feat:` scope (Inc 1).
        return query_feature_context(repo_root, scope)
    return query_brief(repo_root, scope)


def cmd_vcycle(repo_root: Path, scope_raw: str) -> dict:
    scope = parse_scope_ref(scope_raw)
    return query_vcycle(repo_root, scope)


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


def cmd_bundle_check(repo_root: Path, draft_raw: str) -> dict:
    """Answer four deterministic questions about a draft bundle.

    Resolution, coverage delta, overlap with existing bundles, and
    id/filename consistency. It proposes nothing and writes nothing -- the
    draft is judged, not generated. `--draft -` reads stdin, in which case
    there is no filename to check the id against and `id_matches_filename`
    is None rather than False.
    """
    if draft_raw == "-":
        raw = json.loads(sys.stdin.read())
        id_matches_filename: bool | None = None
    else:
        draft_path = Path(draft_raw)
        raw = json.loads(draft_path.read_text(encoding="utf-8"))
        id_matches_filename = str(raw.get("id")) == draft_path.stem

    members = [str(m) for m in raw.get("members", [])]

    resolved: dict[str, Path] = {}
    unresolved: list[str] = []
    for ref in members:
        target = member_target(repo_root, ref)
        if target is None:
            unresolved.append(ref)
        else:
            resolved[ref] = target

    before = bundle_coverage(repo_root)
    already_claimed = {
        member_target(repo_root, m.ref)
        for bundle in list_bundles(repo_root / "bundles")
        for m in bundle.members
    }
    newly_claimed = {p for p in resolved.values() if p not in already_claimed}

    overlaps: list[dict] = []
    for ref, target in resolved.items():
        containing = [
            bundle.id
            for bundle in list_bundles(repo_root / "bundles")
            if any(member_target(repo_root, m.ref) == target for m in bundle.members)
        ]
        if containing:
            overlaps.append({"member": ref, "bundles": containing})

    return {
        "id": raw.get("id"),
        "label": raw.get("label"),
        "members_total": len(members),
        "members_resolved": len(resolved),
        "unresolved": unresolved,
        "coverage_before": {"bundled": before.bundled, "total": before.total},
        "coverage_after": {
            "bundled": before.bundled + len(newly_claimed),
            "total": before.total,
        },
        "overlaps": overlaps,
        "id_matches_filename": id_matches_filename,
    }


def cmd_health(repo_root: Path, recency_source=None) -> dict:
    """The composed health projection: the single landing document."""
    return health_module.query_health(repo_root, recency_source=recency_source)


def cmd_labels(repo_root: Path) -> dict:
    return labels_module.build_labels(repo_root)


def cmd_vocabulary() -> dict:
    return vocabulary_module.build_vocabulary()


def cmd_memberships(repo_root: Path, ref: str) -> dict:
    """Every bundle that declares `ref` as a member (deterministic order).

    A `/system` member-of affordance needs the answer on the command line too,
    for scripting and for the docs-server endpoint to reuse.
    """
    return {"ref": ref, "bundles": bundles_module.bundles_containing(repo_root, ref)}


def cmd_traversal(repo_root: Path, scope_raw: str) -> dict:
    """The core working-traversal chain for an sr:/bundle: anchor.

    requirement -> satisfying tasks -> design decisions -> changed files,
    walked over the real trace graph by `queries.query_traversal` (no parser,
    no synthesis).
    """
    return query_traversal(repo_root, parse_scope_ref(scope_raw))


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
    if "dossier" in result:
        return _render_dossier(result, lines)
    for claim in result["claims"]:
        lines.append(f"  [{claim['kind']}] ({claim['freshness']['state']}) {claim['text']}")
    return "\n".join(lines)


def _render_dossier(result: dict, lines: list[str]) -> str:
    dossier = result["dossier"]
    lines.append(f"  {dossier['id']} - {dossier['title']}")
    lines.append("  intent:")
    for intent_line in dossier["intent"].splitlines():
        lines.append(f"    {intent_line}" if intent_line else "")
    lines.append("  requirements:")
    for requirement in dossier["requirements"]:
        lines.append(f"    - {requirement['id']} ({requirement['kind']}) {requirement['title']}")
    lines.append("  design_records:")
    for record in dossier["design_records"]:
        lines.append(f"    - {record['id']} {record['title']}")
    lines.append("  implementation_files:")
    for path in dossier["implementation_files"]:
        lines.append(f"    - {path}")
    lines.append("  verification:")
    for status in dossier["verification"]:
        stale = " (stale)" if status["stale"] else ""
        lines.append(f"    - {status['id']}: {status['state']}{stale}")
    lines.append("  goals: " + (", ".join(dossier["goal_ids"]) if dossier["goal_ids"] else "none"))
    lines.append("  metrics: " + (", ".join(dossier["metric_ids"]) if dossier["metric_ids"] else "none"))
    lines.append("  recent_changes:")
    for change in dossier["recent_changes"]:
        lines.append(f"    - {change['commit']} {change['authored_at']} {change['subject']}")
    if not dossier["recent_changes"]:
        lines.append("    none recorded")
    return "\n".join(lines)


def _render_vcycle(result: dict) -> str:
    lines = [f"scope: {result['scope']['ref']}"]
    vcycle = result["vcycle"]
    lines.append(f"  anchor: {vcycle['anchor']}")
    lines.append("  definition:")
    for side in vcycle["definition"]:
        _render_vcycle_side(lines, side)
    lines.append("  verification:")
    for side in vcycle["verification"]:
        _render_vcycle_side(lines, side)
    lines.append("  goals: " + (", ".join(n["id"] for n in vcycle["goals"]) if vcycle["goals"] else "none"))
    lines.append("  metrics: " + (", ".join(n["id"] for n in vcycle["metrics"]) if vcycle["metrics"] else "none"))
    return "\n".join(lines)


def _render_vcycle_side(lines: list[str], side: dict) -> None:
    nodes = [node["id"] for node in side["nodes"]]
    if nodes:
        lines.append(f"    {side['label']}: {', '.join(nodes)}")
    else:
        lines.append(f"    {side['label']}: (empty)")


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


def _render_bundle_check(result: dict) -> str:
    before, after = result["coverage_before"], result["coverage_after"]
    lines = [
        f"draft: {result['id']} -- {result['label']}",
        f"  resolves       {result['members_resolved']}/{result['members_total']} members",
        f"  coverage       {before['bundled']}/{before['total']} -> "
        f"{after['bundled']}/{after['total']} bundled",
    ]
    for ref in result["unresolved"]:
        lines.append(f"  ! unresolved   {ref}")
    for overlap in result["overlaps"]:
        lines.append(f"  ~ also in      {overlap['member']} -> {', '.join(overlap['bundles'])}")
    if result["id_matches_filename"] is False:
        lines.append("  ! id does not match the draft filename (bundles must be named <id>.json)")
    return "\n".join(lines)


def _render_health(result: dict) -> str:
    h = result["health"]
    lines = [
        f"health: {h['satisfied']}/{h['expected']} SR ({h['percent']}%) "
        f"[dangling {h['dangling']}, deferred {h['deferred']}, proposed {h['proposed']}]"
    ]
    for cls in h["classes"]:
        suffix = f" (exempt {cls['exempt']})" if cls["exempt"] else ""
        lines.append(f"  {cls['name']}: {cls['satisfied']}/{cls['expected']}{suffix}")
    lines.append(f"bundles: {len(result['bundles'])}")
    for b in result["bundles"]:
        counts = b["readiness_counts"]
        lines.append(
            f"  {b['id']}: {b['readiness']} "
            f"({counts['sr_total']} SR, {counts['bound']} bound)"
        )
    unbundled_total = sum(len(v) for v in result["unbundled"].values())
    if unbundled_total:
        lines.append(f"unbundled ({unbundled_total}):")
        for refs in result["unbundled"].values():
            lines.extend(f"  - {ref}" for ref in refs)
    for reason in result["degraded"]:
        lines.append(f"  ! degraded: {reason}")
    return "\n".join(lines)


def _render_labels(result: dict) -> str:
    lines = [f"labels: {len(result['labels'])}"]
    for ref, entry in result["labels"].items():
        described = "described" if entry["description"] else "no description"
        lines.append(f"  {ref}: {entry['title']} [{described}]")
    return "\n".join(lines)


def _render_vocabulary(result: dict) -> str:
    terms = result["terms"]
    lines = [f"vocabulary: {len(terms)} terms"]
    for term, entry in terms.items():
        lines.append(f"  {term} [{entry['group']}]: {entry['gloss']}")
    return "\n".join(lines)


def _render_memberships(result: dict) -> str:
    if not result["bundles"]:
        return f"{result['ref']} in no bundle"
    return f"{result['ref']} in bundles: {', '.join(result['bundles'])}"


def _render_traversal(result: dict) -> str:
    lines = [f"requirement: {', '.join(result['requirement'])}"]
    lines.append("tasks: " + (", ".join(result["tasks"]) if result["tasks"] else "(none)"))
    lines.append("design: " + (", ".join(result["design"]) if result["design"] else "(none)"))
    lines.append("files: " + (", ".join(result["files"]) if result["files"] else "(none)"))
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

    p_traversal = sub.add_parser("traversal", parents=[common])
    p_traversal.add_argument("--scope", required=True)

    p_vcycle = sub.add_parser("vcycle", parents=[common])
    p_vcycle.add_argument("--scope", required=True)

    sub.add_parser("scope", parents=[common])

    sub.add_parser("health", parents=[common])

    sub.add_parser("labels", parents=[common])

    sub.add_parser("vocabulary", parents=[common])

    p_memberships = sub.add_parser("memberships", parents=[common])
    p_memberships.add_argument("ref")

    p_bundle = sub.add_parser("bundle")
    bundle_sub = p_bundle.add_subparsers(dest="bundle_cmd", required=True)
    p_bundle_check = bundle_sub.add_parser("check", parents=[common])
    p_bundle_check.add_argument("--draft", required=True, help="path to a draft bundle, or - for stdin")

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
        elif args.cmd == "vcycle":
            result = cmd_vcycle(args.repo_root, args.scope)
            rendered = _render_vcycle(result)
        elif args.cmd == "bundle":
            result = cmd_bundle_check(args.repo_root, args.draft)
            rendered = _render_bundle_check(result)
        elif args.cmd == "coverage":
            result = cmd_coverage(args.repo_root)
            rendered = _render_coverage(result)
        elif args.cmd == "health":
            result = cmd_health(args.repo_root)
            rendered = _render_health(result)
        elif args.cmd == "labels":
            result = cmd_labels(args.repo_root)
            rendered = _render_labels(result)
        elif args.cmd == "vocabulary":
            result = cmd_vocabulary()
            rendered = _render_vocabulary(result)
        elif args.cmd == "memberships":
            result = cmd_memberships(args.repo_root, args.ref)
            rendered = _render_memberships(result)
        elif args.cmd == "traversal":
            result = cmd_traversal(args.repo_root, args.scope)
            rendered = _render_traversal(result)
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
