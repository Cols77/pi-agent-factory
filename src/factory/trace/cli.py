from __future__ import annotations

import argparse
import json
from pathlib import Path

from factory.trace.graph import build_graph, graph_to_dict


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
    pending = [g for g in graph.gaps if g.disposition == "pending"]
    lines.append("")
    lines.append(f"gaps: {len(graph.gaps)} ({len(pending)} pending)")
    for gap in graph.gaps:
        mark = {"pending": "!", "deferred": "~", "exempt": "-"}[gap.disposition]
        lines.append(f"  {mark} {gap.node_id:<24} {gap.kind:<18} {gap.detail}")
    return "\n".join(lines)


def _add_root(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project-root", default=Path("."), type=Path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="factory-trace")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_status = sub.add_parser("status")
    _add_root(p_status)

    p_graph = sub.add_parser("graph")
    _add_root(p_graph)
    p_graph.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)

    if args.cmd == "status":
        print(cmd_status(args.project_root))
    elif args.cmd == "graph":
        print(json.dumps(cmd_graph(args.project_root), indent=2))
    return 0
