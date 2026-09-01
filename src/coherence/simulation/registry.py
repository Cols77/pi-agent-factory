"""Experiment/run registry loaded from evidence/runs/** manifest bundles.

Two manifest shapes live side by side under ``evidence/runs/`` and BOTH are
loaded here:

* spec §20 simulation bundles -- ``RUN-<ts>/manifest.json``, keyed ``run``,
  carrying ``experiment``/``feature``/``requirements``/``goals``;
* v1 orchestration manifests -- a flat ``<run_id>.json``, keyed ``run_id``
  with a ``task_id``, carrying ``result_commit``/``outcome``/``ended_at``.

Important 5 (review round 3): this reader used to ``continue`` past anything
without a ``run`` key, so the v1 shape was skipped. That is the shape of the
first evidence this repository ever recorded (T-6). It loads fine through
``list_run_manifests``, so ``register check`` saw it, but it never reached
the registry -- which is where ``navigate health`` builds its
``freshness_universe`` from. ``evidence_freshness`` therefore read 0/0: the
repository's first recorded evidence could not be reported stale, because it
was not in the universe staleness is measured over. Missing evidence must be
reported, never inferred (I-03), and "0/0" reported nothing at all.

The accommodation is in the reader, not in the recorded evidence: the
manifest on disk is untouched. Fields absent from the v1 shape are read from
their v1 equivalents where one exists (``commit`` <- ``result_commit``,
``result`` <- ``outcome``, ``recorded_ts`` <- ``ended_at``) and left empty
otherwise -- a v1 manifest declares no experiment, feature, requirement or
goal, and nothing here invents one.

The tolerant loader in ``substrate.evidence.read`` turns a malformed bundle
into a dict the registry turns into a Run carrying ``scope_errors`` -- one
bad/renamed file degrades one run's chain, never the engine.
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


def _manifest_path(evidence_dir: Path, run_id: str) -> Path | None:
    """Where this run's manifest actually is, or None.

    Both on-disk layouts are checked: the §20 bundle
    (``runs/<run_id>/manifest.json``) and the v1 flat file
    (``runs/<run_id>.json``). Reporting "manifest file missing" for a
    manifest that was just read out of the other layout would be a false
    scope error on real evidence.
    """
    bundle = evidence_dir / "runs" / run_id / "manifest.json"
    if bundle.exists():
        return bundle
    flat = evidence_dir / "runs" / f"{run_id}.json"
    if flat.exists():
        return flat
    return None


def load_runs(evidence_dir: Path) -> list[Run]:
    """Load every simulation run bundle under ``evidence_dir/runs``.

    Deterministic order: newest bundle first (run id / recorded timestamp).
    Malformed bundles degrade to a Run carrying scope_errors, never raise.
    """
    runs: list[Run] = []
    for manifest in list_run_manifests(evidence_dir):
        is_bundle = "run" in manifest
        run_id = manifest.get("run") if is_bundle else manifest.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            continue  # neither shape: nothing here identifies a run
        scope_errors: list[str] = []
        experiment = manifest.get("experiment")
        if not isinstance(experiment, str):
            # A §20 bundle must name its experiment; a v1 orchestration
            # manifest has no such field by design, so its absence is the
            # shape, not a defect.
            if is_bundle:
                scope_errors.append("experiment: not a string")
            experiment = ""
        manifest_path = _manifest_path(evidence_dir, run_id)
        if manifest_path is None:
            manifest_path = evidence_dir / "runs" / run_id / "manifest.json"
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
                commit=manifest.get("commit") or manifest.get("result_commit"),
                result=manifest.get("result") or manifest.get("outcome"),
                path=manifest_path,
                scope_errors=scope_errors,
                recorded_ts=manifest.get("recorded_ts") or manifest.get("ended_at"),
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

