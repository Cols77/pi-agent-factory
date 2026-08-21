from __future__ import annotations

import argparse
import json
from pathlib import Path

from coherence.doctor.context import format_context, gather_context
from coherence.doctor.write import emit_task, mint, promote


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="factory-doctor")
    sub = parser.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--project-root", default=Path("."), type=Path)

    p_context = sub.add_parser("context", parents=[common])
    p_context.add_argument("--json", action="store_true", dest="as_json")

    p_mint = sub.add_parser("mint", parents=[common])
    p_mint.add_argument("--source", required=True)
    p_mint.add_argument("--title", required=True)
    p_mint.add_argument("--statement", required=True)
    p_mint.add_argument("--domain", default="behavioral")

    p_promote = sub.add_parser("promote", parents=[common])
    p_promote.add_argument("id")
    p_promote.add_argument("--harness", required=True)
    p_promote.add_argument("--experiment", required=True)
    p_promote.add_argument("--metric", required=True)
    p_promote.add_argument("--assert", dest="assert_expr", required=True)
    p_promote.add_argument("--trials", type=int, default=1)
    p_promote.add_argument("--window-json", dest="window_json", default=None)

    p_task = sub.add_parser("task", parents=[common])
    p_task.add_argument("--satisfies", required=True)
    p_task.add_argument("--title", required=True)
    p_task.add_argument("--dod", action="append", required=True)
    p_task.add_argument("--body", default="")

    args = parser.parse_args(argv)

    try:
        if args.cmd == "context":
            ctx = gather_context(args.project_root)
            print(json.dumps(ctx, indent=2) if args.as_json else format_context(ctx))
        elif args.cmd == "mint":
            path = mint(args.project_root, args.source, args.title, args.statement, args.domain)
            print(f"minted {path.stem} at {path}")
        elif args.cmd == "promote":
            window = json.loads(args.window_json) if args.window_json else None
            path, implemented = promote(
                args.project_root,
                args.id,
                args.harness,
                args.experiment,
                args.metric,
                args.assert_expr,
                args.trials,
                window,
            )
            print(f"promoted {args.id} at {path}")
            state = (
                "implemented"
                if implemented
                else "NOT implemented in the declared scorers module"
            )
            print(f"metric {args.metric!r}: {state}")
        elif args.cmd == "task":
            path = emit_task(
                args.project_root, args.satisfies, args.title, args.dod, args.body
            )
            print(f"wrote {path.stem} at {path}")
    except ValueError as exc:
        print(str(exc))
        return 1
    return 0


__all__ = ["main"]

