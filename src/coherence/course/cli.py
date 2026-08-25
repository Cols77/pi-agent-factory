from __future__ import annotations

import argparse
import json
from pathlib import Path

from coherence.course.check import check_course


def _parser(prog: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=prog)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_check = sub.add_parser("check")
    p_check.add_argument("--project-root", default=Path("."), type=Path)
    p_check.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None, *, prog: str = "coherence-course") -> int:
    parser = _parser(prog)
    args = parser.parse_args(argv)

    if args.cmd == "check":
        report = check_course(args.project_root)
        if args.json:
            print(json.dumps(report.to_dict(), indent=2))
            return 0 if report.ok else 1
        lines = [f"{len(report.notes)} course note(s)"]
        lines.append(f"{len(report.unreached)} unreached known SR/spec: "
                     f"{', '.join(report.unreached) if report.unreached else '—'}")
        if report.non_referenceable:
            lines.append(
                "non-referenceable spec id(s) (no SPEC-... reference exists in the "
                "course grammar; not counted unreached): "
                f"{', '.join(report.non_referenceable)}"
            )
        for err in report.errors:
            lines.append(f"error: {err}")
        print("\n".join(lines))
        return 0 if report.ok else 1
    return 0


__all__ = ["main"]