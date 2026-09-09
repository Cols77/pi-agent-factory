from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

import coherence.planning.session as session_module
from coherence.planning.artifacts import build_artifact_manifest, write_artifact_manifest
from coherence.planning.consent import CONSENT_PHRASE, write_sr_decision
from coherence.planning.gates import compile_planning_gate_pack, evaluate_planning_gate_pack
from coherence.planning.handoff import build_handoff, write_handoff
from coherence.planning.lifecycle import LifecycleEvidence
from coherence.planning.model import PlanningFinding, PlanningReport
from coherence.planning.run import planning_report_digest
from coherence.planning.session import legal_actions_session, start_session

pytestmark = pytest.mark.unit


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    task.write_text("---\nid: T-001\n---\nClean task/relation evidence.\n", encoding="utf-8")

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
    pack = compile_planning_gate_pack("FEAT-017", "v1")
    evaluate_planning_gate_pack(tmp_path, run_id, pack)
    handoff = build_handoff(tmp_path, report, workflow="standard-development")
    write_handoff(tmp_path, handoff)

    # The current loader intentionally does not infer approvals from mere files;
    # feed the clean, independently reviewed state into the real projector.
    original_loader = session_module._lifecycle_evidence

    def clean_evidence(root: Path, session: object) -> LifecycleEvidence:
        evidence = original_loader(root, session)  # type: ignore[arg-type]
        return replace(evidence, consent_status="valid", spec_review_status="valid",
                       plan_review_status="valid", gate_status="valid")

    monkeypatch.setattr(session_module, "_lifecycle_evidence", clean_evidence)
    projection = legal_actions_session(tmp_path, run_id)
    assert projection["legal_next_actions"] == ["inspect-handoff"]
    assert projection["starts_automatically"] is False
    assert implementation_gate_calls == []

    # Handoff authority is invalidated by a source mutation.
    plan.write_text("mutated plan\n", encoding="utf-8")
    mutated = legal_actions_session(tmp_path, run_id)
    assert mutated["legal_next_actions"] != ["inspect-handoff"]
