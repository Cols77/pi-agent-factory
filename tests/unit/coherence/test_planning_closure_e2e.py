from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from coherence.planning.artifacts import build_artifact_manifest, write_artifact_manifest
from coherence.planning.consent import CONSENT_PHRASE, write_sr_decision
from coherence.planning.gates import PlanningGateError, compile_planning_gate_pack, evaluate_planning_gate_pack, write_cross_artifact_review
from coherence.planning.handoff import HandoffError, build_handoff, write_handoff
from coherence.planning.model import PlanningFinding, PlanningReport
from coherence.planning.run import planning_report_digest
from coherence.planning.review import GeneratedTaskReviewInput
from coherence.planning.session import legal_actions_session, start_session

pytestmark = pytest.mark.unit


def test_missing_cross_artifact_review_blocks_handoff(tmp_path: Path) -> None:
    from tests.unit.coherence.test_planning_gates import _write_current_planning_evidence
    from coherence.planning.cli import _read_report

    _write_current_planning_evidence(tmp_path)
    run_dir = tmp_path / ".factory/planning/run-001"
    (run_dir / "cross-artifact-review.json").unlink(missing_ok=True)
    evaluate_planning_gate_pack(tmp_path, "run-001", compile_planning_gate_pack("FEAT-017", "v1"))
    with pytest.raises(HandoffError):
        build_handoff(tmp_path, _read_report(run_dir / "report.json", "run-001"))


