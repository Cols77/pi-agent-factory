from __future__ import annotations

import argparse
import json
from pathlib import Path

from factory.freshness.model import FreshnessSeverity
from factory.preflight.checks import PreflightPhase, run_preflight


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="factory.preflight")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--task", default=None)
    parser.add_argument("--phase", choices=[item.value for item in PreflightPhase], default="start")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = run_preflight(Path(args.repo).resolve(), args.task, PreflightPhase(args.phase))
    payload = report.to_dict()
    if args.json:
        print(json.dumps(payload))
    else:
        if not report.issues:
            print("preflight passed")
        for issue in report.issues:
            print(f"{issue.severity.value}: {issue.code}: {issue.subject}: {issue.detail}")
    if any(item.severity is FreshnessSeverity.INTEGRITY for item in report.issues):
        return 3
    if any(item.severity is FreshnessSeverity.BLOCKING for item in report.issues):
        return 2
    return 0
