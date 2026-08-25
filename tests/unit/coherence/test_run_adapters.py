"""Increment 7 Task 2: independent source adapters.

Each adapter reads one durable native store and projects it into internal
:class:`coherence.runs.model.RunStatusInput` rows -- preserving native identity,
outcome, artifact refs and (for simulation) the requirement list -- and degrades
a malformed source to ``unknown`` plus a diagnostic rather than a pass.
"""
import pytest
import json

from coherence.runs import (
    audit_adapter,
    experiment_adapter,
    factory_adapter,
    measurement_adapter,
    simulation_adapter,
)

pytestmark = pytest.mark.unit


def _manifest(run_id: str, experiment: str, result: str | None, requirements: list[str] | None = None):
    payload = {
        "run": run_id,
        "experiment": experiment,
        "feature": "FEAT-1",
        "requirements": requirements if requirements is not None else ["SR-A"],
        "goals": [],
        "commit": "abc123",
        "result": result,
    }
    return json.dumps(payload)


# -- factory ----------------------------------------------------------------


def test_factory_adapter_preserves_native_identity(tmp_path):
    run_dir = tmp_path / "sessions" / ".factory-runs" / "by-session" / "run-1"
    run_dir.mkdir(parents=True)
    (run_dir / "journal.jsonl").write_text("", encoding="utf-8")

    rows = factory_adapter.factory_run_status(tmp_path)
    assert rows and rows[0].producer == "factory" and rows[0].run_id == "run-1"


def test_factory_adapter_no_store_returns_empty(tmp_path):
    assert factory_adapter.factory_run_status(tmp_path) == []


def test_factory_adapter_malformed_degrades_to_unknown(tmp_path):
    run_dir = tmp_path / "sessions" / ".factory-runs" / "by-session" / "run-1"
    run_dir.mkdir(parents=True)
    (run_dir / "checkpoint.json").write_text("not-json{", encoding="utf-8")
    rows = factory_adapter.factory_run_status(tmp_path)
    assert rows and rows[0].state == "unknown"
    assert any(d.code == "FACTORY_RUN_MALFORMED" for d in rows[0].diagnostics)


# -- audit ------------------------------------------------------------------


def test_audit_adapter_reads_report_json(tmp_path):
    run_dir = tmp_path / "coverage-reviews" / "feat-1-run1"
    run_dir.mkdir(parents=True)
    (run_dir / "report.json").write_text(
        json.dumps({"feature": "feat-1", "run_id": "run1", "states": {"SR-A": ["pass", []]}}),
        encoding="utf-8",
    )
    rows = audit_adapter.audit_run_status(tmp_path)
    assert rows and rows[0].producer == "audit" and rows[0].run_id == "run1" and rows[0].state == "passed"


def test_audit_adapter_hard_fail_state_is_failed(tmp_path):
    run_dir = tmp_path / "coverage-reviews" / "feat-1-run1"
    run_dir.mkdir(parents=True)
    (run_dir / "audit.json").write_text(
        json.dumps({"feature": "feat-1", "run_id": "run1", "states": {"SR-A": ["dishonest", []]}}),
        encoding="utf-8",
    )
    rows = audit_adapter.audit_run_status(tmp_path)
    assert rows and rows[0].state == "failed"


def test_audit_adapter_missing_report_degrades(tmp_path):
    run_dir = tmp_path / "coverage-reviews" / "feat-1"
    run_dir.mkdir(parents=True)
    rows = audit_adapter.audit_run_status(tmp_path)
    assert rows and rows[0].state == "unknown"
    assert rows[0].diagnostics and rows[0].diagnostics[0].code == "AUDIT_RUN_NO_REPORT"


# -- measurement -------------------------------------------------------------


def test_measurement_adapter_passed(tmp_path):
    (tmp_path / "validation").mkdir(parents=True)
    (tmp_path / "validation" / "validation-report.json").write_text(
        json.dumps({"run_id": "v1", "generated_at": "2026-01-01T00:00:00Z", "requirements": [{"id": "SR-A", "passed": True}]}),
        encoding="utf-8",
    )
    rows = measurement_adapter.measurement_run_status(tmp_path)
    assert rows and rows[0].producer == "measurement" and rows[0].state == "passed"


def test_measurement_adapter_failed_requirement(tmp_path):
    (tmp_path / "validation").mkdir(parents=True)
    (tmp_path / "validation" / "validation-report.json").write_text(
        json.dumps({"run_id": "v1", "requirements": [{"id": "SR-A", "passed": False}]}),
        encoding="utf-8",
    )
    rows = measurement_adapter.measurement_run_status(tmp_path)
    assert rows and rows[0].state == "failed"


def test_measurement_adapter_malformed(tmp_path):
    (tmp_path / "validation").mkdir(parents=True)
    (tmp_path / "validation" / "validation-report.json").write_text("{oops", encoding="utf-8")
    rows = measurement_adapter.measurement_run_status(tmp_path)
    assert rows and rows[0].state == "unknown"


# -- simulation --------------------------------------------------------------


def test_simulation_adapter_preserves_requirements_order(tmp_path):
    (tmp_path / "evidence" / "runs" / "RUN-1").mkdir(parents=True)
    (tmp_path / "evidence" / "runs" / "RUN-1" / "manifest.json").write_text(
        _manifest("RUN-1", "exp", "failed", requirements=["SR-B", "SR-A"]),
        encoding="utf-8",
    )
    rows = simulation_adapter.simulation_run_status(tmp_path)
    assert rows and rows[0].producer == "simulation"
    assert rows[0].requirement_ids == ("SR-B", "SR-A")  # native order preserved verbatim


def test_simulation_adapter_failed_state(tmp_path):
    (tmp_path / "evidence" / "runs" / "RUN-1").mkdir(parents=True)
    (tmp_path / "evidence" / "runs" / "RUN-1" / "manifest.json").write_text(
        _manifest("RUN-1", "exp", "failed"), encoding="utf-8"
    )
    rows = simulation_adapter.simulation_run_status(tmp_path)
    assert rows and rows[0].state == "failed"


# -- experiment --------------------------------------------------------------


def test_experiment_adapter_is_distinct_producer(tmp_path):
    (tmp_path / "evidence" / "runs" / "RUN-1").mkdir(parents=True)
    (tmp_path / "evidence" / "runs" / "RUN-2").mkdir(parents=True)
    (tmp_path / "evidence" / "runs" / "RUN-1" / "manifest.json").write_text(
        _manifest("RUN-1", "exp-alpha", "passed"), encoding="utf-8"
    )
    (tmp_path / "evidence" / "runs" / "RUN-2" / "manifest.json").write_text(
        _manifest("RUN-2", "exp-alpha", "failed"), encoding="utf-8"
    )
    rows = experiment_adapter.experiment_run_status(tmp_path)
    # one row per distinct experiment, state from its latest run
    assert len(rows) == 1
    row = rows[0]
    assert row.producer == "experiment" and row.run_id == "exp-alpha"
    assert row.requirement_ids == ()


def test_experiment_adapter_none_when_empty(tmp_path):
    assert experiment_adapter.experiment_run_status(tmp_path) == []


def test_all_adapters_return_carrier_instances(tmp_path):
    assert isinstance(factory_adapter.factory_run_status(tmp_path), list)
    assert isinstance(audit_adapter.audit_run_status(tmp_path), list)
    assert isinstance(measurement_adapter.measurement_run_status(tmp_path), list)
    assert isinstance(simulation_adapter.simulation_run_status(tmp_path), list)
    assert isinstance(experiment_adapter.experiment_run_status(tmp_path), list)