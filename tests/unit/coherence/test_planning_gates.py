from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from coherence.cli import main
from coherence.planning.consent import CONSENT_PHRASE, write_sr_decision
from coherence.planning.gates import (
    PlanningGateError,
    _validate_feat17_bundle_members,
    compile_planning_gate_pack,
    evaluate_planning_gate_pack,
    validate_planning_gate_result,
)
from coherence.planning.run import planning_report_digest

pytestmark = pytest.mark.unit

_DOSSIER_MEMBERS = [
    "feat:FEAT-017",
    "spec:docs/superpowers/specs/2026-08-27-feat17-planning-bootstrap-design.md",
    "plan:docs/superpowers/plans/2026-08-27-feat17-planning-workflow-plan.md",
    "task:T-032",
    "task:T-045",
]
_OWNED_IDS = ["SR-043", "SR-044", "SR-051", "SR-052", "SR-053", "SR-054", "SR-055"]


def test_feat17_bundle_accepts_owned_requirements_and_extra_dossier_refs() -> None:
    members = [*_DOSSIER_MEMBERS, *(f"sr:{req_id}" for req_id in _OWNED_IDS)]
    assert _validate_feat17_bundle_members(members, _OWNED_IDS) == (
        True, "FEAT-017 bundle ownership is current",
    )


def test_feat17_bundle_rejects_non_owned_requirements() -> None:
    members = [*_DOSSIER_MEMBERS, *(f"sr:{req_id}" for req_id in [*_OWNED_IDS, "SR-050"])]
    assert _validate_feat17_bundle_members(members, _OWNED_IDS) == (
        False, "FEAT-017 bundle contains non-owned requirement(s): SR-050",
    )


def test_feat17_bundle_rejects_duplicate_members() -> None:
    members = [*_DOSSIER_MEMBERS, *(f"sr:{req_id}" for req_id in _OWNED_IDS), "sr:SR-055"]
    assert _validate_feat17_bundle_members(members, _OWNED_IDS) == (
        False, "FEAT-017 bundle has duplicate members",
    )


def test_feat17_bundle_rejects_non_list_members() -> None:
    assert _validate_feat17_bundle_members("feat:FEAT-017", _OWNED_IDS) == (
        False, "FEAT-017 bundle has invalid members",
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_current_planning_evidence(root: Path, run_id: str = "run-001") -> None:
    plan = root / "docs" / "plan.md"
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text("# plan\n", encoding="utf-8")
    run_dir = root / ".factory" / "planning" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "schema": 1,
        "run_id": run_id,
        "ok": True,
        "artifacts": [{"path": "docs/plan.md", "sha256": _sha(plan)}],
        "findings": [],
        "next_actions": [],
        "review_required": True,
        "suggestion": None,
    }
    (run_dir / "report.json").write_text(json.dumps(report), encoding="utf-8")
    decision = {
        "schema": 1,
        "run_id": run_id,
        "decision": "approve",
        "reviewer": "human",
        "reason": "Reviewed planning evidence.",
        "reviewed_artifacts": ["docs/plan.md"],
        "report_sha256": planning_report_digest(report),
    }
    (run_dir / "review-decision.json").write_text(json.dumps(decision), encoding="utf-8")
    feature = root / "docs" / "features" / "FEAT-017.md"
    feature.parent.mkdir(exist_ok=True)
    feature.write_text(
        "---\nid: FEAT-017\nrequirements: [SR-001]\n---\n",
        encoding="utf-8",
    )
    requirement = root / "requirements" / "SR-001.md"
    requirement.parent.mkdir(exist_ok=True)
    requirement.write_text("---\nid: SR-001\n---\nCurrent requirement.\n", encoding="utf-8")
    requirement_digest = _sha(requirement)
    write_sr_decision(
        root, run_id, "SR-001", requirement_digest, "approve", "human", CONSENT_PHRASE,
        "Independently reviewed the current requirement.",
    )
    (run_dir / "requirement-consent.json").write_text(
        json.dumps({
            "schema": 1,
            "run_id": run_id,
            "decision": "approve",
            "reviewer": "human",
            "reason": "Planning requirements were reviewed.",
            "requirements": ["SR-001"],
        }),
        encoding="utf-8",
    )


