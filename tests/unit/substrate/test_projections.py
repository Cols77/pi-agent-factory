from __future__ import annotations

import pytest

from substrate.observations import ObservationEnvelope, PayloadRegistry, RejectedObservation
from substrate.projections import agent_compact, human, machine

from test_observations import observation_payload, registry


pytestmark = pytest.mark.unit


FRESHNESS = {"state": "fresh", "checked_at": "2026-08-20T10:31:00Z"}


def valid_envelope() -> ObservationEnvelope:
    envelope = ObservationEnvelope.from_dict(observation_payload())
    assert isinstance(envelope, ObservationEnvelope)
    return envelope.validate_for_gate(registry())


def test_machine_projection_contains_full_envelope_and_provenance_metadata() -> None:
    envelope = valid_envelope()

    projected = machine(envelope, FRESHNESS)

    assert projected["source_id"] == envelope.id
    assert projected["schema"] == 1
    assert projected["freshness"] == FRESHNESS
    assert projected["truncated"] is False
    assert projected["redacted"] is False
    assert projected["outcome"] == "pass"
    assert projected["facts"] == {"schema": "test-run/v1", "passed": 41, "failed": 0}
    assert projected["diagnostics"] == [
        {"code": "ASSERTION_FAILED", "summary": "no failed assertions"}
    ]
    assert projected["artifacts"][0]["location"] == "evidence/test-run.json"


def test_human_projection_is_deterministic_and_explains_source_and_freshness() -> None:
    envelope = valid_envelope()

    first = human(envelope, FRESHNESS)
    second = human(envelope, FRESHNESS)

    assert first == second
    text = first["text"]
    assert isinstance(text, str)
    assert "outcome: pass" in text
    assert "ASSERTION_FAILED" in text
    assert "evidence/test-run.json" in text
    assert "artifact:evidence:test-run" in text
    assert "fresh" in text


def test_agent_compact_stably_orders_facts_diagnostics_and_artifact_pointers() -> None:
    payload = observation_payload(
        facts={
            "schema": "test-run/v1",
            "zeta": "last fact",
            "alpha": "first fact",
            "middle": "middle fact",
        }
    )
    payload["diagnostics"] = [
        {"code": "Z_LAST", "summary": "last diagnostic"},
        {"code": "A_FIRST", "summary": "first diagnostic"},
    ]
    payload["artifacts"] = [
        {**payload["artifacts"][0], "ref": "artifact:z-last"},
        {**payload["artifacts"][0], "ref": "artifact:a-first"},
    ]
    envelope = ObservationEnvelope.from_dict(payload)

    projected = agent_compact(envelope, FRESHNESS, 500)
    text = projected["text"]
    assert isinstance(text, str)

    assert text.index("alpha") < text.index("middle") < text.index("zeta")
    assert text.index("A_FIRST") < text.index("Z_LAST")
    assert text.index("artifact:a-first") < text.index("artifact:z-last")
    assert projected["truncated"] is False


def test_agent_compact_honours_character_budget_and_preserves_metadata() -> None:
    envelope = valid_envelope()

    projected = agent_compact(envelope, FRESHNESS, 72)

    assert len(projected["text"]) <= 72
    assert projected["truncated"] is True
    assert projected["source_id"] == envelope.id
    assert projected["outcome"] == "pass"
    assert [item["code"] for item in projected["diagnostics"]] == ["ASSERTION_FAILED"]


def test_agent_compact_redacts_only_declared_sensitive_values() -> None:
    envelope = ObservationEnvelope.from_dict(
        observation_payload(
            facts={
                "schema": "test-run/v1",
                "token": "top-secret-token",
                "ordinary": "secret-like content remains",
            }
        )
    )

    projected = agent_compact(envelope, FRESHNESS, 500, redactions=("top-secret-token",))

    assert projected["redacted"] is True
    assert "top-secret-token" not in projected["text"]
    assert "[REDACTED]" in projected["text"]
    assert "secret-like content remains" in projected["text"]


def test_agent_compact_redacts_sensitive_base_fields_and_diagnostics() -> None:
    sensitive_source_id = "sensitive-source-id"
    sensitive_freshness = "sensitive-freshness"
    payload = observation_payload()
    payload["id"] = sensitive_source_id
    payload["diagnostics"] = [
        {"code": "SENSITIVE_CONTEXT", "summary": sensitive_freshness},
    ]
    envelope = ObservationEnvelope.from_dict(payload)
    freshness = {"state": sensitive_freshness, "checked_at": "2026-08-20T10:31:00Z"}

    projected = agent_compact(
        envelope,
        freshness,
        500,
        redactions=(sensitive_source_id, sensitive_freshness),
    )

    assert projected["redacted"] is True
    assert projected["source_id"] == "[REDACTED]"
    assert projected["freshness"]["state"] == "[REDACTED]"
    assert projected["diagnostics"] == [
        {"code": "SENSITIVE_CONTEXT", "summary": "[REDACTED]"},
    ]
    assert sensitive_source_id not in str(projected)
    assert sensitive_freshness not in str(projected)


@pytest.mark.parametrize("outcome", ["invalid", "unknown"])
def test_every_projection_preserves_invalidity_outcome_and_diagnostic_codes(outcome: str) -> None:
    envelope = ObservationEnvelope.from_dict(observation_payload(outcome=outcome))
    envelope = envelope.validate_for_gate(registry())

    projections = [
        machine(envelope, FRESHNESS),
        human(envelope, FRESHNESS),
        agent_compact(envelope, FRESHNESS, 500),
    ]

    for projected in projections:
        assert projected["outcome"] == outcome
        assert [item["code"] for item in projected["diagnostics"]] == ["ASSERTION_FAILED"]
        assert "pass" not in projected["text"] if "text" in projected else True


def test_rejected_observations_are_projectable_only_as_explicit_invalid_values() -> None:
    rejected = ObservationEnvelope.from_dict(
        observation_payload(),
        registry=PayloadRegistry({
            "test-run/v1": lambda facts: (_ for _ in ()).throw(ValueError("payload rejected")),
        }),
    )
    assert isinstance(rejected, RejectedObservation)

    projected = agent_compact(rejected, FRESHNESS, 500)

    assert projected["outcome"] == "invalid"
    assert projected["invalid"] is True
    assert projected["truncated"] is False
    assert "FACTS_VALIDATION_REJECTED" in projected["text"]


def test_projection_does_not_mutate_the_envelope_or_freshness() -> None:
    envelope = valid_envelope()
    before = envelope.to_dict()
    freshness = {"state": "fresh"}

    machine(envelope, freshness)
    human(envelope, freshness)
    agent_compact(envelope, freshness, 200, redactions=("not-present",))

    assert envelope.to_dict() == before
    assert freshness == {"state": "fresh"}
