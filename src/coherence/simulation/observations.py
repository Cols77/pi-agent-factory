"""Adapts native simulation-run bundles into ``simulation-run/v1`` envelopes.

``coherence.simulation.registry.Run`` is loaded from an
``evidence/runs/<RUN-ID>/manifest.json`` bundle (see
``coherence.simulation.registry.load_runs``). That manifest file is already
the run's authoritative raw output, so this adapter content-hashes the file
itself -- rather than re-serializing the ``Run`` dataclass -- into its own
``ArtifactRef``, per this increment's review amendment ("each content-hashes
raw output artifacts"). A missing manifest (``Run.scope_errors`` non-empty)
degrades the observation to outcome ``"invalid"`` instead of raising: a
malformed run bundle is not a trustworthy claim, but it is still an
observation worth recording.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from substrate.artifacts import ArtifactRef, ProducerRef, SnapshotInputRef
from substrate.freshness.fingerprint import sha256_bytes
from substrate.observations import Diagnostic, ObservationEnvelope, Outcome, PayloadRegistry

from coherence.simulation.registry import Run

__all__ = ["REGISTRY", "SIMULATION_RUN_SCHEMA", "simulation_run_observation"]

SIMULATION_RUN_SCHEMA = "simulation-run/v1"


def _manifest_artifact(run: Run, *, id: str, scope_refs: Sequence[str]) -> ArtifactRef | None:
    if not run.path.is_file():
        return None
    return ArtifactRef(
        schema=1,
        kind="simulation-manifest",
        ref=f"artifact:simulation-manifest:{id}",
        location=str(run.path),
        content_hash=sha256_bytes(run.path.read_bytes()),
        scope_refs=tuple(scope_refs),
        media_type="application/json",
    )


def _default_outcome(run: Run) -> Outcome:
    if run.scope_errors:
        return "invalid"
    if run.result == "passed":
        return "pass"
    if run.result == "failed":
        return "fail"
    return "unknown"


def _scope_error_diagnostics(run: Run) -> tuple[Diagnostic, ...]:
    return tuple(
        Diagnostic(code="SIMULATION_RUN_SCOPE_ERROR", summary=error)
        for error in run.scope_errors
    )


def _validate_simulation_run_facts(facts: Mapping[str, object]) -> None:
    run_id = facts.get("run_id")
    if not isinstance(run_id, str) or not run_id.strip():
        raise ValueError("simulation-run/v1 facts.run_id must be a nonblank string")
    if not isinstance(facts.get("experiment"), str):
        raise ValueError("simulation-run/v1 facts.experiment must be a string")
    for key in ("requirements", "goals"):
        value = facts.get(key)
        if not isinstance(value, (list, tuple)) or any(not isinstance(v, str) for v in value):
            raise ValueError(f"simulation-run/v1 facts.{key} must be a list of strings")
    for key in ("feature", "commit", "recorded_ts", "manifest"):
        value = facts.get(key)
        if value is not None and not isinstance(value, str):
            raise ValueError(f"simulation-run/v1 facts.{key} must be a string or null")
    if facts.get("result") not in (None, "passed", "failed"):
        raise ValueError("simulation-run/v1 facts.result must be 'passed', 'failed', or null")
    artifact_refs = facts.get("artifacts")
    if not isinstance(artifact_refs, (list, tuple)) or any(
        not isinstance(ref, str) or not ref.strip() for ref in artifact_refs
    ):
        raise ValueError("simulation-run/v1 facts.artifacts must be a list of ref strings")


REGISTRY = PayloadRegistry()
REGISTRY.register(SIMULATION_RUN_SCHEMA, _validate_simulation_run_facts)


def simulation_run_observation(
    run: Run,
    inputs: Sequence[SnapshotInputRef],
    artifacts: Sequence[ArtifactRef],
    *,
    id: str,
    producer: ProducerRef,
    observed_at: str,
    scope_refs: Sequence[str] = (),
    outcome: Outcome | None = None,
    diagnostics: Sequence[Diagnostic] = (),
) -> ObservationEnvelope:
    """Adapt a loaded ``Run`` into a ``simulation-run/v1`` envelope.

    ``outcome`` defaults from ``run.scope_errors``/``run.result``: a
    malformed bundle is ``"invalid"``, else pass/fail/unknown mirrors
    ``run.result``. Pass an explicit override for a claim the caller knows
    better than the stored manifest (e.g. an aborted run recorded as
    ``"interrupted"``).
    """
    manifest_ref = _manifest_artifact(run, id=id, scope_refs=scope_refs)
    all_artifacts = (*artifacts, manifest_ref) if manifest_ref is not None else tuple(artifacts)
    facts = {
        "schema": SIMULATION_RUN_SCHEMA,
        "run_id": run.run_id,
        "experiment": run.experiment,
        "feature": run.feature,
        "requirements": list(run.requirements),
        "goals": list(run.goals),
        "commit": run.commit,
        "result": run.result,
        "recorded_ts": run.recorded_ts,
        "artifacts": [a.ref for a in artifacts],
        "manifest": manifest_ref.ref if manifest_ref is not None else None,
    }
    envelope = ObservationEnvelope(
        schema=1,
        id=id,
        kind="simulation-run",
        producer=producer,
        observed_at=observed_at,
        scope_refs=tuple(scope_refs),
        inputs=tuple(inputs),
        outcome=outcome if outcome is not None else _default_outcome(run),
        facts=facts,
        diagnostics=(*_scope_error_diagnostics(run), *diagnostics),
        artifacts=all_artifacts,
    )
    return envelope.validate_for_gate(REGISTRY)
