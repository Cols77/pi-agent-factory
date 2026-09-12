from __future__ import annotations

from dataclasses import fields, replace

import pytest

from coherence.planning.lifecycle import LifecycleEvidence, project_lifecycle


pytestmark = pytest.mark.unit


def _evidence(**changes: object) -> LifecycleEvidence:
    values: dict[str, object] = {
        "run_id": "run-001",
        "state": "intent_provisional",
        "run_identity": {"run_id": "run-001", "next_sequence": 2, "journal_sha256": "a" * 64},
        "manifest_status": "missing",
        "artifact_kinds": frozenset(),
        "consent_status": "missing",
        "spec_review_status": "missing",
        "plan_review_status": "missing",
        "gate_status": "missing",
        "handoff_status": "missing",
        "unresolved_challenges": False,
    }
    values.update(changes)
    return LifecycleEvidence(**values)


@pytest.mark.parametrize(
    ("evidence", "action"),
    [
        (_evidence(), "author-requirements"),
        (_evidence(manifest_status="valid", artifact_kinds=frozenset({"requirements"})), "record-sr-consent"),
        (_evidence(manifest_status="valid", artifact_kinds=frozenset({"requirements"}), consent_status="valid"), "author-spec"),
        (_evidence(manifest_status="valid", artifact_kinds=frozenset({"requirements", "spec"}), consent_status="valid"), "author-plan"),
        (_evidence(manifest_status="valid", artifact_kinds=frozenset({"requirements", "spec", "plan"}), consent_status="valid"), "review-spec"),
        (_evidence(manifest_status="valid", artifact_kinds=frozenset({"requirements", "spec", "plan"}), consent_status="valid", spec_review_status="valid"), "review-plan"),
        (_evidence(manifest_status="valid", artifact_kinds=frozenset({"requirements", "spec", "plan"}), consent_status="valid", spec_review_status="valid", plan_review_status="valid"), "run-planning-gates"),
        (_evidence(manifest_status="valid", artifact_kinds=frozenset({"requirements", "spec", "plan"}), consent_status="valid", spec_review_status="valid", plan_review_status="valid", gate_status="valid"), "create-handoff"),
        (_evidence(manifest_status="valid", artifact_kinds=frozenset({"requirements", "spec", "plan"}), consent_status="valid", spec_review_status="valid", plan_review_status="valid", gate_status="valid", handoff_status="valid"), "inspect-handoff"),
    ],
)
def test_projects_exactly_one_current_lifecycle_action(
    evidence: LifecycleEvidence, action: str
) -> None:
    projection = project_lifecycle(evidence)

    assert projection.blocked is False
    assert projection.reason is None
    assert projection.legal_next_actions == (action,)
    assert projection.starts_automatically is False
    assert projection.run_identity == evidence.run_identity
    assert projection.to_dict()["legal_next_actions"] == [action]


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"unresolved_challenges": True}, "UNRESOLVED_CHALLENGE"),
        ({"manifest_status": "invalid"}, "ARTIFACT_MANIFEST_INVALID"),
        ({"manifest_status": "valid", "artifact_kinds": frozenset({"requirements"}), "consent_status": "stale"}, "STALE_REQUIREMENT_CONSENT"),
        ({"manifest_status": "valid", "artifact_kinds": frozenset({"requirements", "spec", "plan"}), "consent_status": "valid", "spec_review_status": "stale"}, "STALE_SPEC_REVIEW"),
        ({"manifest_status": "valid", "artifact_kinds": frozenset({"requirements", "spec", "plan"}), "consent_status": "valid", "spec_review_status": "valid", "plan_review_status": "valid", "gate_status": "failed"}, "PLANNING_GATES_FAILED"),
        ({"manifest_status": "valid", "artifact_kinds": frozenset({"requirements", "spec", "plan"}), "consent_status": "valid", "spec_review_status": "valid", "plan_review_status": "valid", "gate_status": "valid", "handoff_status": "invalid"}, "HANDOFF_INVALID"),
    ],
)
def test_blocks_on_unresolved_or_stale_lifecycle_evidence(
    changes: dict[str, object], reason: str
) -> None:
    projection = project_lifecycle(_evidence(**changes))

    assert projection.blocked is True
    assert projection.reason == reason
    assert projection.legal_next_actions == ()


def test_projection_is_immutable_and_never_exposes_multiple_actions() -> None:
    projection = project_lifecycle(_evidence())

    assert {field.name for field in fields(projection)} >= {
        "schema", "run_id", "blocked", "reason", "state", "legal_next_actions",
        "starts_automatically", "run_identity", "action_registry",
    }
    assert len(projection.legal_next_actions) <= 1
    with pytest.raises(AttributeError):
        projection.blocked = True  # type: ignore[misc]


@pytest.mark.parametrize("changes", [
    {"legal_next_actions": ("run-arbitrary-command",)},
    {"legal_next_actions": ("author-spec", "author-plan")},
    {"legal_next_actions": ()},
    {"blocked": True, "reason": "BLOCKED"},
    {"reason": "BLOCKED"},
    {"starts_automatically": True},
])
def test_projection_rejects_invalid_or_contradictory_actions(changes: dict[str, object]) -> None:
    projection = project_lifecycle(_evidence())

    with pytest.raises(ValueError):
        replace(projection, **changes)


def test_cancelled_capture_cannot_restart_authoring() -> None:
    projection = project_lifecycle(_evidence(state="blocked"))

    assert projection.blocked is True
    assert projection.reason == "SESSION_NOT_READY"
    assert projection.legal_next_actions == ()


def test_future_missing_evidence_does_not_skip_requirements() -> None:
    projection = project_lifecycle(_evidence(spec_review_status="stale", gate_status="failed"))

    assert projection.legal_next_actions == ("author-requirements",)


def test_evidence_copies_mutable_inputs() -> None:
    identity: dict[str, object] = {"run_id": "run-001"}
    evidence = _evidence(run_identity=identity)
    identity["run_id"] = "other-run"

    assert evidence.run_identity["run_id"] == "run-001"
    with pytest.raises(TypeError):
        evidence.run_identity["run_id"] = "other-run"  # type: ignore[index]
