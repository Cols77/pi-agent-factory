from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from factory.evidence.manifests import list_run_manifests, load_run_manifest

_RUN_ID = re.compile(r"^[A-Za-z0-9._-]+$")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="factory.evidence")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run")
    run.add_argument("run_id")
    run.add_argument("--repo", default=".")
    run.add_argument("--json", action="store_true")

    task = sub.add_parser("task")
    task.add_argument("task_id")
    task.add_argument("--repo", default=".")
    task.add_argument("--json", action="store_true")

    listing = sub.add_parser("list")
    listing.add_argument("--repo", default=".")
    listing.add_argument("--json", action="store_true")
    return parser


def _emit(payload: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload))
    else:
        runs = payload.get("runs")
        if isinstance(runs, list):
            for item in runs:
                print(f"{item['run_id']}  {item['task_id']}  {item['outcome']}")
        else:
            print(f"{payload['run_id']}  {payload['task_id']}  {payload['outcome']}")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    repo = Path(args.repo).resolve()
    evidence_dir = repo / "evidence"

    if args.command == "run":
        if not _RUN_ID.fullmatch(args.run_id):
            print(f"invalid run id: {args.run_id}", file=sys.stderr)
            return 2
        path = evidence_dir / "runs" / f"{args.run_id}.json"
        try:
            manifest = load_run_manifest(path)
        except FileNotFoundError:
            print(f"evidence run not found: {args.run_id}", file=sys.stderr)
            return 2
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"could not read evidence run {args.run_id}: {exc}", file=sys.stderr)
            return 2
        _emit(manifest, args.json)
        return 0

    task_id = args.task_id if args.command == "task" else None
    runs = list_run_manifests(evidence_dir, task_id)
    _emit({"runs": runs}, args.json)
    return 0