@pytest.mark.parametrize("production,validation", [(True, False), (False, True)])
def test_cross_artifact_review_blocks_missing_sr_then_allows_current_relations(
    tmp_path: Path, production: bool, validation: bool, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from coherence.planning.cli import _read_report
    from coherence.planning.handoff import validate_handoff
    from tests.unit.coherence.test_planning_gates import _write_current_planning_evidence

    _write_current_planning_evidence(tmp_path)
    run_id = "run-001"
    run_dir = tmp_path / ".factory/planning" / run_id
    task_path = tmp_path / "tasks/T-001.md"
    task_path.parent.mkdir()
    task_path.write_text("---\nid: T-001\ntitle: Behavior\nstatus: todo\ndod: []\n---\nImplement behavior.\n", encoding="utf-8")
    source = tmp_path / "src/feature.py"
    test = tmp_path / "tests/test_feature.py"
    source.parent.mkdir()
    test.parent.mkdir()
    source.write_text("def behavior():\n    return 1\n", encoding="utf-8")
    helper = tmp_path / "src/helper.py"
    helper.write_text("VALUE = 1\n", encoding="utf-8")
    test.write_text("def test_behavior():\n    assert True\n", encoding="utf-8")
    requirement = tmp_path / "requirements/SR-001.md"
    requirement.write_text(
        "---\nid: SR-001\ntitle: Behavior\nstatement: Behavior is traced.\ndomain: behavioral\n"
        "implemented_by:\n  - path: src/feature.py\n    symbol: feature:behavior\n"
        "verified_by:\n  - path: tests/test_feature.py\n    test: tests/test_feature.py::test_behavior\n---\n",
        encoding="utf-8",
    )
    write_sr_decision(tmp_path, run_id, "SR-001", _sha(requirement), "approve", "human", CONSENT_PHRASE, "Reviewed current relations.")
    raw = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    raw["artifacts"].append({"path": "tasks/T-001.md", "sha256": _sha(task_path)})
    (run_dir / "report.json").write_text(json.dumps(raw), encoding="utf-8")
    decision = json.loads((run_dir / "review-decision.json").read_text(encoding="utf-8"))
    decision.update(report_sha256=planning_report_digest(raw), reviewed_artifacts=[item["path"] for item in raw["artifacts"]])
    (run_dir / "review-decision.json").write_text(json.dumps(decision), encoding="utf-8")
    report = _read_report(run_dir / "report.json", run_id)
    pack = compile_planning_gate_pack("FEAT-017", "v1")

    def no_process(*args: object, **kwargs: object) -> None:
        pytest.fail("planning cross-artifact review must not launch a process")

    monkeypatch.setattr(subprocess, "run", no_process)
    with pytest.raises(PlanningGateError):
        write_cross_artifact_review(tmp_path, run_id, {})
    missing = GeneratedTaskReviewInput("T-001", ("src/feature.py",), production, validation, None)
    blocked = write_cross_artifact_review(tmp_path, run_id, {"tasks/T-001.md": missing})
    assert isinstance(blocked["review"], dict)
    assert blocked["review"]["findings"][0]["code"] == "TASK_SR_DECLARATION_MISSING"
    evaluate_planning_gate_pack(tmp_path, run_id, pack)
    with pytest.raises(HandoffError):
        build_handoff(tmp_path, report)

    valid = GeneratedTaskReviewInput("T-001", ("src/feature.py", "src/helper.py"), production, validation, ("SR-001",))
    write_cross_artifact_review(tmp_path, run_id, {"tasks/T-001.md": valid})
    review_path = run_dir / "cross-artifact-review.json"
    malformed = json.loads(review_path.read_text(encoding="utf-8"))
    del malformed["tasks"]["tasks/T-001.md"]["changes_validation"]
    review_path.write_text(json.dumps(malformed), encoding="utf-8")
    evaluate_planning_gate_pack(tmp_path, run_id, pack)
    with pytest.raises(HandoffError):
        build_handoff(tmp_path, report)
    write_cross_artifact_review(tmp_path, run_id, {"tasks/T-001.md": valid})
    evaluate_planning_gate_pack(tmp_path, run_id, pack)
    handoff = build_handoff(tmp_path, report)
    path, _ = write_handoff(tmp_path, handoff)
    assert validate_handoff(tmp_path, path) == handoff

    helper.write_text("VALUE = 2\n", encoding="utf-8")
    with pytest.raises(HandoffError):
        validate_handoff(tmp_path, path)
    helper.write_text("VALUE = 1\n", encoding="utf-8")

    # Even a still-resolving symbol with changed bytes invalidates review evidence.
    source.write_text("def behavior():\n    return 2\n", encoding="utf-8")
    with pytest.raises(HandoffError):
        validate_handoff(tmp_path, path)
    evaluate_planning_gate_pack(tmp_path, run_id, pack)
    with pytest.raises(HandoffError):
        build_handoff(tmp_path, report)

    # A fresh review of a now-dangling relation is also blocking.
    source.write_text("def renamed():\n    return 2\n", encoding="utf-8")
    dangling = write_cross_artifact_review(tmp_path, run_id, {"tasks/T-001.md": valid})
    assert isinstance(dangling["review"], dict)
    assert "RELATION_DANGLING" in {item["code"] for item in dangling["review"]["findings"]}
    evaluate_planning_gate_pack(tmp_path, run_id, pack)
    with pytest.raises(HandoffError):
        build_handoff(tmp_path, report)

    # Malformed canonical metadata must fail the gate, not crash evaluation.
    requirement.write_text(requirement.read_text(encoding="utf-8").replace(
        "domain: behavioral", "domain: behavioral\nbinding: malformed",
    ), encoding="utf-8")
    result = evaluate_planning_gate_pack(tmp_path, run_id, pack)
    assert isinstance(result["executions"], list)
    assert result["executions"][-1]["status"] == "fail"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _review_fixture(root: Path, *, decision: dict[str, object] | None = None) -> Path:
    run_id = "review-negative"
    start_session(root, run_id, "Review evidence")
    req = root / "requirements/SR-001.md"
    feature = root / "docs/features/FEAT-017.md"
    spec = root / "docs/spec.md"
    plan = root / "docs/plan.md"
    req.parent.mkdir(parents=True)
    feature.parent.mkdir(parents=True)
    req.write_text("---\nid: SR-001\n---\nRequirement.\n", encoding="utf-8")
    feature.write_text("---\nid: FEAT-017\nrequirements: [SR-001]\n---\n", encoding="utf-8")
    spec.write_text("spec", encoding="utf-8")
    plan.write_text("plan", encoding="utf-8")
    write_artifact_manifest(root, run_id, build_artifact_manifest(root, run_id, [
        {"kind": "requirements", "path": "requirements/SR-001.md"},
        {"kind": "spec", "path": "docs/spec.md"}, {"kind": "plan", "path": "docs/plan.md"},
    ]))
    write_sr_decision(root, run_id, "SR-001", _sha(req), "approve", "human", CONSENT_PHRASE, "Reviewed.")
    run_dir = root / ".factory/planning" / run_id
    run_dir.joinpath("spec-review.json").write_text('{"status":"pass"}', encoding="utf-8")
    run_dir.joinpath("plan-review.json").write_text('{"status":"pass"}', encoding="utf-8")
    artifacts = [{"path": "docs/plan.md", "sha256": _sha(plan)}, {"path": "docs/spec.md", "sha256": _sha(spec)}]
    report = {"schema": 1, "run_id": run_id, "ok": True, "artifacts": artifacts,
              "findings": [], "next_actions": [], "review_required": True, "suggestion": None}
    run_dir.joinpath("report.json").write_text(json.dumps(report), encoding="utf-8")
    if decision is not None:
        run_dir.joinpath("review-decision.json").write_text(json.dumps(decision), encoding="utf-8")
    return run_dir


@pytest.mark.parametrize("decision", [None, {}, {"decision": "reject"}])
def test_review_marker_never_authorizes_gate_without_current_human_decision(
    tmp_path: Path, decision: dict[str, object] | None,
) -> None:
    run_dir = _review_fixture(tmp_path, decision=decision)
    if decision == {"decision": "reject"}:
        report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
        (run_dir / "review-decision.json").write_text(json.dumps({
            "schema": 1, "run_id": "review-negative", "decision": "reject", "reviewer": "human",
            "reason": "Rejected the reviewed planning evidence.",
            "reviewed_artifacts": ["docs/plan.md", "docs/spec.md"],
            "report_sha256": planning_report_digest(report),
        }), encoding="utf-8")
    projection = legal_actions_session(tmp_path, "review-negative")
    assert projection["legal_next_actions"] != ["run-planning-gates"]
    if decision is not None:
        assert projection["blocked"] is True


def test_refreshed_manifest_cannot_hide_mutated_reviewed_bytes(tmp_path: Path) -> None:
    _review_fixture(tmp_path, decision={
        "schema": 1, "run_id": "review-negative", "decision": "approve", "reviewer": "human",
        "reason": "Reviewed.", "reviewed_artifacts": ["docs/plan.md", "docs/spec.md"],
        "report_sha256": "placeholder",
    })
    run_dir = tmp_path / ".factory/planning/review-negative"
    report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    report_digest = planning_report_digest(report)
    decision = json.loads((run_dir / "review-decision.json").read_text(encoding="utf-8"))
    decision["report_sha256"] = report_digest
    (run_dir / "review-decision.json").write_text(json.dumps(decision), encoding="utf-8")
    (tmp_path / "docs/spec.md").write_text("mutated", encoding="utf-8")
    write_artifact_manifest(tmp_path, "review-negative", build_artifact_manifest(tmp_path, "review-negative", [
        {"kind": "requirements", "path": "requirements/SR-001.md"},
        {"kind": "spec", "path": "docs/spec.md"}, {"kind": "plan", "path": "docs/plan.md"},
    ]))
    projection = legal_actions_session(tmp_path, "review-negative")
    assert projection["blocked"] is True
    assert projection["legal_next_actions"] != ["run-planning-gates"]


def test_legal_actions_progress_through_absent_durable_evidence(tmp_path: Path) -> None:
    run_id = "staged-proof"
    start_session(tmp_path, run_id, "Stage the closure")
    assert legal_actions_session(tmp_path, run_id)["legal_next_actions"] == ["author-requirements"]
    requirement = tmp_path / "requirements/SR-001.md"
    feature = tmp_path / "docs/features/FEAT-017.md"
    requirement.parent.mkdir(parents=True)
    feature.parent.mkdir(parents=True)
    requirement.write_text("---\nid: SR-001\n---\nRequirement.\n", encoding="utf-8")
    feature.write_text("---\nid: FEAT-017\nrequirements: [SR-001]\n---\n", encoding="utf-8")
    write_artifact_manifest(tmp_path, run_id, build_artifact_manifest(tmp_path, run_id, [
        {"kind": "requirements", "path": "requirements/SR-001.md"},
    ]))
    assert legal_actions_session(tmp_path, run_id)["legal_next_actions"] == ["record-sr-consent"]
    write_sr_decision(tmp_path, run_id, "SR-001", _sha(requirement), "approve", "human", CONSENT_PHRASE, "Reviewed.")
    spec = tmp_path / "docs/spec.md"
    plan = tmp_path / "docs/plan.md"
    spec.write_text("spec", encoding="utf-8")
    plan.write_text("plan", encoding="utf-8")
    write_artifact_manifest(tmp_path, run_id, build_artifact_manifest(tmp_path, run_id, [
        {"kind": "requirements", "path": "requirements/SR-001.md"},
        {"kind": "spec", "path": "docs/spec.md"}, {"kind": "plan", "path": "docs/plan.md"},
    ]))
    assert legal_actions_session(tmp_path, run_id)["legal_next_actions"] == ["review-spec"]
    run_dir = tmp_path / ".factory/planning" / run_id
    run_dir.joinpath("spec-review.json").write_text('{"status":"pass"}', encoding="utf-8")
    artifacts = ({"path": "docs/plan.md", "sha256": _sha(plan)}, {"path": "docs/spec.md", "sha256": _sha(spec)})
    report = {"schema": 1, "run_id": run_id, "ok": True, "artifacts": list(artifacts),
              "findings": [], "next_actions": [], "review_required": True, "suggestion": None}
    run_dir.joinpath("report.json").write_text(json.dumps(report), encoding="utf-8")
    run_dir.joinpath("review-decision.json").write_text(json.dumps({
        "schema": 1, "run_id": run_id, "decision": "approve", "reviewer": "human",
        "reason": "Reviewed.", "reviewed_artifacts": [item["path"] for item in artifacts],
        "report_sha256": planning_report_digest(report),
    }), encoding="utf-8")
    assert legal_actions_session(tmp_path, run_id)["legal_next_actions"] == ["review-plan"]
    run_dir.joinpath("plan-review.json").write_text('{"status":"pass"}', encoding="utf-8")
    assert legal_actions_session(tmp_path, run_id)["legal_next_actions"] == ["run-planning-gates"]


def test_coordinated_closure_is_non_executing_and_ends_at_inspect_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = "closure-proof"
    start_session(tmp_path, run_id, "Prove the planning closure")

    requirement = tmp_path / "requirements" / "SR-001.md"
    feature = tmp_path / "docs" / "features" / "FEAT-017.md"
    spec = tmp_path / "docs" / "spec.md"
    plan = tmp_path / "docs" / "plan.md"
    task = tmp_path / "tasks" / "T-001-proof.md"
    for path in (requirement, feature, spec, plan, task):
        path.parent.mkdir(parents=True, exist_ok=True)
    requirement.write_text("---\nid: SR-001\n---\nCurrent requirement.\n", encoding="utf-8")
    feature.write_text("---\nid: FEAT-017\nrequirements: [SR-001]\n---\n", encoding="utf-8")
    spec.write_text("---\nid: SPEC-1\n---\nAuthored specification.\n", encoding="utf-8")
    plan.write_text("---\nid: PLAN-1\n---\nAuthored implementation plan.\n", encoding="utf-8")
    task.write_text("---\nid: T-001\ntitle: Documentation\nstatus: todo\ndod: []\n---\nDocument the plan.\n", encoding="utf-8")

    artifacts = [
        {"kind": kind, "path": path.relative_to(tmp_path).as_posix()}
        for kind, path in (("requirements", requirement), ("feature", feature),
                           ("spec", spec), ("plan", plan), ("task", task))
    ]
    artifacts.sort(key=lambda item: item["path"])
    write_artifact_manifest(tmp_path, run_id, build_artifact_manifest(tmp_path, run_id, artifacts))
    write_sr_decision(
        tmp_path, run_id, "SR-001", _sha(requirement), "approve", "human", CONSENT_PHRASE,
        "Independently reviewed the current requirement.",
    )
    (tmp_path / ".factory" / "planning" / run_id / "requirement-consent.json").write_text(
        json.dumps({"schema": 1, "run_id": run_id, "decision": "approve", "reviewer": "human",
                    "reason": "Reviewed requirements.", "requirements": ["SR-001"]}),
        encoding="utf-8",
    )

    report = PlanningReport(
        1, run_id, True,
        tuple({"path": item["path"], "sha256": _sha(tmp_path / item["path"])} for item in artifacts),
        (PlanningFinding("NOTE", "warning", "task", "clean task/relation review"),),
        (), True, None,
    )
    run_dir = tmp_path / ".factory" / "planning" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    raw_report = report.to_dict()
    (run_dir / "report.json").write_text(json.dumps(raw_report), encoding="utf-8")
    (run_dir / "review-decision.json").write_text(json.dumps({
        "schema": 1, "run_id": run_id, "decision": "approve", "reviewer": "human",
        "reason": "Reviewed authored spec, plan, and task relations.",
        "reviewed_artifacts": [item["path"] for item in artifacts],
        "report_sha256": planning_report_digest(raw_report),
    }), encoding="utf-8")

    implementation_gate_calls: list[object] = []
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: implementation_gate_calls.append(args))
    write_cross_artifact_review(tmp_path, run_id, {
        "tasks/T-001-proof.md": GeneratedTaskReviewInput("T-001", ("docs/plan.md",), False, False, None),
    })
    pack = compile_planning_gate_pack("FEAT-017", "v1")
    evaluate_planning_gate_pack(tmp_path, run_id, pack)
    handoff = build_handoff(tmp_path, report, workflow="standard-development")
    write_handoff(tmp_path, handoff)
    (run_dir / "spec-review.json").write_text('{"status":"pass"}', encoding="utf-8")
    (run_dir / "plan-review.json").write_text('{"status":"pass"}', encoding="utf-8")

    projection = legal_actions_session(tmp_path, run_id)
    assert projection["legal_next_actions"] == ["inspect-handoff"]
    assert projection["starts_automatically"] is False
    assert implementation_gate_calls == []

    # Handoff authority is invalidated by a source mutation.
    plan.write_text("mutated plan\n", encoding="utf-8")
    mutated = legal_actions_session(tmp_path, run_id)
    assert mutated["legal_next_actions"] != ["inspect-handoff"]
