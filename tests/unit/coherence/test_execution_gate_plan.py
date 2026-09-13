"""SR-034 Coherence-owned GatePlan compilation: RED tests (Task 8, Step 1/4)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from coherence.execution.gate_plan import (
    AC8_GATE,
    CANONICAL_EXECUTION_STAGES,
    CANONICAL_GATES,
    PREFLIGHT_POLICIES,
    GatePlan,
    GatePlanError,
    compile_gate_plan,
    gate_plan_identity_sha256,
)

pytestmark = pytest.mark.unit

CANONICAL_STAGE_IDS = (
    "contract-compiled",
    "preflight",
    "transport-materialized",
    "baseline",
    "dev",
    "validation",
    "campaign-classification",
    "review-spec",
    "review-quality",
    "review-join",
    "fixer",
    "canonical-gates",
    "handoff",
)


def plan(**overrides: object) -> GatePlan:
    values: dict[str, object] = {
        "workflow_version": "governed-execution/v1",
        "version": "behavior-change@1",
        "required_gates": ("unit", "full"),
        "preflight_policy": "mandatory-only",
    }
    values.update(overrides)
    return compile_gate_plan(**values)  # type: ignore[arg-type]


def test_canonical_stage_graph_and_gate_vocabulary_are_fixed() -> None:
    assert CANONICAL_EXECUTION_STAGES == CANONICAL_STAGE_IDS
    assert len(set(CANONICAL_EXECUTION_STAGES)) == 13
    assert CANONICAL_GATES == ("unit", "integration", "full")
    assert PREFLIGHT_POLICIES == ("mandatory-only",)
    assert AC8_GATE == "ac8-obligation-health"


def test_gate_plan_identity_is_stable_and_binds_every_compiled_input() -> None:
    first = plan()
    second = plan()

    assert len(first.gate_plan_sha256) == 64
    assert first.gate_plan_sha256 == second.gate_plan_sha256
    assert first.gate_plan_sha256 == first.rebuild_hash()
    assert first.stages == CANONICAL_EXECUTION_STAGES
    assert first.ac8_decision_ref is None

    payload = first.to_dict()
    assert payload["schema"] == 1
    assert payload["workflow_version"] == "governed-execution/v1"
    assert payload["version"] == "behavior-change@1"
    assert payload["stages"] == list(CANONICAL_STAGE_IDS)
    assert payload["required_gates"] == ["unit", "full"]
    assert payload["preflight_policy"] == "mandatory-only"


def test_changed_version_or_gate_list_changes_the_gate_plan_hash() -> None:
    base = plan()

    assert plan(version="behavior-change@2").gate_plan_sha256 != base.gate_plan_sha256
    assert plan(workflow_version="governed-execution/v2").gate_plan_sha256 != base.gate_plan_sha256
    assert plan(required_gates=("unit",)).gate_plan_sha256 != base.gate_plan_sha256
    assert plan(required_gates=("full", "unit")).gate_plan_sha256 != base.gate_plan_sha256


def test_a_changed_preflight_policy_changes_the_identity_and_is_not_compilable() -> None:
    """SR-034 ships ``mandatory-only``; the obligation/health policy is unconfirmed
    (decision 5), so the identity function records it while the compiler refuses it."""

    assert (
        gate_plan_identity_sha256(
            workflow_version="governed-execution/v1",
            version="behavior-change@1",
            stages=CANONICAL_EXECUTION_STAGES,
            required_gates=("unit", "full"),
            preflight_policy="obligation-health",
            ac8_decision_ref=None,
        )
        != gate_plan_identity_sha256(
            workflow_version="governed-execution/v1",
            version="behavior-change@1",
            stages=CANONICAL_EXECUTION_STAGES,
            required_gates=("unit", "full"),
            preflight_policy="mandatory-only",
            ac8_decision_ref=None,
        )
    )

    with pytest.raises(GatePlanError):
        plan(preflight_policy="obligation-health")


def test_missing_extra_duplicated_or_reordered_stage_is_rejected() -> None:
    with pytest.raises(GatePlanError):
        plan(stages=CANONICAL_STAGE_IDS[:-1])
    with pytest.raises(GatePlanError):
        plan(stages=CANONICAL_STAGE_IDS + ("extra",))
    with pytest.raises(GatePlanError):
        plan(stages=CANONICAL_STAGE_IDS[:3] + ("dev",) + CANONICAL_STAGE_IDS[3:])
    with pytest.raises(GatePlanError):
        plan(stages=tuple(reversed(CANONICAL_STAGE_IDS)))


def test_unknown_gate_blank_version_and_unknown_transport_free_values_are_rejected() -> None:
    with pytest.raises(GatePlanError):
        plan(required_gates=("unit", "not-a-gate"))
    with pytest.raises(GatePlanError):
        plan(version="   ")
    with pytest.raises(GatePlanError):
        plan(workflow_version="")
    with pytest.raises(GatePlanError):
        plan(required_gates=())


def test_ac8_obligation_health_gate_requires_a_current_decision_ref(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import coherence.execution.gate_plan as module

    # Decision 5: the FEAT-018 supply is unconfirmed, so no ref is current yet.
    with pytest.raises(GatePlanError):
        plan(required_gates=("unit", AC8_GATE))
    with pytest.raises(GatePlanError):
        plan(required_gates=("unit", AC8_GATE), ac8_decision_ref="feat-018/decision-5")

    monkeypatch.setattr(module, "CURRENT_AC8_DECISION_REF", "feat-018/decision-5")
    compiled = plan(required_gates=("unit", AC8_GATE), ac8_decision_ref="feat-018/decision-5")
    assert compiled.ac8_decision_ref == "feat-018/decision-5"

    with pytest.raises(GatePlanError):
        plan(required_gates=("unit", AC8_GATE), ac8_decision_ref="feat-018/decision-4")


def test_gate_plan_is_frozen_and_rejects_a_forged_digest() -> None:
    compiled = plan()

    with pytest.raises(FrozenInstanceError):
        compiled.preflight_policy = "obligation-health"  # type: ignore[misc]

    with pytest.raises(ValueError):
        GatePlan(
            schema=1,
            workflow_version="governed-execution/v1",
            version="behavior-change@1",
            stages=CANONICAL_EXECUTION_STAGES,
            required_gates=("unit", "full"),
            preflight_policy="mandatory-only",
            ac8_decision_ref=None,
            gate_plan_sha256="f" * 64,
        )

    with pytest.raises(GatePlanError):
        plan(version=123)  # type: ignore[arg-type]


def _hand_built_plan(**overrides: object) -> GatePlan:
    """Construct a GatePlan directly, digest made consistent with its own payload.

    This is the adversarial probe: a *self-consistent* digest is not validation,
    so before the structural gate every one of these reached ``with_gate_plan``
    and the transport projected cards for a bogus graph.
    """
    values: dict[str, object] = {
        "schema": 1,
        "workflow_version": "governed-execution/v1",
        "version": "behavior-change@1",
        "stages": CANONICAL_EXECUTION_STAGES,
        "required_gates": ("unit", "full"),
        "preflight_policy": "mandatory-only",
        "ac8_decision_ref": None,
    }
    values.update(overrides)
    digest = gate_plan_identity_sha256(
        workflow_version=values["workflow_version"],  # type: ignore[arg-type]
        version=values["version"],  # type: ignore[arg-type]
        stages=tuple(values["stages"]),  # type: ignore[arg-type]
        required_gates=tuple(values["required_gates"]),  # type: ignore[arg-type]
        preflight_policy=values["preflight_policy"],  # type: ignore[arg-type]
        ac8_decision_ref=values["ac8_decision_ref"],  # type: ignore[arg-type]
    )
    return GatePlan(**{**values, "gate_plan_sha256": digest})  # type: ignore[arg-type]


def test_a_hand_forged_plan_with_a_self_consistent_digest_is_rejected_at_construction() -> None:
    """``GatePlan`` validates its own structure, not just its own digest."""

    with pytest.raises(GatePlanError):
        _hand_built_plan(stages=("bogus", "dev"))
    with pytest.raises(GatePlanError):
        _hand_built_plan(stages=CANONICAL_EXECUTION_STAGES[:-1])
    with pytest.raises(GatePlanError):
        _hand_built_plan(stages=CANONICAL_EXECUTION_STAGES + ("extra",))
    with pytest.raises(GatePlanError):
        _hand_built_plan(stages=tuple(reversed(CANONICAL_EXECUTION_STAGES)))
    with pytest.raises(GatePlanError):
        _hand_built_plan(stages=("dev", "dev"))
    with pytest.raises(GatePlanError):
        _hand_built_plan(stages="dev")
    with pytest.raises(GatePlanError):
        _hand_built_plan(required_gates=("unit", "bogus"))
    with pytest.raises(GatePlanError):
        _hand_built_plan(required_gates=())
    with pytest.raises(GatePlanError):
        _hand_built_plan(required_gates=(AC8_GATE,))  # no current decision ref
    with pytest.raises(GatePlanError):
        _hand_built_plan(
            required_gates=("unit", AC8_GATE), ac8_decision_ref="feat-018/decision-5"
        )
    with pytest.raises(GatePlanError):
        _hand_built_plan(preflight_policy="obligation-health")
    with pytest.raises(GatePlanError):
        _hand_built_plan(schema=2)
    with pytest.raises(GatePlanError):
        _hand_built_plan(version="   ")
    with pytest.raises(GatePlanError):
        _hand_built_plan(workflow_version="")

    # And the forged digest itself is still rejected.
    with pytest.raises(ValueError):
        GatePlan(
            schema=1,
            workflow_version="governed-execution/v1",
            version="behavior-change@1",
            stages=CANONICAL_EXECUTION_STAGES,
            required_gates=("unit", "full"),
            preflight_policy="mandatory-only",
            ac8_decision_ref=None,
            gate_plan_sha256="f" * 64,
        )


def test_list_valued_fields_are_coerced_so_mutation_cannot_desync_the_digest() -> None:
    """A list field was mutable after verification: appending a stage left the
    stored digest untouched while the transport projected the mutated graph."""
    stages = list(CANONICAL_EXECUTION_STAGES)
    gates = ["unit", "full"]

    compiled = _hand_built_plan(stages=stages, required_gates=gates)

    assert isinstance(compiled.stages, tuple) and isinstance(compiled.required_gates, tuple)
    assert compiled.stages == CANONICAL_EXECUTION_STAGES
    assert compiled.required_gates == ("unit", "full")
    assert compiled.rebuild_hash() == compiled.gate_plan_sha256

    before = compiled.gate_plan_sha256
    stages.append("bogus")
    gates.append("bogus")
    assert compiled.stages == CANONICAL_EXECUTION_STAGES
    assert compiled.required_gates == ("unit", "full")
    assert compiled.rebuild_hash() == before == compiled.gate_plan_sha256
    assert "bogus" not in compiled.to_dict()["stages"]


def test_the_canonical_plan_still_compiles_unchanged() -> None:
    compiled = plan()
    assert compiled.stages == CANONICAL_EXECUTION_STAGES
    assert compiled.required_gates == ("unit", "full")
    assert compiled.gate_plan_sha256 == compiled.rebuild_hash()
    assert compiled == plan()
