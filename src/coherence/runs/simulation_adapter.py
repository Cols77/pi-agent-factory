"""Simulation-run source adapter.

Projects the durable simulation registry (``evidence/runs/<run-id>/manifest.json``
loaded via ``coherence.simulation.registry.load_runs``) into unified
:class:`~coherence.runs.model.RunStatusInput` rows, preserving native identity,
result and -- uniquely among the adapters -- the native ``requirements`` list.
Read-only; never synthesizes a raw artifact.
"""

from __future__ import annotations

from pathlib import Path

from substrate.observations import Diagnostic

from coherence.runs.model import RunStatusInput
from coherence.simulation import registry as sim_registry


def _state_from_result(result: str | None, scope_errors: list[str]) -> str:
    if scope_errors:
        return "unknown"
    if result == "passed":
        return "passed"
    if result == "failed":
        return "failed"
    return "unknown"


def simulation_run_status(root: Path) -> list[RunStatusInput]:
    """Read every simulation run from the evidence registry as status inputs."""
    runs = sim_registry.load_runs(root / "evidence")
    rows: list[RunStatusInput] = []
    for run in runs:
        rows.append(
            RunStatusInput(
                producer="simulation",
                run_id=run.run_id,
                state=_state_from_result(run.result, run.scope_errors),
                observation_ref=f"run:{run.run_id}",
                resume_cmd=None,
                updated_at=run.recorded_ts or run.run_id,
                diagnostics=(
                    tuple(Diagnostic(code="SIM_RUN_SCOPE_ERROR", summary=e) for e in run.scope_errors)
                ),
                requirement_ids=tuple(run.requirements),
            )
        )
    return rows