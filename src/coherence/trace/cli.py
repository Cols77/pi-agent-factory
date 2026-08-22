from __future__ import annotations

import argparse
import json
from pathlib import Path

from coherence.trace.graph import build_graph, graph_to_dict
from coherence.trace.propose import UnknownGapError, next_gap, proposal_to_dict
from coherence.trace.write import (
    link_satisfies,
    link_source_plan,
    link_spec,
    set_deferred,
    set_exempt,
    unlink_relation,
)


def cmd_graph(root: Path) -> dict:
    return graph_to_dict(build_graph(root))


def cmd_status(root: Path) -> str:
    graph = build_graph(root)
    health = graph.health
    lines = [
        f"traceability health: {health.percent}%  ({health.satisfied}/{health.expected} slots)"
    ]
    for cls in health.classes:
        suffix = f"  [{cls.exempt} exempt]" if cls.exempt else ""
        lines.append(f"  {cls.name:<14} {cls.satisfied}/{cls.expected}{suffix}")
    lines.append(f"  dangling refs  {health.dangling}")
    lines.append(f"  deferred       {health.deferred}")
    lines.append(f"  proposed       {health.proposed}")
    pending = [g for g in graph.gaps if g.disposition == "pending"]
    lines.append("")
    lines.append(f"gaps: {len(graph.gaps)} ({len(pending)} pending)")
    for gap in graph.gaps:
        mark = {"pending": "!", "deferred": "~", "exempt": "-"}[gap.disposition]
        lines.append(f"  {mark} {gap.node_id:<24} {gap.kind:<18} {gap.detail}")
    return "\n".join(lines)


def cmd_check(root: Path) -> tuple[str, int]:
    # Stateless by design: every gap and every disposition is re-derived from disk,
    # so the gate cannot be satisfied by a claim that the work was done. Spec 6.3.
    graph = build_graph(root)
    pending = [g for g in graph.gaps if g.disposition == "pending"]
    deferred = [g for g in graph.gaps if g.disposition == "deferred"]
    exempt = [g for g in graph.gaps if g.disposition == "exempt"]

    lines = [
        f"traceability health: {graph.health.percent}%",
        f"{len(pending)} pending, {len(deferred)} deferred, {len(exempt)} exempt",
    ]
    if pending:
        lines.append("")
        lines.append("undiscussed gaps (the gate fails on these):")
        for gap in pending:
            lines.append(f"  ! {gap.node_id:<24} {gap.kind:<18} {gap.detail}")
    if deferred:
        lines.append("")
        lines.append("deferred — discussed, still open:")
        for gap in deferred:
            lines.append(f"  ~ {gap.node_id:<24} {gap.kind:<18} {gap.detail}")
    return "\n".join(lines), (1 if pending else 0)


def _add_root(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project-root", default=Path("."), type=Path)


def _parser(prog: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=prog)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_status = sub.add_parser("status")
    _add_root(p_status)

    p_graph = sub.add_parser("graph")
    _add_root(p_graph)
    p_graph.add_argument("--json", action="store_true")

    p_link = sub.add_parser("link")
    _add_root(p_link)
    p_link.add_argument("node_id")
    p_link.add_argument("--satisfies", metavar="SR-###")
    p_link.add_argument("--spec", metavar="FILENAME")
    p_link.add_argument("--source-plan", metavar="FILENAME")

    p_unlink = sub.add_parser("unlink")
    _add_root(p_unlink)
    p_unlink.add_argument("node_id")
    unlink_group = p_unlink.add_mutually_exclusive_group(required=True)
    unlink_group.add_argument("--satisfies", metavar="SR-###")
    unlink_group.add_argument("--upstream", metavar="BR-###")

    p_next = sub.add_parser("next")
    _add_root(p_next)
    p_next.add_argument("--json", action="store_true")
    p_next.add_argument("--node-id", dest="node_id", default=None)

    p_check = sub.add_parser("check")
    _add_root(p_check)

    p_exempt = sub.add_parser("exempt")
    _add_root(p_exempt)
    p_exempt.add_argument("node_id")
    p_exempt.add_argument("--reason", required=True)

    p_defer = sub.add_parser("defer")
    _add_root(p_defer)
    p_defer.add_argument("node_id")
    p_defer.add_argument("--reason", required=True)

    return parser


def main(argv: list[str] | None = None, *, prog: str = "coherence-trace") -> int:
    parser = _parser(prog)

    args = parser.parse_args(argv)

    if args.cmd == "status":
        print(cmd_status(args.project_root))
    elif args.cmd == "graph":
        print(json.dumps(cmd_graph(args.project_root), indent=2))
    elif args.cmd == "next":
        try:
            proposal = next_gap(args.project_root, args.node_id)
        except UnknownGapError as exc:
            print(str(exc))
            return 1
        if proposal is None:
            print(json.dumps({"gap": None}) if args.json else "no pending gaps")
            return 0
        if args.json:
            print(json.dumps(proposal_to_dict(proposal), indent=2))
        else:
            print(
                f"{proposal.gap.node_id}  {proposal.gap.kind}  {proposal.gap.detail}"
                f"  ({proposal.pending_total} pending)"
            )
            for candidate in proposal.candidates:
                print(f"  {candidate.id:<12} {candidate.title}")
                print(f"    {candidate.summary}")
    elif args.cmd == "link":
        if not args.satisfies and not args.spec and not args.source_plan:
            parser.error("link requires --satisfies, --spec, or --source-plan")
        try:
            if args.satisfies:
                print(link_satisfies(args.project_root, args.node_id, args.satisfies))
            if args.spec:
                print(link_spec(args.project_root, args.node_id, args.spec))
            if args.source_plan:
                print(link_source_plan(args.project_root, args.node_id, args.source_plan))
        except (LookupError, ValueError) as exc:
            print(f"error: {exc}")
            return 2
    elif args.cmd == "unlink":
        try:
            unlink_relation(
                args.project_root,
                args.node_id,
                satisfies=args.satisfies,
                upstream=args.upstream,
            )
        except (LookupError, ValueError) as exc:
            print(f"error: {exc}")
            return 2
        relation = "satisfies" if args.satisfies is not None else "upstream"
        target = args.satisfies if args.satisfies is not None else args.upstream
        print(f"unlinked {relation} {target} from {args.node_id}")
    elif args.cmd == "exempt":
        try:
            print(set_exempt(args.project_root, args.node_id, args.reason))
        except (LookupError, ValueError) as exc:
            print(f"error: {exc}")
            return 2
    elif args.cmd == "defer":
        try:
            print(set_deferred(args.project_root, args.node_id, args.reason))
        except LookupError as exc:
            print(f"error: {exc}")
            return 2
    elif args.cmd == "check":
        text, code = cmd_check(args.project_root)
        print(text)
        return code
    return 0
