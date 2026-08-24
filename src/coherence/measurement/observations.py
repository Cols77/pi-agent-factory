"""Adapts native measurement/test-execution results into observation envelopes.

``coherence.measurement`` owns two native result shapes and their facts
schemas, both built from the same ``HarnessResult``/``TrialResult`` pair
(see ``coherence.measurement.harness``):

* ``measurement/v1`` -- a trial-scored experiment (frame-trace source or a
  live Playwright e2e run): a continuous ``metric_value`` over N trials.
* ``test-run/v1`` -- a pytest-selection harness run
  (``SimTestbenchHarness._run_pytest``; this is Increment 1's own worked
  example at ``docs/superpowers/specs/2026-08-20-coherence-agentic-io-design.md``
  section 4.2): collected/passed/failed test counts, no continuous metric.

The caller picks the adapter matching how the trials were produced. Raw
harness output (``HarnessResult.raw``) is never embedded in facts -- it is
content-hashed into its own ``ArtifactRef`` and only its ``ref`` is carried
in facts, per design decision AIO-4 and this increment's review amendment
("each content-hashes raw output artifacts").
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json

from substrate.artifacts import ArtifactRef, ProducerRef, SnapshotInputRef
from substrate.freshness.fingerprint import sha256_bytes
from substrate.observations import Diagnostic, ObservationEnvelope, Outcome, PayloadRegistry

from coherence.measurement.harness import HarnessResult

__all__ = [
    "MEASUREMENT_SCHEMA",
    "REGISTRY",
    "TEST_RUN_SCHEMA",
    "measurement_observation",
    "test_run_observation",
]

MEASUREMENT_SCHEMA = "measurement/v1"
TEST_RUN_SCHEMA = "test-run/v1"


def _raw_artifact(raw: Mapping[str, object], *, id: str, scope_refs: Sequence[str]) -> ArtifactRef:
    """Content-hash ``HarnessResult.raw`` into its own artifact reference.

    The payload is not written to disk here -- a harness that already wrote a
    file (JUnit XML, a Playwright JSON report) passes that file's own
    ``ArtifactRef`` through the ``artifacts`` parameter below; this reference
    exists so the exact raw dict a result carried is always independently
    addressable by content hash, never folded into ``facts``.
    """
    payload = json.dumps(dict(raw), sort_keys=True, separators=(",", ":"), default=str).encode(
        "utf-8"
    )
    return ArtifactRef(
        schema=1,
        kind="measurement-raw",
        ref=f"artifact:measurement-raw:{id}",
        location=f"inline:measurement-raw:{id}",
        content_hash=sha256_bytes(payload),
        scope_refs=tuple(scope_refs),
        media_type="application/json",
    )


def _resolve_outcome(result: HarnessResult, outcome: Outcome | None) -> Outcome:
    if outcome is not None:
        return outcome
    return "pass" if result.passed else "fail"


def _trial_facts(result: HarnessResult) -> list[dict[str, object]]:
    return [{"seed": t.seed, "passed": t.passed, "detail": t.detail} for t in result.trials]


def _validate_measurement_facts(facts: Mapping[str, object]) -> None:
    metric_value = facts.get("metric_value")
    if isinstance(metric_value, bool) or not isinstance(metric_value, (int, float)):
        raise ValueError("measurement/v1 facts.metric_value must be a number")
    if not isinstance(facts.get("passed"), bool):
        raise ValueError("measurement/v1 facts.passed must be a bool")
    trials = facts.get("trials")
    if not isinstance(trials, (list, tuple)):
        raise ValueError("measurement/v1 facts.trials must be a list")
    for trial in trials:
        if not isinstance(trial, Mapping) or "seed" not in trial or "passed" not in trial:
            raise ValueError("measurement/v1 facts.trials entries need seed and passed")
    _validate_ref_list(facts.get("artifacts"), "measurement/v1 facts.artifacts")
    _validate_nonblank_ref(facts.get("raw"), "measurement/v1 facts.raw")


def _validate_test_run_facts(facts: Mapping[str, object]) -> None:
    for key in ("passed", "failed"):
        value = facts.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"test-run/v1 facts.{key} must be a non-negative integer")
    _validate_ref_list(facts.get("artifacts"), "test-run/v1 facts.artifacts")
    _validate_nonblank_ref(facts.get("raw"), "test-run/v1 facts.raw")


def _validate_ref_list(value: object, field_name: str) -> None:
    if not isinstance(value, (list, tuple)) or any(
        not isinstance(ref, str) or not ref.strip() for ref in value
    ):
        raise ValueError(f"{field_name} must be a list of ref strings")


def _validate_nonblank_ref(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a nonblank ref string")


REGISTRY = PayloadRegistry()
REGISTRY.register(MEASUREMENT_SCHEMA, _validate_measurement_facts)
REGISTRY.register(TEST_RUN_SCHEMA, _validate_test_run_facts)


def measurement_observation(
    result: HarnessResult,
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
    """Adapt a trial-scored ``HarnessResult`` into a ``measurement/v1`` envelope.

    ``inputs``/``artifacts`` are the caller's own references (git commit,
    requirement doc, an existing report file); this adapter appends exactly
    one more artifact -- ``result.raw`` content-hashed by
    :func:`_raw_artifact` -- so raw output is always retained by reference,
    never embedded in ``facts``.

    ``outcome`` defaults to pass/fail from ``result.passed``; pass an
    explicit override (e.g. ``"interrupted"``, ``"invalid"``) when the
    harness itself could not produce a trustworthy result -- that judgment
    belongs to the caller's execution context, not to this adapter.
    """
    raw_ref = _raw_artifact(result.raw, id=id, scope_refs=scope_refs)
    facts = {
        "schema": MEASUREMENT_SCHEMA,
        "metric_value": result.metric_value,
        "passed": result.passed,
        "trials": _trial_facts(result),
        "artifacts": [a.ref for a in artifacts],
        "raw": raw_ref.ref,
    }
    envelope = ObservationEnvelope(
        schema=1,
        id=id,
        kind="measurement",
        producer=producer,
        observed_at=observed_at,
        scope_refs=tuple(scope_refs),
        inputs=tuple(inputs),
        outcome=_resolve_outcome(result, outcome),
        facts=facts,
        diagnostics=tuple(diagnostics),
        artifacts=(*artifacts, raw_ref),
    )
    return envelope.validate_for_gate(REGISTRY)


def test_run_observation(
    result: HarnessResult,
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
    """Adapt a pytest-selection ``HarnessResult`` into a ``test-run/v1`` envelope.

    One trial per collected test (``SimTestbenchHarness._run_pytest``);
    facts carry aggregate passed/failed counts, matching Increment 1's own
    ``test-run/v1`` worked example rather than ``measurement/v1``'s
    continuous ``metric_value`` shape.
    """
    raw_ref = _raw_artifact(result.raw, id=id, scope_refs=scope_refs)
    passed_count = sum(1 for t in result.trials if t.passed)
    facts = {
        "schema": TEST_RUN_SCHEMA,
        "passed": passed_count,
        "failed": len(result.trials) - passed_count,
        "artifacts": [a.ref for a in artifacts],
        "raw": raw_ref.ref,
    }
    envelope = ObservationEnvelope(
        schema=1,
        id=id,
        kind="test-run",
        producer=producer,
        observed_at=observed_at,
        scope_refs=tuple(scope_refs),
        inputs=tuple(inputs),
        outcome=_resolve_outcome(result, outcome),
        facts=facts,
        diagnostics=tuple(diagnostics),
        artifacts=(*artifacts, raw_ref),
    )
    return envelope.validate_for_gate(REGISTRY)
