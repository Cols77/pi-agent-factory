"""Metric ingestion and evidence helpers over simulation run bundles."""

from __future__ import annotations

import json
from pathlib import Path

from factory.simulation.registry import Run, load_runs, runs_for


def metric_values(run: Run, metrics_json: dict) -> dict[str, float]:
    """Return the run's metric map (id -> numeric value) from a parsed metrics.json."""
    out: dict[str, float] = {}
    for key, value in metrics_json.items():
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            out[key] = float(value)
    return out


def _manifest_metrics(run: Run) -> dict:
    """Read cumulative metrics.json for a run bundle, tolerant of a missing file."""
    path = run.path.parent / "metrics.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def metric_history(evidence_dir: Path, metric_id: str) -> list[dict]:
    """Ascending history of ``metric_id`` across runs, keyed {run, commit, value, ts}.

    Fundamental order: manifest ``recorded_ts`` then ``run_id`` (stable tiebreak), never mtime.
    """
    entries: list[dict] = []
    for run in load_runs(evidence_dir):
        metrics = metric_values(run, _manifest_metrics(run))
        if metric_id in metrics:
            entries.append(
                {
                    "run": run.run_id,
                    "commit": run.commit,
                    "value": metrics[metric_id],
                    "ts": run.recorded_ts,
                }
            )
    return sorted(entries, key=lambda e: (e["ts"] or "", e["run"]))


def latest_failure(evidence_dir: Path, feature: str) -> Run | None:
    """Most recent run for a feature whose result is not 'passed' (or empty)."""
    failures = [r for r in runs_for(evidence_dir, feature=feature) if r.result != "passed"]
    if not failures:
        return None
    return max(failures, key=lambda r: r.run_id)


def evidence_for_goal(evidence_dir: Path, goal_id: str) -> list[Run]:
    """Runs whose manifest lists ``goal_id`` (ascending by run id)."""
    return runs_for(evidence_dir, goal=goal_id)