def _publish_result(root: Path, payload: dict[str, object], run_id: str = "run-001") -> None:
    payload.pop("result_sha256", None)
    encoded = (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    results = root / ".factory" / "planning" / run_id / "planning-gate-results"
    results.mkdir(exist_ok=True)
    (results / f"{digest}.json").write_bytes(encoded)
    (root / ".factory" / "planning" / run_id / "planning-gate-result.json").write_bytes(encoded)


def test_compiled_pack_is_deterministic_versioned_and_complete() -> None:
    first = compile_planning_gate_pack("FEAT-017", "v1")
    assert first == compile_planning_gate_pack("FEAT-017", "v1")
    assert first["sha256"] == hashlib.sha256(
        json.dumps({key: value for key, value in first.items() if key != "sha256"}, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    gates = first["gates"]
    assert isinstance(gates, list) and all(isinstance(gate, dict) for gate in gates)
    assert {"id", "stage", "required", "resolver", "dependencies", "expected_evidence", "failure_behavior"} <= set(gates[0])
    assert all(gate["dependencies"] == sorted(gate["dependencies"]) for gate in gates)
    with pytest.raises(PlanningGateError):
        compile_planning_gate_pack("FEAT-999", "v1")
    with pytest.raises(PlanningGateError):
        compile_planning_gate_pack("FEAT-017", "v2")


def test_result_is_hash_bound_current_and_fails_closed_on_missing_or_mutated_evidence(tmp_path: Path) -> None:
    _write_current_planning_evidence(tmp_path)
    pack = compile_planning_gate_pack("FEAT-017", "v1")
    result = evaluate_planning_gate_pack(tmp_path, "run-001", pack)
    assert validate_planning_gate_result(tmp_path, "run-001", pack) == result
    assert result["result_sha256"] == _sha(tmp_path / ".factory/planning/run-001/planning-gate-result.json")

    tampered = dict(result)
    executions = tampered["executions"]
    assert isinstance(executions, list)
    tampered["executions"] = executions[:-1]
    _publish_result(tmp_path, tampered)
    with pytest.raises(PlanningGateError):
        validate_planning_gate_result(tmp_path, "run-001", pack)

    evaluate_planning_gate_pack(tmp_path, "run-001", pack)
    (tmp_path / "docs" / "plan.md").write_text("# changed\n", encoding="utf-8")
    with pytest.raises(PlanningGateError):
        validate_planning_gate_result(tmp_path, "run-001", pack)


def test_required_failed_unevidenced_or_downgraded_execution_cannot_validate(tmp_path: Path) -> None:
    _write_current_planning_evidence(tmp_path)
    pack = compile_planning_gate_pack("FEAT-017", "v1")
    result = evaluate_planning_gate_pack(tmp_path, "run-001", pack)
    for field, value in (("status", "fail"), ("required", False), ("evidence", [])):
        broken = json.loads(json.dumps(result))
        broken["executions"][0][field] = value
        _publish_result(tmp_path, broken)
        with pytest.raises(PlanningGateError):
            validate_planning_gate_result(tmp_path, "run-001", pack)


def test_error_finding_or_empty_or_mismatched_requirement_consent_blocks_gate_result(tmp_path: Path) -> None:
    _write_current_planning_evidence(tmp_path)
    pack = compile_planning_gate_pack("FEAT-017", "v1")
    run_dir = tmp_path / ".factory" / "planning" / "run-001"

    report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    report["findings"] = [{"code": "CONTRADICTION", "severity": "error", "subject": "plan", "detail": "blocking"}]
    (run_dir / "report.json").write_text(json.dumps(report), encoding="utf-8")
    (run_dir / "review-decision.json").write_text(json.dumps({
        **json.loads((run_dir / "review-decision.json").read_text(encoding="utf-8")),
        "report_sha256": planning_report_digest(report),
    }), encoding="utf-8")
    result = evaluate_planning_gate_pack(tmp_path, "run-001", pack)
    assert result["executions"][0]["status"] == "fail"
    with pytest.raises(PlanningGateError):
        validate_planning_gate_result(tmp_path, "run-001", pack)

    _write_current_planning_evidence(tmp_path)
    (run_dir / "requirement-consent.json").write_text(json.dumps({
        "schema": 1, "run_id": "run-001", "decision": "approve", "reviewer": "human",
        "reason": "No coverage.", "requirements": [],
    }), encoding="utf-8")
    result = evaluate_planning_gate_pack(tmp_path, "run-001", pack)
    assert result["executions"][2]["status"] == "fail"
    with pytest.raises(PlanningGateError):
        validate_planning_gate_result(tmp_path, "run-001", pack)

    (run_dir / "requirement-consent.json").write_text(json.dumps({
        "schema": 1, "run_id": "run-001", "decision": "approve", "reviewer": "human",
        "reason": "Wrong coverage.", "requirements": ["SR-999"],
    }), encoding="utf-8")
    result = evaluate_planning_gate_pack(tmp_path, "run-001", pack)
    assert result["executions"][2]["status"] == "fail"


@pytest.mark.parametrize("rehash", [False, True])
def test_pack_rejects_exact_type_confusion_and_tampered_digest_combinations(tmp_path: Path, rehash: bool) -> None:
    _write_current_planning_evidence(tmp_path)
    valid = compile_planning_gate_pack("FEAT-017", "v1")
    for mutation in (
        lambda pack: pack.__setitem__("schema", True),
        lambda pack: pack["gates"][0].__setitem__("required", 1),
        lambda pack: pack["gates"][0].__setitem__("failure_behavior", "continue"),
        lambda pack: pack.__setitem__("extra", "unrecognized"),
        lambda pack: pack["gates"][0].__setitem__("extra", "unrecognized"),
        lambda pack: pack.__setitem__("sha256", "0" * 64),
    ):
        pack = json.loads(json.dumps(valid))
        mutation(pack)
        if rehash:
            if pack["sha256"] != valid["sha256"]:
                continue
            pack["sha256"] = hashlib.sha256(json.dumps(
                {key: value for key, value in pack.items() if key != "sha256"},
                sort_keys=True, separators=(",", ":"),
            ).encode()).hexdigest()
        with pytest.raises(PlanningGateError):
            evaluate_planning_gate_pack(tmp_path, "run-001", pack)


def test_current_per_sr_consent_suffices_without_legacy_record(tmp_path: Path) -> None:
    _write_current_planning_evidence(tmp_path)
    (tmp_path / ".factory/planning/run-001/requirement-consent.json").unlink()
    pack = compile_planning_gate_pack("FEAT-017", "v1")
    result = evaluate_planning_gate_pack(tmp_path, "run-001", pack)
    assert validate_planning_gate_result(tmp_path, "run-001", pack) == result


@pytest.mark.parametrize("mutation", ["missing", "stale", "new-requirement", "empty-feature"])
def test_consent_must_cover_every_current_feature_requirement(tmp_path: Path, mutation: str) -> None:
    _write_current_planning_evidence(tmp_path)
    if mutation == "missing":
        (tmp_path / ".factory/planning/run-001/consent/SR-001.json").unlink()
    elif mutation == "stale":
        requirement = tmp_path / "requirements/SR-001.md"
        requirement.write_text(requirement.read_text(encoding="utf-8") + "Changed claim.\n", encoding="utf-8")
    else:
        ids = "[SR-001, SR-002]" if mutation == "new-requirement" else "[]"
        (tmp_path / "docs/features/FEAT-017.md").write_text(
            f"---\nid: FEAT-017\nrequirements: {ids}\n---\n", encoding="utf-8",
        )
    pack = compile_planning_gate_pack("FEAT-017", "v1")
    result = evaluate_planning_gate_pack(tmp_path, "run-001", pack)
    assert result["executions"][2]["status"] == "fail"
    with pytest.raises(PlanningGateError):
        validate_planning_gate_result(tmp_path, "run-001", pack)


def test_cli_runs_only_planning_gate_pack_without_subprocess(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    _write_current_planning_evidence(tmp_path)

    def _forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("planning gate command must not invoke subprocesses")

    monkeypatch.setattr(subprocess, "run", _forbidden)
    assert main([
        "plan", "run-planning-gates", "--project-root", str(tmp_path), "--run-id", "run-001", "--json",
    ]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["action"] == "run-planning-gates"
    assert payload["ok"] is True
