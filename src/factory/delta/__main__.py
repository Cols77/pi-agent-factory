"""`python -m factory.delta` CLI (Inc 7 Task 3).

Subcommands:

* ``catchup --feature FEAT-...`` -- execute the `/catchup` command shim
  (compute the deterministic delta since the recorded checkpoint, upgrade
  the checkpoint to HEAD, route the REVIEW presentation). JSON on stdout
  with ``--json``, human rendering otherwise.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from factory.commands.catchup import run_catchup


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="factory-delta")
    sub = parser.add_subparsers(dest="cmd", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--repo", default=Path("."), type=Path)
    common.add_argument("--json", action="store_true")

    p_catchup = sub.add_parser("catchup", parents=[common])
    p_catchup.add_argument("--feature", required=True)
    p_catchup.add_argument(
        "--verify-understanding",
        action="store_true",
        help="offer the optional grill-understanding comprehension step (D8); the delta stays deterministic",
    )

    args = parser.parse_args(argv)
    if args.cmd == "catchup":
        result = run_catchup(
            args.repo,
            args.feature,
            verify_understanding=args.verify_understanding,
        )
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(_render(result))
        return 0
    return 1


def _render(result: dict) -> str:
    feature = result["feature"]
    if not result["reviewed"]:
        return f"catchup: {feature}\n  no review recorded yet for this feature"
    delta = result["delta"]
    lines = [
        f"catchup: {feature}",
        f"  since: {(result.get('since_commit') or '')[:8]}",
        "Since your last review:",
    ]
    for req in delta["requirements_changed"]:
        lines.append(f"  requirements changed:  {req}")
    for adr in delta["adrs_added"]:
        lines.append(f"  design decisions:      {adr} added")
    for pr in delta["prs_merged"]:
        lines.append(f"  implementation:        {pr}")
    for scenario in delta["scenarios_added"]:
        lines.append(f"  new experiments:       {scenario}")
    for goal in delta["goals_reached"]:
        lines.append(f"  goals reached:         {goal}")
    for goal in delta["goals_regressed"]:
        lines.append(f"  goals regressed:       {goal}")
    for metric in delta["metric_changes"]:
        from_v = metric["from"]
        to_v = metric["to"]
        arrow = f"{from_v} -> {to_v}" if from_v is not None else f"{to_v} (no prior value)"
        lines.append(f"  metrics:               {metric['metric']} {arrow}")
    for item in delta["new_open_items"]:
        lines.append(f"  new open items:        {item}")
    if len(lines) == 3:
        lines.append("  no changes since your last review")
    presentation = result.get("presentation", {})
    if presentation.get("target"):
        lines.append(f"  presented: {presentation['target']} ({presentation.get('level', '')})")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
