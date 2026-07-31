from __future__ import annotations

import argparse
import json
from pathlib import Path

from factory.validation.pipeline import validate_task_requirements
from factory.validation.report import write_validation_report


def cmd_validate(
    project_root: Path, *, full_sweep: bool, satisfies: list[str] | None = None
) -> tuple[dict, bool]:
    report, ok = validate_task_requirements(project_root, satisfies or [], full_sweep=full_sweep)
    write_validation_report(project_root / "validation" / "validation-report.json", report)
    return report, ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="factory-validate")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_run = sub.add_parser("run")
    p_run.add_argument("--project-root", default=Path("."), type=Path)
    p_run.add_argument("--all", action="store_true", help="full sweep (include periodic SRs)")
    p_run.add_argument("--satisfies", action="append", default=[], metavar="SR-###")
    args = parser.parse_args(argv)

    report, ok = cmd_validate(args.project_root, full_sweep=args.all, satisfies=args.satisfies)
    print(json.dumps(report, indent=2))
    return 0 if ok else 1
