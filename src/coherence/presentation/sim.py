"""Simulation presentation adapter (spec §21, §22).

Resolves a ``RUN-<ts>`` (or ``run:<id>``) artifact to its durable evidence
bundle (spec §20) and returns it as the presentation target. The dedicated
simulation *viewer* (camera/trajectory/events UI) lands in Inc 6, so until then
this adapter honestly returns the run's evidence bundle + an ``Inc 6`` viewer
marker — it never claims a viewer that does not exist yet.
"""
from __future__ import annotations

from pathlib import Path

from coherence.simulation.registry import load_runs
from coherence.navigate._claims import evidence_dir


def _run_id_from(artifact: str) -> str:
    return artifact[4:] if artifact.lower().startswith("run:") else artifact


def resolve_sim(repo_root: Path, artifact: str, focus: str | None) -> dict:
    """Resolve a simulation run artifact to its evidence bundle or a downgrade."""
    run_id = _run_id_from(artifact)
    runs = load_runs(evidence_dir(repo_root))
    run = next((r for r in runs if r.run_id == run_id), None)
    if run is None:
        return {
            "target": None,
            "note": f"no simulation run with id {run_id!r} (spec §20 bundle not found).",
            "viewer": "Inc 6",
        }
    bundle_dir = Path(run.path).parent
    return {
        "target": str(bundle_dir),
        "manifest": str(run.path),
        "focus": focus,
        "note": (
            "simulation viewer lands in Inc 6; returning the run's durable "
            "evidence bundle (spec §20) as the presentation target."
        ),
        "viewer": "Inc 6",
    }

