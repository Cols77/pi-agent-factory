"""Metric ingestion and evidence helpers over simulation run bundles."""

from __future__ import annotations

import json
from pathlib import Path

from factory.simulation.registry import Run, load_runs, runs_for
from factory.goals.evaluator import GoalResult, evaluate
from factory.goals.lifecycle import can_transition
from factory.goals.registry import record


class GoalNotFoundError(ValueError):
    """An eng_evaluate_goal addressed a goal id no file declares."""

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


def _derive_one(goal, evidence_dir: Path) -> GoalResult | None:
    """Derive (without persisting) one goal's result from its latest run.

    A goal with no metric name, no ``source_experiment``, no matching run, or
    no measurable metric value yields ``None`` -- the goal is left untouched.
    Shared by the batch ``evaluate_goals_from_runs`` and the single-goal
    ``evaluate_goal_from_runs`` so both run the exact same Inc 3 evaluator.
    """
    if not goal.metric or not goal.metric.get("name"):
        return None
    experiment = goal.metric.get("source_experiment")
    if not experiment:
        return None
    runs = runs_for(evidence_dir, experiment=experiment)
    if not runs:
        return None
    latest = max(runs, key=lambda r: r.run_id)
    metrics = metric_values(latest, _manifest_metrics(latest))
    value = metrics.get(goal.metric["name"])
    if value is None:
        return None
    return evaluate(
        goal,
        value,
        run_id=latest.run_id,
        commit=latest.commit or "",
        metrics_path=latest.path.parent / "metrics.json",
    )


def evaluate_goals_from_runs(evidence_dir: Path, goals) -> list:
    """Automatically evaluate every given goal against its latest experiment run.

    Spec §14/§16/§17 pipeline: for each goal, take the latest run of its
    ``source_experiment``, read the goal's ``metric.name`` from that run's
    metrics.json, call ``factory.goals.evaluator.evaluate``, then persist via
    ``factory.goals.registry.record``. ``goals`` is the dict from
    ``factory.goals.registry.load_goals``. Returns the list of GoalResult in goal
    id order. A goal with no matching run (or no measurable metric value) is
    left untouched and produces no result.
    """
    results: list = []
    for goal in goals.values():
        result = _derive_one(goal, evidence_dir)
        if result is None:
            continue
        record(result, goal.path)
        results.append(result)
    return results


def evaluate_goal_from_runs(evidence_dir: Path, goals, goal_id: str) -> dict:
    """Evaluate ONE goal (the `eng_evaluate_goal` action) against its run.

    ``goals`` is the ``factory.goals.registry.load_goals`` dict. Returns a
    structured outcome dict rather than raising on a non-event, because "no
    measurable run" is a legitimate state for an action tool to report. The
    derived state is only persisted (via ``record``) when the goal's current
    lifecycle state legally permits the edge (spec §13 ``can_transition``); an
    illegal edge is reported without writing, keeping this the single goal-state
    write path behind policy.
    """
    if goal_id not in goals:
        raise GoalNotFoundError(f"no goal with id {goal_id!r}")
    goal = goals[goal_id]
    from_state = goal.state
    result = _derive_one(goal, evidence_dir)
    if result is None:
        return {
            "evaluated": False,
            "goal_id": goal_id,
            "state": from_state,
            "transition": None,
            "note": "no measurable run for this goal's metric/source_experiment; goal left untouched",
        }

    derived = {
        "state": result.state,
        "passed": result.passed,
        "value": result.value,
        "target": result.target_value,
        "operator": result.operator,
        "run": result.evidence.get("run"),
        "commit": result.evidence.get("commit"),
        "blocked_reason": result.blocked_reason,
    }
    if not can_transition(from_state, result.state):  # spec §13 lifecycle
        return {
            "evaluated": False,
            "goal_id": goal_id,
            "state": from_state,
            "transition": None,
            "derived": derived,
            "note": (
                f"derived state {result.state} is not a legal transition from "
                f"{from_state} (spec §13); move the goal to ACTIVE/EVALUATING "
                "first. No state written."
            ),
        }
    record(result, goal.path)
    return {
        "evaluated": True,
        "goal_id": goal_id,
        "transition": {"from": from_state, "to": result.state, "legal": True},
        "derived": derived,
    }