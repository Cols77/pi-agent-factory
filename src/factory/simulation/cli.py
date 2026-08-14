"""`factory.simulation` command-line interface.

Additive on v1: a new `python -m factory.simulation` entry model over the same
argparse-subparser pattern `factory.goals` uses. Subcommands:

- `runs`: list simulation run bundles.
- `sensitivity`: compare enabled vs disabled evidence (patch-reversal, brief
  §5.2) and emit a SENSITIVE / INSENSITIVE verdict per monitored metric.

Determinism: runs order by run id / recorded timestamp, never by mtime.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from factory.simulation import evidence as sim_evidence
from factory.simulation import registry as sim_registry
from factory.simulation.sensitivity import (
    InsensitiveError,
    evaluate_sensitivity,
    sensitivity_verdict,
)


def _emit(payload: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        for key, value in payload.items():
            print(f"{key}: {value}")


def _evidence_dir(repo_root: Path) -> Path:
    return repo_root / "evidence"


def _runs(repo_root: Path, args) -> int:
    runs = sim_registry.load_runs(_evidence_dir(repo_root))
    payload = {
        "runs": [
            {
                "run": r.run_id,
                "experiment": r.experiment,
                "feature": r.feature,
                "result": r.result,
                "goals": r.goals,
            }
            for r in runs
        ]
    }
    _emit(payload, args.json)
    return 0


def _sensitivity(repo_root: Path, args) -> int:
    """Compare enabled vs disabled evidence on the same monitored keys."""
    evidence_dir = _evidence_dir(repo_root)
    enabled = sim_evidence.metric_values(
        sim_registry.latest_run(evidence_dir, args.feature),
        _load_metrics(evidence_dir, args.enabled_run),
    ) if args.enabled_run else {}

    keys = args.keys
    tol = args.tol
    result = evaluate_sensitivity(
        enabled,
        _load_metrics(evidence_dir, args.disabled_run),
        keys=keys,
        tol=tol,
    )
    try:
        verdict = sensitivity_verdict(result, block_insensitive=args.block_insensitive)
    except InsensitiveError as exc:
        _emit({"verdict": "INSENSITIVE", "error": str(exc)}, args.json)
        return 2 if args.block_insensitive else 0
    _emit({"verdict": verdict, "deltas": result.deltas}, args.json)
    return 0


def _load_metrics(evidence_dir: Path, run_id: str | None) -> dict:
    if not run_id:
        return {}
    for run in sim_registry.load_runs(evidence_dir):
        if run.run_id == run_id:
            return sim_evidence.metric_values(
                run, sim_evidence._manifest_metrics(run)
            )
    return {}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="factory.simulation")
    sub = parser.add_subparsers(dest="command", required=True)

    runs = sub.add_parser("runs", help="list simulation run bundles")
    runs.add_argument("repo_root", type=Path)
    runs.add_argument("--json", action="store_true")
    runs.set_defaults(func=_runs)

    sens = sub.add_parser("sensitivity", help="patch-reversal evidence check (brief §5.2)")
    sens.add_argument("repo_root", type=Path)
    sens.add_argument("--enabled-run", default=None, help="run id of the enabled evidence")
    sens.add_argument("--disabled-run", required=True, help="run id of the disabled evidence")
    sens.add_argument("--feature", default="FEAT-NAV-017", help="feature whose runs to use")
    sens.add_argument("--keys", nargs="+", default=["reacquisition_rate"],
                      help="metric keys to monitor")
    sens.add_argument("--tol", type=float, default=0.2, help="degradation threshold")
    sens.add_argument("--block-insensitive", action="store_true",
                      help="exit non-zero when evidence is INSENSITIVE")
    sens.add_argument("--json", action="store_true")
    sens.set_defaults(func=_sensitivity)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    return args.func(args.repo_root, args)
