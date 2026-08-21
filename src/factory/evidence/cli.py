from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from substrate.evidence.read import list_run_manifests, load_run_manifest
from factory.evidence.records import build_historical_record, write_historical_record
from factory.evidence.reconcile import (
    blocks_evidence_gate,
    reconcile,
    repair_reconciliation,
)

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

    record = sub.add_parser("record")
    record.add_argument("task_id")
    record.add_argument("--repo", default=".")
    record.add_argument("--start", required=True)
    record.add_argument("--result", required=True)
    record.add_argument("--recorded-by", required=True)
    record.add_argument("--reason", required=True)
    record.add_argument("--json", action="store_true")

    listing = sub.add_parser("list")
    listing.add_argument("--repo", default=".")
    listing.add_argument("--json", action="store_true")

    reconciliation = sub.add_parser("reconcile")
    reconciliation.add_argument("--task", default=None)
    reconciliation.add_argument("--repo", default=".")
    reconciliation.add_argument("--json", action="store_true")
    reconciliation.add_argument("--repair", action="store_true")
    reconciliation.add_argument("--reason", default=None)
    reconciliation.add_argument("--gate", action="store_true")
    reconciliation.add_argument("--strict", action="store_true")
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

    if args.command == "reconcile":
        try:
            items = reconcile(repo, args.task)
            actions = (
                repair_reconciliation(repo, items, reason=args.reason)
                if args.repair
                else []
            )
            if actions:
                items = reconcile(repo, args.task)
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            print(f"could not reconcile evidence: {exc}", file=sys.stderr)
            return 2
        payload = {
            "items": [item.to_dict() for item in items],
            "repairs": actions,
        }
        if args.json:
            print(json.dumps(payload))
        else:
            for item in items:
                print(f"{item.kind.value}  {item.subject}  {item.detail}")
        if args.gate:
            pending = bool(items) if args.strict else any(blocks_evidence_gate(item) for item in items)
            return 1 if pending else 0
        return 1 if items else 0

    if args.command == "record":
        try:
            record = build_historical_record(
                repo,
                args.task_id,
                args.start,
                args.result,
                args.recorded_by,
                args.reason,
            )
            path = write_historical_record(evidence_dir, record)
            relative_path = path.relative_to(repo).as_posix()
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"could not record historical evidence: {exc}", file=sys.stderr)
            return 2
        payload = {
            "record_id": record["record_id"],
            "task_id": record["task_id"],
            "changed_files": record["changed_files"],
            "path": relative_path,
        }
        if args.json:
            print(json.dumps(payload))
        else:
            print(f"{payload['record_id']}  {payload['task_id']}  {payload['path']}")
        return 0

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
