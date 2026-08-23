"""``python -m coherence.presentation`` CLI (Inc 5, Task 4).

Exposes the presentation router for headless/agent use: resolves a semantic
presentation intent to the chosen level + adapter + target and prints it as
JSON (the shape the pi-ext ``eng_present`` tool consumes). Never opens anything
itself — it reports the resolved action deterministically.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from coherence.navigate.queries import ScopeError
from coherence.presentation.level import parse_level
from coherence.presentation.router import present


def _print_error(exc: Exception) -> None:
    print(json.dumps({"error": str(exc), "kind": type(exc).__name__}), file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="factory-presentation")
    sub = parser.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--repo-root", default=Path("."), type=Path)
    common.add_argument("--json", action="store_true")

    p_present = sub.add_parser("present", parents=[common])
    p_present.add_argument("artifact")
    p_present.add_argument("--focus", default=None)
    p_present.add_argument(
        "--level",
        default=None,
        help="INSPECT, PRESENT or REVIEW (default: decided by policy — INSPECT with no facts)",
    )
    p_present.add_argument("--why-required", action="store_true", dest="why_required")

    args = parser.parse_args(argv)

    try:
        if args.cmd == "present":
            level = parse_level(args.level) if args.level is not None else None
            result = present(args.repo_root, args.artifact, args.focus, level=level)
            if args.why_required and "snapshot" not in result:
                from coherence.navigate.obligations import present_obligations

                result = {**result, **present_obligations(args.repo_root, args.artifact)}
        else:  # pragma: no cover - argparse enforces subcommand
            parser.error(f"unknown command: {args.cmd}")
            return 1
    except (FileNotFoundError, ValueError, ScopeError) as exc:
        _print_error(exc)
        return 1

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"level: {result['level']}")
        print(f"adapter: {result['adapter']}")
        print(f"target: {result['target']}")
        print(f"resolution: {result['resolution']}")
        if result["note"]:
            print(f"note: {result['note']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

