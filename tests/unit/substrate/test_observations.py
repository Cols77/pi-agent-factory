from __future__ import annotations

from copy import deepcopy

import pytest

from substrate.artifacts import ArtifactRef, ProducerRef, SnapshotInputRef
from substrate.observations import (
    Diagnostic,
    ObservationEnvelope,
    PayloadRegistry,
    RejectedObservation,
)


pytestmark = pytest.mark.unit

HASH = "sha256:" + "a" * 64
OTHER_HASH = "sha256:" + "b" * 64


def artifact_payload(ref: str = "artifact:evidence:test-run") -> dict[str, object]:
    return {
        "schema": 1,
        "kind": "test-report",
        "ref": ref,
        "location": "evidence/test-run.json",
        "content_hash": HASH,
        "scope_refs": ["scope:project"],
        "media_type": "application/json",
    }


def observation_payload(*, outcome: str = "pass", facts: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "schema": 1,
        "id": "obs:pytest-adapter:run-001",
        "kind": "test-run",
        "producer": {"name": "pytest-adapter", "version": 1, "engine": "pytest-8"},
        "observed_at": "2026-08-20T10:30:00Z",
        "scope_refs": ["sr:SR-032", "task:T-067"],
        "inputs": [
            {"ref": "git:commit:abc123", "content_hash": OTHER_HASH},
            {"ref": "artifact:requirements/SR-032.md"},
        ],
        "outcome": outcome,
        "facts": facts or {"schema": "test-run/v1", "passed": 41, "failed": 0},
        "diagnostics": [
            {"code": "ASSERTION_FAILED", "summary": "no failed assertions"},
        ],
        "artifacts": [artifact_payload()],
    }


def facts_validator(facts: dict[str, object]) -> None:
    if facts.get("passed") != 41 or facts.get("failed") != 0:
        raise ValueError("test-run facts do not describe the expected run")


def registry() -> PayloadRegistry:
    result = PayloadRegistry()
    result.register("test-run/v1", facts_validator)
    return result


def test_valid_envelope_round_trips_and_is_gate_eligible_after_explicit_validation() -> None:
    envelope = ObservationEnvelope.from_dict(observation_payload())

    assert isinstance(envelope, ObservationEnvelope)
    assert envelope.producer == ProducerRef("pytest-adapter", 1, "pytest-8")
    assert envelope.inputs == (
        SnapshotInputRef("git:commit:abc123", OTHER_HASH),
        SnapshotInputRef("artifact:requirements/SR-032.md"),
    )
    assert envelope.artifacts[0] == ArtifactRef.from_dict(artifact_payload())
    assert envelope.to_dict() == observation_payload()

    envelope.validate_for_gate(registry())

    assert envelope.gate_eligible is True


def test_facts_schema_must_be_a_string() -> None:
    payload = observation_payload(facts={"schema": 1, "passed": 41, "failed": 0})

    with pytest.raises((TypeError, ValueError), match="facts.schema"):
        ObservationEnvelope.from_dict(payload)


def test_unknown_facts_schema_is_rejected_by_explicit_gate_validation() -> None:
    envelope = ObservationEnvelope.from_dict(
        observation_payload(facts={"schema": "test-run/v9", "passed": 41, "failed": 0})
    )

    with pytest.raises(ValueError, match="unknown facts schema"):
        envelope.validate_for_gate(registry())

    assert envelope.gate_eligible is False


def test_registered_facts_validator_rejection_is_retained_as_invalid_observation() -> None:
    rejected = ObservationEnvelope.from_dict(observation_payload(), registry=PayloadRegistry({
        "test-run/v1": lambda facts: (_ for _ in ()).throw(ValueError("bad payload")),
    }))

    assert isinstance(rejected, RejectedObservation)
    assert rejected.id == "obs:pytest-adapter:run-001"
    assert rejected.kind == "test-run"
    assert rejected.producer == ProducerRef("pytest-adapter", 1, "pytest-8")
    assert rejected.outcome == "invalid"
    assert rejected.gate_eligible is False
    assert rejected.diagnostics[0].code == "FACTS_VALIDATION_REJECTED"
    assert rejected.raw_artifacts == (artifact_payload(),)


def test_unknown_facts_schema_with_explicit_registry_is_retained_as_invalid_observation() -> None:
    rejected = ObservationEnvelope.from_dict(
        observation_payload(
            facts={"schema": "test-run/v9", "passed": 41, "failed": 0},
        ),
        registry=registry(),
    )

    assert isinstance(rejected, RejectedObservation)
    assert rejected.outcome == "invalid"
    assert rejected.gate_eligible is False
    assert rejected.diagnostics[0].code == "FACTS_VALIDATION_REJECTED"
    assert "test-run/v9" in rejected.diagnostics[0].summary
    assert rejected.raw_artifacts == (artifact_payload(),)


@pytest.mark.parametrize("outcome", ["invalid", "unknown"])
def test_invalid_and_unknown_outcomes_are_preserved_and_never_gate_eligible(outcome: str) -> None:
    envelope = ObservationEnvelope.from_dict(observation_payload(outcome=outcome))
    envelope.validate_for_gate(registry())

    assert envelope.outcome == outcome
    assert envelope.gate_eligible is False


def test_unrecognised_outcome_is_not_silently_coerced() -> None:
    payload = observation_payload(outcome="maybe")

    with pytest.raises(ValueError, match="outcome"):
        ObservationEnvelope.from_dict(payload)


def test_invalid_observed_at_is_rejected() -> None:
    payload = observation_payload()
    payload["observed_at"] = "2026-08-20T10:30:00+02:00"

    with pytest.raises(ValueError, match="observed_at"):
        ObservationEnvelope.from_dict(payload)


@pytest.mark.parametrize(
    "diagnostics",
    [
        [{"code": "ONLY_CODE"}],
        [{"summary": "only summary"}],
        [{"code": "", "summary": "summary"}],
        [{"code": "CODE", "summary": 42}],
        [{"code": "CODE", "summary": "summary", "unexpected": True}],
    ],
)
def test_malformed_diagnostics_are_rejected(diagnostics: object) -> None:
    payload = observation_payload()
    payload["diagnostics"] = diagnostics

    with pytest.raises((TypeError, ValueError), match="diagnostic"):
        ObservationEnvelope.from_dict(payload)


def test_invalid_artifact_refs_are_rejected_without_reading_locations() -> None:
    payload = observation_payload()
    artifact = deepcopy(payload["artifacts"])
    assert isinstance(artifact, list)
    artifact[0]["content_hash"] = "md5:not-a-sha256"
    payload["artifacts"] = artifact

    with pytest.raises(ValueError, match="content_hash"):
        ObservationEnvelope.from_dict(payload)


def test_an_explicitly_validated_observation_keeps_its_interpretation() -> None:
    payload = observation_payload()
    local_registry = registry()
    envelope = ObservationEnvelope.from_dict(payload, registry=local_registry)
    assert isinstance(envelope, ObservationEnvelope)

    local_registry.register(
        "test-run/v1",
        lambda facts: (_ for _ in ()).throw(ValueError("replacement validator must not reinterpret it")),
    )

    assert envelope.gate_eligible is True


def test_diagnostic_is_a_structured_value_with_only_declared_fields() -> None:
    diagnostic = Diagnostic(code="ASSERTION_FAILED", summary="one assertion failed")

    assert diagnostic.to_dict() == {
        "code": "ASSERTION_FAILED",
        "summary": "one assertion failed",
    }
