"""Experiment/run registry loaded from evidence/runs/** manifest bundles.

Simulation run bundles are the spec §20 shape: a `RUN-<ts>/manifest.json` under
`evidence/runs/`. The tolerant loader in ``factory.evidence.manifests`` turns a
malformed bundle into a dict the registry turns into a Run carrying
``scope_errors`` — one bad/renamed file degrades one run's chain, never the
engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from substrate.evidence.read import list_run_manifests


@dataclass(frozen=True)
class Run:
    run_id: str
    experiment: str
    feature: str | None
    requirements: list[str]
    goals: list[str]
    commit: str | None
    result: str | None
    path: Path
    scope_errors: list[str]
    recorded_ts: str | None = None


def load_runs(evidence_dir: Path) -> list[Run]:
    """Load every simulation run bundle under ``evidence_dir/runs``.

    Deterministic order: newest bundle first (run id / recorded timestamp).
    Malformed bundles degrade to a Run carrying scope_errors, never raise.
    """
    runs: list[Run] = []
    for manifest in list_run_manifests(evidence_dir):
        if "run" not in manifest:
            continue  # v1 orchestration manifest, not a simulation bundle
        scope_errors: list[str] = []
        experiment = manifest.get("experiment")
        if not isinstance(experiment, str):
            scope_errors.append("experiment: not a string")
            experiment = ""
        run_id = manifest.get("run", "")
        manifest_path = evidence_dir / "runs" / run_id / "manifest.json"
        if not manifest_path.exists():
            scope_errors.append(f"manifest file missing: {manifest_path}")
        runs.append(
            Run(
                run_id=run_id,
                experiment=experiment,
                feature=manifest.get("feature"),
                requirements=[
                    r for r in manifest.get("requirements", []) if isinstance(r, str)
                ],
                goals=[g for g in manifest.get("goals", []) if isinstance(g, str)],
                commit=manifest.get("commit"),
                result=manifest.get("result"),
                path=manifest_path,
                scope_errors=scope_errors,
                recorded_ts=manifest.get("recorded_ts"),
            )
        )
    return runs


def runs_for(
    evidence_dir: Path,
    *,
    feature: str | None = None,
    requirement: str | None = None,
    experiment: str | None = None,
    goal: str | None = None,
) -> list[Run]:
    """Filter simulation runs by one or more dimensions."""
    runs = load_runs(evidence_dir)
    if feature is not None:
        runs = [r for r in runs if r.feature == feature]
    if requirement is not None:
        runs = [r for r in runs if requirement in r.requirements]
    if experiment is not None:
        runs = [r for r in runs if r.experiment == experiment]
    if goal is not None:
        runs = [r for r in runs if goal in r.goals]
    return sorted(runs, key=lambda r: r.run_id)


def latest_run(evidence_dir: Path, feature: str) -> Run | None:
    """Most recent passing-capable run for a feature, by run id (deterministic)."""
    matches = runs_for(evidence_dir, feature=feature)
    if not matches:
        return None
    return max(matches, key=lambda r: r.run_id)

