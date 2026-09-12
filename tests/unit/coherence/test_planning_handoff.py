from __future__ import annotations

import json
import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from coherence.planning.handoff import (
    HandoffError,
    build_downstream_menu,
    build_handoff,
    render_summary,
    validate_handoff,
    write_handoff,
)
from coherence.planning.gates import compile_planning_gate_pack, evaluate_planning_gate_pack, write_cross_artifact_review
from coherence.planning.model import PlanningFinding, PlanningReport
from coherence.planning.run import planning_report_digest
from tests.unit.coherence.test_planning_gates import _write_current_planning_evidence

pytestmark = pytest.mark.unit


def _report(root: Path) -> PlanningReport:
    _write_current_planning_evidence(root)
    raw = json.loads((root / ".factory/planning/run-001/report.json").read_text(encoding="utf-8"))
    return PlanningReport(1, "run-001", True, tuple(raw["artifacts"]), (), (), True, None)


def _write_current_gate_result(root: Path, report: PlanningReport) -> None:
    run_dir = root / ".factory" / "planning" / report.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    raw_report = report.to_dict()
    (run_dir / "report.json").write_text(json.dumps(raw_report), encoding="utf-8")
    (run_dir / "review-decision.json").write_text(json.dumps({
        "schema": 1,
        "run_id": report.run_id,
        "decision": "approve",
        "reviewer": "human",
        "reason": "Reviewed planning artifacts.",
        "reviewed_artifacts": [item["path"] for item in raw_report["artifacts"]],
        "report_sha256": planning_report_digest(raw_report),
    }), encoding="utf-8")
    if not any(finding.severity == "error" for finding in report.findings):
        write_cross_artifact_review(root, report.run_id, {})
    evaluate_planning_gate_pack(root, report.run_id, compile_planning_gate_pack("FEAT-017", "v1"))


def test_clean_result_summary_and_menu_are_explicit_without_launching(tmp_path: Path) -> None:
    report = _report(tmp_path)
    summary = render_summary(report, semantic_notes=("semantic note",), unresolved=("open question",),
                             gate_summary={"status": "pass"})
    assert "semantic note" in summary and "open question" in summary
    assert "docs/plan.md" in summary and "pass" in summary
    menu = build_downstream_menu()
    assert [item["id"] for item in menu] == ["standard-development", "health-recovery", "feature-planning"]
    assert all(item["starts_automatically"] is False for item in menu)


def test_handoff_round_trip_is_hash_bound_and_paths_stay_in_run(tmp_path: Path) -> None:
    report = _report(tmp_path)
    _write_current_gate_result(tmp_path, report)
    (tmp_path / ".factory/planning/run-001/semantic-review-report.json").write_text("{}", encoding="utf-8")
    payload = build_handoff(tmp_path, report, workflow="standard-development")
    paths = write_handoff(tmp_path, payload)
    assert paths[0] == tmp_path / ".factory/planning/run-001/handoff.json"
    assert paths[1].read_text(encoding="utf-8").find("run-001") >= 0
    loaded = json.loads(paths[0].read_text(encoding="utf-8"))
    assert loaded["starts_automatically"] is False
    assert len(loaded["planning_gate_pack_sha256"]) == 64
    assert len(loaded["planning_gate_result_sha256"]) == 64
    assert validate_handoff(tmp_path, paths[0]) == loaded
    (tmp_path / "docs/plan.md").write_text("changed", encoding="utf-8")
    with pytest.raises(HandoffError):
        validate_handoff(tmp_path, paths[0])


def test_invalid_workflow_fails_closed() -> None:
    with pytest.raises(HandoffError):
        build_downstream_menu("run-process")


def test_handoff_workflow_must_match_the_current_cross_artifact_review(tmp_path: Path) -> None:
    report = _report(tmp_path)
    _write_current_gate_result(tmp_path, report)
    with pytest.raises(HandoffError, match="does not match"):
        build_handoff(tmp_path, report, workflow="health-recovery")

    write_cross_artifact_review(
        tmp_path, report.run_id, {}, selected_workflow="health-recovery",
    )
    evaluate_planning_gate_pack(tmp_path, report.run_id, compile_planning_gate_pack("FEAT-017", "v1"))
    with pytest.raises(HandoffError, match="does not match"):
        build_handoff(tmp_path, report, workflow="standard-development")
    assert build_handoff(tmp_path, report, workflow="health-recovery")["selected_workflow"] == "health-recovery"


@pytest.mark.parametrize("mutation", ["empty", "substituted", "appended", "duplicated"])
def test_handoff_artifacts_must_match_gate_attested_list(tmp_path: Path, mutation: str) -> None:
    report = _report(tmp_path)
    _write_current_gate_result(tmp_path, report)
    payload = build_handoff(tmp_path, report)
    path, _ = write_handoff(tmp_path, payload)
    assert validate_handoff(tmp_path, path) == payload

    # A real file with a correct digest must not gain the report's authority.
    substitute = tmp_path / "docs/substitute.md"
    substitute.write_text("unreviewed plan", encoding="utf-8")
    replacement = {
        "path": "docs/substitute.md",
        "sha256": hashlib.sha256(substitute.read_bytes()).hexdigest(),
    }
    original = list(report.artifacts)
    payload["canonical_artifacts"] = {
        "empty": [],
        "substituted": [replacement],
        "appended": [*original, replacement],
        "duplicated": [*original, *original],
    }[mutation]
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(HandoffError, match="artifacts do not match.*gate"):
        validate_handoff(tmp_path, path)


def test_handoff_rejects_ok_report_with_error_finding(tmp_path: Path) -> None:
    clean = _report(tmp_path)
    _write_current_gate_result(tmp_path, clean)
    build_handoff(tmp_path, clean)
    contradictory = replace(clean, findings=(PlanningFinding("BLOCK", "error", "plan", "Blocking defect."),))
    _write_current_gate_result(tmp_path, contradictory)
    with pytest.raises(HandoffError):
        build_handoff(tmp_path, contradictory)


def test_validator_rejects_tampered_workflow_menu_and_unsafe_run_id(tmp_path: Path) -> None:
    report = _report(tmp_path)
    _write_current_gate_result(tmp_path, report)
    payload = build_handoff(tmp_path, report)
    path, _ = write_handoff(tmp_path, payload)

    tampered = json.loads(path.read_text(encoding="utf-8"))
    tampered["selected_workflow"] = "launch-process"
    path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(HandoffError):
        validate_handoff(tmp_path, path)

    with pytest.raises(HandoffError):
        build_handoff(tmp_path, _report(tmp_path), workflow=".")


def test_handoff_rejects_legacy_default_or_unvalidated_gate_summary(tmp_path: Path) -> None:
    report = _report(tmp_path)
    with pytest.raises(HandoffError):
        build_handoff(tmp_path, report)
    _write_current_gate_result(tmp_path, report)
    with pytest.raises(HandoffError):
        build_handoff(tmp_path, report, gate_summary={"status": "pass"})
