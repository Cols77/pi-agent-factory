from __future__ import annotations

import json
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
from coherence.planning.gates import compile_planning_gate_pack, evaluate_planning_gate_pack
from coherence.planning.model import PlanningFinding, PlanningReport
from coherence.planning.run import planning_report_digest

pytestmark = pytest.mark.unit


def _report(root: Path) -> PlanningReport:
    (root / "docs").mkdir(exist_ok=True)
    (root / "docs" / "plan.md").write_text("plan", encoding="utf-8")
    import hashlib
    digest = hashlib.sha256(b"plan").hexdigest()
    return PlanningReport(1, "run-001", True, ({"path": "docs/plan.md", "sha256": digest},),
                          (PlanningFinding("NOTE", "warning", "plan", "unresolved note"),),
                          (), True, None)


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
        "reviewed_artifacts": ["docs/plan.md"],
        "report_sha256": planning_report_digest(raw_report),
    }), encoding="utf-8")
    (run_dir / "requirement-consent.json").write_text(json.dumps({
        "schema": 1,
        "run_id": report.run_id,
        "decision": "approve",
        "reviewer": "human",
        "reason": "Reviewed planning requirements.",
        "requirements": [],
    }), encoding="utf-8")
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
