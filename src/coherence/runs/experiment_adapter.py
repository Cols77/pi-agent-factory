"""Experiment source adapter.

Projects the durable simulation/experiment registry at the experiment level --
one :class:`~coherence.runs.model.RunStatusInput` per distinct native
``experiment`` id (``evidence/runs/*/manifest.json`` via
``coherence.simulation.registry``), with state derived from that experiment's
latest run. This is a distinct producer projection from the per-run
``simulation_run_status``: it surfaces experiments rather than individual runs.
Read-only; never synthesizes a raw artifact.
"""

from __future__ import annotations

from pathlib import Path

from coherence.runs.model import RunStatusInput
from coherence.simulation import registry as sim_registry


def _state_from_result(result: str | None) -> str:
    if result == "passed":
        return "passed"
    if result == "failed":
        return "failed"
    return "unknown"


def experiment_run_status(root: Path) -> list[RunStatusInput]:
    """Read every distinct experiment from the evidence registry."""
    runs = sim_registry.load_runs(root / "evidence")
    by_experiment: dict[str, list] = {}
    for run in runs:
        by_experiment.setdefault(run.experiment or run.run_id, []).append(run)
    rows: list[RunStatusInput] = []
    for experiment_id, experiment_runs in sorted(by_experiment.items()):
        latest = max(experiment_runs, key=lambda r: r.recorded_ts or r.run_id)
        rows.append(
            RunStatusInput(
                producer="experiment",
                run_id=experiment_id,
                state=_state_from_result(latest.result),
                observation_ref=f"experiment:{experiment_id}",
                resume_cmd=None,
                updated_at=latest.recorded_ts or "",
                requirement_ids=(),
            )
        )
    return rows