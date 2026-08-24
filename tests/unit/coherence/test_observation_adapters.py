"""Contract fixtures for coherence's native observation adapters.

One section per registered facts schema (measurement/v1, test-run/v1,
simulation-run/v1 in this file; Task 3 appends an audit/v1 section below
without restructuring what is here). Each section proves, against its own
native domain object:

* the envelope carries the right ``facts["schema"]`` and the expected
  ``outcome``;
* typed facts preserve the domain object's own fields, and raw/native
  output is referenced by content hash rather than embedded;
* the ``machine`` and ``agent_compact`` projections agree on outcome,
  diagnostic codes and artifact refs;
* an invalid/unknown outcome cannot project as a pass -- the compact
  material view drops facts entirely rather than showing a stale
  ``passed`` value next to a distrusted outcome.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from substrate.artifacts import ArtifactRef, ProducerRef, SnapshotInputRef
from substrate.observations import ObservationEnvelope, PayloadRegistry
from substrate.projections import agent_compact, machine

from coherence.measurement.harness import HarnessResult, TrialResult
from coherence.measurement.observations import (
    MEASUREMENT_SCHEMA,
    REGISTRY as MEASUREMENT_REGISTRY,
    TEST_RUN_SCHEMA,
    measurement_observation,
)

# Imported under an alias: a bare `test_run_observation` import would land a
# name matching pytest's `test_*` collection pattern in this module's
# namespace, and pytest would try to collect the adapter itself as a test.
from coherence.measurement.observations import test_run_observation as make_test_run_observation
from coherence.simulation.observations import (
    REGISTRY as SIMULATION_REGISTRY,
    SIMULATION_RUN_SCHEMA,
    simulation_run_observation,
)
from coherence.simulation.registry import Run

pytestmark = pytest.mark.unit

HASH = "sha256:" + "a" * 64
PRODUCER = ProducerRef(name="test-harness-adapter", version=1)
OBSERVED_AT = "2026-08-24T10:00:00Z"
SOME_INPUT = SnapshotInputRef(ref="git:commit:abc123", content_hash=HASH)
SOME_ARTIFACT = ArtifactRef(
    schema=1,
    kind="test-report",
    ref="artifact:evidence:existing-report",
    location="evidence/existing-report.json",
    content_hash=HASH,
    scope_refs=("scope:project",),
)


def _artifact_refs(view: dict) -> set[str]:
    return {a["ref"] for a in view["artifacts"]}


def _diagnostic_codes(view: dict) -> list[str]:
    return [d["code"] for d in view["diagnostics"]]


def _compact_contains_ref(text: str, ref: str) -> bool:
    quoted = json.dumps(ref, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return quoted in text


def _assert_projection_parity(envelope: ObservationEnvelope) -> None:
    """machine and agent_compact must agree on outcome, diagnostic codes, and
    artifact refs -- the two views may differ in shape, never in substance."""
    machine_view = machine(envelope, freshness="fresh")
    compact_view = agent_compact(envelope, freshness="fresh", max_chars=10_000)

    assert machine_view["outcome"] == compact_view["outcome"] == envelope.outcome
    assert _diagnostic_codes(machine_view) == _diagnostic_codes(compact_view)

    envelope_refs = {a.ref for a in envelope.artifacts}
    assert _artifact_refs(machine_view) == envelope_refs
    for ref in envelope_refs:
        assert _compact_contains_ref(compact_view["text"], ref)


def _assert_invalid_or_unknown_cannot_project_to_pass(envelope: ObservationEnvelope) -> None:
    assert envelope.outcome in {"invalid", "unknown"}
    compact_view = agent_compact(envelope, freshness="fresh", max_chars=10_000)
    # The compact material view omits the "facts=" line entirely for a
    # distrusted outcome -- a stray "passed=True" fact could not otherwise
    # be told apart from a real pass. ("facts=" is checked as a whole line,
    # not a substring: "artifacts=" also contains the characters "facts=".)
    lines = compact_view["text"].splitlines()
    assert not any(line.startswith("facts=") for line in lines)
    assert "passed=True" not in compact_view["text"]

    # The machine projection remains the complete source of truth: nothing
    # here about what facts recorded, only about what may be trusted.
    machine_view = machine(envelope, freshness="fresh")
    assert machine_view["facts"] == envelope.to_dict()["facts"]


# --------------------------------------------------------------------------
# measurement/v1 (coherence.measurement.observations.measurement_observation)
# --------------------------------------------------------------------------


def _harness_result(
    *,
    passed: bool,
    metric_value: float = 0.9,
    trials: list[TrialResult] | None = None,
    raw: dict | None = None,
) -> HarnessResult:
    return HarnessResult(
        metric_value=metric_value,
        passed=passed,
        trials=trials if trials is not None else [TrialResult(seed=0, passed=passed)],
        artifacts=[],
        raw=raw if raw is not None else {"detail": "native raw payload", "nested": {"x": 1}},
    )


@pytest.mark.parametrize(
    "harness_passed,outcome_override,expected_outcome",
    [
        (True, None, "pass"),
        (False, None, "fail"),
        (False, "interrupted", "interrupted"),
        (False, "invalid", "invalid"),
    ],
)
def test_measurement_v1_outcome_matches_expected(
    harness_passed: bool, outcome_override: str | None, expected_outcome: str
) -> None:
    result = _harness_result(passed=harness_passed)

    envelope = measurement_observation(
        result,
        (SOME_INPUT,),
        (SOME_ARTIFACT,),
        id=f"obs:measurement:{expected_outcome}",
        producer=PRODUCER,
        observed_at=OBSERVED_AT,
        scope_refs=("sr:SR-001",),
        outcome=outcome_override,
    )

    assert envelope.facts["schema"] == MEASUREMENT_SCHEMA
    assert envelope.outcome == expected_outcome
    assert envelope.gate_eligible is (expected_outcome in {"pass", "fail"})


def test_measurement_v1_facts_preserve_fields_without_embedding_raw_output() -> None:
    raw = {"detail": "native raw payload", "nested": {"x": 1}}
    trials = [TrialResult(seed=0, passed=True, detail="ok"), TrialResult(seed=1, passed=False, detail="bad")]
    result = _harness_result(passed=False, metric_value=0.5, trials=trials, raw=raw)

    envelope = measurement_observation(
        result,
        (SOME_INPUT,),
        (SOME_ARTIFACT,),
        id="obs:measurement:facts",
        producer=PRODUCER,
        observed_at=OBSERVED_AT,
    )

    facts = envelope.facts
    assert facts["metric_value"] == 0.5
    assert facts["passed"] is False
    assert facts["trials"] == (
        {"seed": 0, "passed": True, "detail": "ok"},
        {"seed": 1, "passed": False, "detail": "bad"},
    )
    assert facts["artifacts"] == (SOME_ARTIFACT.ref,)

    # Raw output is referenced, never embedded: no key in facts holds the raw
    # dict (or any of its distinguishing content) directly.
    assert "detail" not in facts
    assert "nested" not in facts
    assert all(value != raw for value in facts.values())

    raw_ref = facts["raw"]
    assert isinstance(raw_ref, str) and raw_ref.strip()
    raw_artifact = next(a for a in envelope.artifacts if a.ref == raw_ref)
    assert raw_artifact.content_hash.startswith("sha256:")
    assert raw_artifact not in (SOME_ARTIFACT,)


def test_measurement_v1_projections_agree_on_outcome_diagnostics_and_artifacts() -> None:
    result = _harness_result(passed=True)
    envelope = measurement_observation(
        result,
        (SOME_INPUT,),
        (SOME_ARTIFACT,),
        id="obs:measurement:parity",
        producer=PRODUCER,
        observed_at=OBSERVED_AT,
    )
    _assert_projection_parity(envelope)


def test_measurement_v1_invalid_outcome_cannot_project_to_pass() -> None:
    result = _harness_result(passed=True)  # facts say passed, outcome overridden below
    envelope = measurement_observation(
        result,
        (SOME_INPUT,),
        (SOME_ARTIFACT,),
        id="obs:measurement:invalid",
        producer=PRODUCER,
        observed_at=OBSERVED_AT,
        outcome="invalid",
    )
    assert envelope.facts["passed"] is True  # the machine truth is retained
    _assert_invalid_or_unknown_cannot_project_to_pass(envelope)


def test_measurement_v1_registry_rejects_facts_missing_required_keys() -> None:
    with pytest.raises(ValueError, match="metric_value"):
        MEASUREMENT_REGISTRY.validate({"schema": MEASUREMENT_SCHEMA})


# --------------------------------------------------------------------------
# test-run/v1 (coherence.measurement.observations.test_run_observation)
# --------------------------------------------------------------------------


def _pytest_harness_result(*, passed_trials: int, failed_trials: int, overall_passed: bool) -> HarnessResult:
    trials = [TrialResult(seed=i, passed=True) for i in range(passed_trials)]
    trials += [
        TrialResult(seed=passed_trials + i, passed=False, detail="assertion failed")
        for i in range(failed_trials)
    ]
    return HarnessResult(
        metric_value=passed_trials / (passed_trials + failed_trials),
        passed=overall_passed,
        trials=trials,
        artifacts=[],
        raw={
            "selection": "tests/unit/example",
            "collected": passed_trials + failed_trials,
            "passed": passed_trials,
            "rc": 0 if overall_passed else 1,
        },
    )


@pytest.mark.parametrize(
    "overall_passed,outcome_override,expected_outcome",
    [
        (True, None, "pass"),
        (False, None, "fail"),
        (False, "interrupted", "interrupted"),
        (False, "invalid", "invalid"),
    ],
)
def test_test_run_v1_outcome_matches_expected(
    overall_passed: bool, outcome_override: str | None, expected_outcome: str
) -> None:
    result = _pytest_harness_result(passed_trials=3, failed_trials=1, overall_passed=overall_passed)

    envelope = make_test_run_observation(
        result,
        (SOME_INPUT,),
        (SOME_ARTIFACT,),
        id=f"obs:test-run:{expected_outcome}",
        producer=PRODUCER,
        observed_at=OBSERVED_AT,
        outcome=outcome_override,
    )

    assert envelope.facts["schema"] == TEST_RUN_SCHEMA
    assert envelope.outcome == expected_outcome


def test_test_run_v1_facts_carry_aggregate_counts_without_embedding_raw_output() -> None:
    result = _pytest_harness_result(passed_trials=41, failed_trials=1, overall_passed=False)

    envelope = make_test_run_observation(
        result,
        (SOME_INPUT,),
        (SOME_ARTIFACT,),
        id="obs:test-run:facts",
        producer=PRODUCER,
        observed_at=OBSERVED_AT,
    )

    facts = envelope.facts
    assert facts["passed"] == 41
    assert facts["failed"] == 1
    assert "selection" not in facts
    assert "rc" not in facts
    raw_ref = facts["raw"]
    assert isinstance(raw_ref, str) and raw_ref.strip()
    raw_artifact = next(a for a in envelope.artifacts if a.ref == raw_ref)
    assert raw_artifact.content_hash.startswith("sha256:")


def test_test_run_v1_projections_agree_on_outcome_diagnostics_and_artifacts() -> None:
    result = _pytest_harness_result(passed_trials=5, failed_trials=0, overall_passed=True)
    envelope = make_test_run_observation(
        result,
        (SOME_INPUT,),
        (SOME_ARTIFACT,),
        id="obs:test-run:parity",
        producer=PRODUCER,
        observed_at=OBSERVED_AT,
    )
    _assert_projection_parity(envelope)


def test_test_run_v1_invalid_outcome_cannot_project_to_pass() -> None:
    result = _pytest_harness_result(passed_trials=5, failed_trials=0, overall_passed=True)
    envelope = make_test_run_observation(
        result,
        (SOME_INPUT,),
        (SOME_ARTIFACT,),
        id="obs:test-run:invalid",
        producer=PRODUCER,
        observed_at=OBSERVED_AT,
        outcome="invalid",
    )
    _assert_invalid_or_unknown_cannot_project_to_pass(envelope)


def test_test_run_v1_registry_rejects_negative_counts() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        MEASUREMENT_REGISTRY.validate(
            {"schema": TEST_RUN_SCHEMA, "passed": -1, "failed": 0, "artifacts": [], "raw": "x"}
        )


# --------------------------------------------------------------------------
# simulation-run/v1 (coherence.simulation.observations.simulation_run_observation)
# --------------------------------------------------------------------------


def _run(tmp_path: Path, *, scope_errors: list[str] | None = None, result: str | None = "passed") -> Run:
    run_dir = tmp_path / "evidence" / "runs" / "RUN-20260824-0001"
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = run_dir / "manifest.json"
    if scope_errors is None:
        manifest_path.write_text(
            json.dumps({"run": "RUN-20260824-0001", "experiment": "SIM-047"}), encoding="utf-8"
        )
    return Run(
        run_id="RUN-20260824-0001",
        experiment="SIM-047",
        feature="FEAT-NAV-017",
        requirements=["SR-032"],
        goals=["GOAL-NAV-003"],
        commit="f92b004",
        result=result,
        path=manifest_path,
        scope_errors=scope_errors or [],
        recorded_ts="2026-08-24T09:00:00Z",
    )


@pytest.mark.parametrize(
    "result,scope_errors,outcome_override,expected_outcome",
    [
        ("passed", None, None, "pass"),
        ("failed", None, None, "fail"),
        (None, None, None, "unknown"),
        ("passed", ["manifest file missing: x"], None, "invalid"),
        ("passed", None, "interrupted", "interrupted"),
    ],
)
def test_simulation_run_v1_outcome_matches_expected(
    tmp_path: Path,
    result: str | None,
    scope_errors: list[str] | None,
    outcome_override: str | None,
    expected_outcome: str,
) -> None:
    run = _run(tmp_path, scope_errors=scope_errors, result=result)

    envelope = simulation_run_observation(
        run,
        (SOME_INPUT,),
        (),
        id=f"obs:simulation-run:{expected_outcome}",
        producer=PRODUCER,
        observed_at=OBSERVED_AT,
        scope_refs=("feat:FEAT-NAV-017",),
        outcome=outcome_override,
    )

    assert envelope.facts["schema"] == SIMULATION_RUN_SCHEMA
    assert envelope.outcome == expected_outcome


def test_simulation_run_v1_facts_preserve_run_fields_and_reference_manifest(tmp_path: Path) -> None:
    run = _run(tmp_path)

    envelope = simulation_run_observation(
        run,
        (SOME_INPUT,),
        (),
        id="obs:simulation-run:facts",
        producer=PRODUCER,
        observed_at=OBSERVED_AT,
    )

    facts = envelope.facts
    assert facts["run_id"] == "RUN-20260824-0001"
    assert facts["experiment"] == "SIM-047"
    assert facts["feature"] == "FEAT-NAV-017"
    assert facts["requirements"] == ("SR-032",)
    assert facts["goals"] == ("GOAL-NAV-003",)
    assert facts["commit"] == "f92b004"
    assert facts["result"] == "passed"

    manifest_ref = facts["manifest"]
    assert isinstance(manifest_ref, str) and manifest_ref.strip()
    manifest_artifact = next(a for a in envelope.artifacts if a.ref == manifest_ref)
    assert manifest_artifact.content_hash.startswith("sha256:")
    assert manifest_artifact.location == str(run.path)


def test_simulation_run_v1_missing_manifest_has_no_manifest_ref_but_is_still_recorded(
    tmp_path: Path,
) -> None:
    run = _run(tmp_path, scope_errors=["manifest file missing: gone.json"])

    envelope = simulation_run_observation(
        run,
        (),
        (),
        id="obs:simulation-run:missing",
        producer=PRODUCER,
        observed_at=OBSERVED_AT,
    )

    assert envelope.outcome == "invalid"
    assert envelope.facts["manifest"] is None
    assert any(d.code == "SIMULATION_RUN_SCOPE_ERROR" for d in envelope.diagnostics)


def test_simulation_run_v1_projections_agree_on_outcome_diagnostics_and_artifacts(
    tmp_path: Path,
) -> None:
    run = _run(tmp_path)
    envelope = simulation_run_observation(
        run,
        (SOME_INPUT,),
        (),
        id="obs:simulation-run:parity",
        producer=PRODUCER,
        observed_at=OBSERVED_AT,
    )
    _assert_projection_parity(envelope)


def test_simulation_run_v1_invalid_outcome_cannot_project_to_pass(tmp_path: Path) -> None:
    run = _run(tmp_path, scope_errors=["manifest file missing: gone.json"])
    envelope = simulation_run_observation(
        run,
        (),
        (),
        id="obs:simulation-run:invalid-projection",
        producer=PRODUCER,
        observed_at=OBSERVED_AT,
    )
    _assert_invalid_or_unknown_cannot_project_to_pass(envelope)


def test_simulation_run_v1_registry_rejects_non_string_run_id() -> None:
    with pytest.raises(ValueError, match="run_id"):
        SIMULATION_REGISTRY.validate(
            {
                "schema": SIMULATION_RUN_SCHEMA,
                "run_id": 123,
                "experiment": "SIM-1",
                "requirements": [],
                "goals": [],
                "feature": None,
                "commit": None,
                "recorded_ts": None,
                "result": None,
                "artifacts": [],
                "manifest": None,
            }
        )


# --------------------------------------------------------------------------
# Registries stay schema-scoped: neither adapter's registry validates the
# other domain's facts schema.
# --------------------------------------------------------------------------


def test_measurement_registry_does_not_know_simulation_run_schema() -> None:
    assert MEASUREMENT_REGISTRY.lookup(SIMULATION_RUN_SCHEMA) is None


def test_simulation_registry_does_not_know_measurement_schema() -> None:
    assert SIMULATION_REGISTRY.lookup(MEASUREMENT_SCHEMA) is None


def test_registries_are_payload_registry_instances() -> None:
    assert isinstance(MEASUREMENT_REGISTRY, PayloadRegistry)
    assert isinstance(SIMULATION_REGISTRY, PayloadRegistry)
