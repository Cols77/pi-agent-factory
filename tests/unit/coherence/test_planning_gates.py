from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from coherence.cli import main
from coherence.planning.consent import CONSENT_PHRASE, write_sr_decision
from coherence.planning.artifacts import build_artifact_manifest, write_artifact_manifest
from coherence.planning.gates import (
    PlanningGateError,
    _validate_feat17_bundle_members,
    compile_planning_gate_pack,
    evaluate_planning_gate_pack,
    validate_planning_gate_result,
    write_cross_artifact_review,
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


def _capture_intent(root: Path, run_id: str) -> None:
    """Capture the run intent through the session API.

    The lifecycle projector replays the session journal and rejects a hand-written
    ``.intent/intent.json`` as STALE_INTENT_SNAPSHOT, so the fixture must drive the
    same capture path the host uses. Repeated calls on one root are a no-op.
    """
    from coherence.planning.intent import IntentError, read_intent
    from coherence.planning.session import append_session_answer, start_session

    journal = root / ".factory" / "planning" / run_id / "capture" / "events.jsonl"
    if not journal.exists():
        start_session(root, run_id, "Plan the goal")
    else:
        try:
            document = read_intent(
                root / ".factory" / "planning" / run_id / "intent.json",
                project_root=root,
            )
        except (IntentError, OSError, ValueError):
            document = None
        if document is not None and any(answer.id == "goal" for answer in document.answers):
            return
    append_session_answer(root, run_id, "goal", "What is the goal?", "Plan the goal")


def _write_current_planning_evidence(root: Path, run_id: str = "run-001") -> None:
    plan = root / "docs" / "plan.md"
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text("---\nspec_ref: SPEC-1\n---\n# plan\nclaim:goal\n", encoding="utf-8")
    spec = root / "docs/spec.md"
    spec.write_text("---\nid: SPEC-1\ntitle: Specification\nstatus: draft\n---\n# Goal\nclaim:goal\n", encoding="utf-8")
    _capture_intent(root, run_id)
    intent = root / ".intent" / "intent.json"
    intent.parent.mkdir(parents=True, exist_ok=True)
    intent.write_bytes(
        (root / ".factory" / "planning" / run_id / "intent.json").read_bytes()
    )
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
        "---\nid: FEAT-017\ntitle: Planning gate coverage\nrequirements: [SR-001]\n---\n",
        encoding="utf-8",
    )
    requirement = root / "requirements" / "SR-001.md"
    requirement.parent.mkdir(exist_ok=True)
    requirement.write_text("---\nid: SR-001\ntitle: Goal\nstatement: Plan the goal.\ndomain: behavioral\nupstream: []\nsource: docs/spec.md#Goal\n---\nCurrent requirement.\n", encoding="utf-8")
    bundle = root / "bundles/FEAT-017.json"
    bundle.parent.mkdir(exist_ok=True)
    bundle.write_text(json.dumps({"id": "FEAT-017", "members": ["feat:FEAT-017", "sr:SR-001"]}), encoding="utf-8")
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
    _refresh_full_review(root, run_id)
    write_cross_artifact_review(root, run_id, {})


_FULL_PLANNING_SOURCES = (
    ("intent", ".intent/intent.json"),
    ("spec", "docs/spec.md"),
    ("plan", "docs/plan.md"),
    ("feature", "docs/features/FEAT-017.md"),
    ("bundle", "bundles/FEAT-017.json"),
    ("requirements", "requirements/SR-001.md"),
)


def _refresh_artifact_evidence(
    root: Path,
    run_id: str = "run-001",
    entries: tuple[tuple[str, str], ...] | None = None,
) -> list[str]:
    """Publish the artifact manifest and re-bind report/review evidence to current bytes.

    The planning gate requires the manifest to cover the complete source set and the
    report to hash exactly those current bytes, so any fixture that mutates a planning
    source must call this afterwards rather than replaying stale evidence.
    """
    run_dir = root / ".factory/planning" / run_id
    pairs = _FULL_PLANNING_SOURCES if entries is None else tuple(entries)
    items = [{"kind": kind, "path": path} for kind, path in pairs]
    write_artifact_manifest(root, run_id, build_artifact_manifest(root, run_id, items))
    report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    paths = {item["path"] for item in report["artifacts"]} | {item["path"] for item in items}
    report["artifacts"] = [{"path": path, "sha256": _sha(root / path)} for path in sorted(paths)]
    (run_dir / "report.json").write_text(json.dumps(report), encoding="utf-8")
    decision_path = run_dir / "review-decision.json"
    if decision_path.is_file():
        decision = json.loads(decision_path.read_text(encoding="utf-8"))
        decision.update(report_sha256=planning_report_digest(report), reviewed_artifacts=sorted(paths))
        decision_path.write_text(json.dumps(decision), encoding="utf-8")
    return sorted(paths)


def _refresh_full_review(root: Path, run_id: str = "run-001") -> None:
    """Explicit fixture review of the complete current planning source set."""
    _refresh_artifact_evidence(root, run_id)


@pytest.mark.parametrize("mutation", [
    "missing-bundle", "wrong-members", "duplicate-members", "missing-intent", "intent-mismatch",
    "spec-mismatch", "plan-mismatch", "missing-manifest", "extra-consent", "source-anchor",
])
def test_full_planning_artifacts_are_required_even_without_production_tasks(tmp_path: Path, mutation: str) -> None:
    _write_current_planning_evidence(tmp_path)
    if mutation.startswith("missing-"):
        path = {"missing-bundle": "bundles/FEAT-017.json", "missing-intent": ".intent/intent.json",
                "missing-manifest": ".factory/planning/run-001/artifacts.json"}[mutation]
        (tmp_path / path).unlink()
    elif mutation in {"wrong-members", "duplicate-members"}:
        members = ["feat:FEAT-017", "sr:SR-999"] if mutation == "wrong-members" else ["feat:FEAT-017", "sr:SR-001", "sr:SR-001"]
        (tmp_path / "bundles/FEAT-017.json").write_text(json.dumps({"id": "FEAT-017", "members": members}), encoding="utf-8")
    elif mutation == "extra-consent":
        write_sr_decision(tmp_path, "run-001", "SR-999", "0" * 64, "approve", "human", CONSENT_PHRASE, "Unrelated SR.")
    else:
        path, before, after = {
            "intent-mismatch": (".intent/intent.json", '"id": "goal"', '"id": "other"'),
            "spec-mismatch": ("docs/spec.md", "SPEC-1", "SPEC-2"),
            "plan-mismatch": ("docs/plan.md", "SPEC-1", "SPEC-2"),
            "source-anchor": ("requirements/SR-001.md", "#Goal", "#absent"),
        }[mutation]
        target = tmp_path / path
        if mutation == "intent-mismatch":
            payload = json.loads(target.read_text(encoding="utf-8"))
            payload["answers"][0]["id"] = "other"
            target.write_text(json.dumps(payload), encoding="utf-8")
        else:
            original = target.read_text(encoding="utf-8")
            assert before in original
            target.write_text(original.replace(before, after), encoding="utf-8")
    # Replaying neither a stale review nor stale consent can make a changed
    # planning source current; the gate must reject the captured evidence.
    pack = compile_planning_gate_pack("FEAT-017", "v1")
    result = evaluate_planning_gate_pack(tmp_path, "run-001", pack)
    assert result["executions"][-1]["status"] == "fail"
    with pytest.raises(PlanningGateError):
        validate_planning_gate_result(tmp_path, "run-001", pack)


def test_full_gate_evidence_covers_sources_decisions_and_selected_workflow(tmp_path: Path) -> None:
    _write_current_planning_evidence(tmp_path)
    run_dir = tmp_path / ".factory/planning/run-001"
    record = json.loads((run_dir / "cross-artifact-review.json").read_text(encoding="utf-8"))
    assert record["selected_workflow"] == "standard-development"
    pack = compile_planning_gate_pack("FEAT-017", "v1")
    assert record["selected_workflow"] in pack["workflows"]
    assert record["planning_gate_pack_sha256"] == pack["sha256"]
    result = evaluate_planning_gate_pack(tmp_path, "run-001", pack)
    assert validate_planning_gate_result(tmp_path, "run-001", pack) == result
    evidence = {entry["path"]: entry["sha256"] for entry in result["executions"][-1]["evidence"]}
    for path in (".intent/intent.json", "docs/spec.md", "docs/plan.md", "docs/features/FEAT-017.md",
                 "bundles/FEAT-017.json", "requirements/SR-001.md", ".factory/planning/run-001/artifacts.json",
                 ".factory/planning/run-001/consent/SR-001.json", ".factory/planning/run-001/review-decision.json",
                 ".factory/planning/run-001/cross-artifact-review.json"):
        assert evidence[path] == _sha(tmp_path / path)


@pytest.mark.parametrize("spec_ref", ["docs/spec.md", "spec:SPEC-1"])
def test_full_gate_accepts_established_spec_reference_forms(tmp_path: Path, spec_ref: str) -> None:
    _write_current_planning_evidence(tmp_path)
    plan = tmp_path / "docs/plan.md"
    plan.write_text(plan.read_text(encoding="utf-8").replace("spec_ref: SPEC-1", f"spec_ref: {spec_ref}"), encoding="utf-8")
    _refresh_full_review(tmp_path)
    write_cross_artifact_review(tmp_path, "run-001", {})
    pack = compile_planning_gate_pack("FEAT-017", "v1")
    result = evaluate_planning_gate_pack(tmp_path, "run-001", pack)
    assert validate_planning_gate_result(tmp_path, "run-001", pack) == result


@pytest.mark.parametrize("mutation", ["missing-title", "unrelated-claims", "numeric-upstream"])
def test_full_gate_rechecks_fresh_hash_consistent_planning_sources(tmp_path: Path, mutation: str) -> None:
    _write_current_planning_evidence(tmp_path)
    if mutation == "missing-title":
        spec = tmp_path / "docs/spec.md"
        spec.write_text(spec.read_text(encoding="utf-8").replace("title: Specification\n", ""), encoding="utf-8")
    elif mutation == "unrelated-claims":
        for path in (tmp_path / "docs/spec.md", tmp_path / "docs/plan.md"):
            path.write_text(path.read_text(encoding="utf-8").replace("claim:goal", "claim:unrelated"), encoding="utf-8")
    else:
        requirement = tmp_path / "requirements/SR-001.md"
        requirement.write_text(requirement.read_text(encoding="utf-8").replace("upstream: []", "upstream: [123]"), encoding="utf-8")
        write_sr_decision(tmp_path, "run-001", "SR-001", _sha(requirement), "approve", "human", CONSENT_PHRASE, "Reviewed current source.")
    _refresh_full_review(tmp_path)
    write_cross_artifact_review(tmp_path, "run-001", {})
    pack = compile_planning_gate_pack("FEAT-017", "v1")
    result = evaluate_planning_gate_pack(tmp_path, "run-001", pack)
    assert result["executions"][-1]["status"] == "fail"
    with pytest.raises(PlanningGateError):
        validate_planning_gate_result(tmp_path, "run-001", pack)


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


@pytest.mark.parametrize("mutation", ["missing", "json", "schema", "run", "hash", "review", "numeric-ok", "unknown", "tasks"])
def test_cross_artifact_evidence_fails_closed(tmp_path: Path, mutation: str) -> None:
    _write_current_planning_evidence(tmp_path)
    path = tmp_path / ".factory/planning/run-001/cross-artifact-review.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    if mutation == "missing":
        path.unlink()
    elif mutation == "json":
        path.write_text('{"schema":1,"schema":1}', encoding="utf-8")
    else:
        if mutation == "schema":
            record["schema"] = True
        elif mutation == "run":
            record["run_id"] = "another-run"
        elif mutation == "hash":
            record["artifact_hashes"]["docs/plan.md"] = "0" * 64
        elif mutation == "review":
            record["review"]["findings"] = [{"code": "fabricated"}]
        elif mutation == "numeric-ok":
            record["review"]["ok"] = 1
        elif mutation == "unknown":
            record["extra"] = "unsupported"
        elif mutation == "tasks":
            record["tasks"] = []
        path.write_text(json.dumps(record), encoding="utf-8")
    pack = compile_planning_gate_pack("FEAT-017", "v1")
    result = evaluate_planning_gate_pack(tmp_path, "run-001", pack)
    assert isinstance(result["executions"], list)
    assert result["executions"][-1]["status"] == "fail"
    with pytest.raises(PlanningGateError):
        validate_planning_gate_result(tmp_path, "run-001", pack)


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
    assert isinstance(result["executions"], list)
    assert result["executions"][0]["status"] == "fail"
    with pytest.raises(PlanningGateError):
        validate_planning_gate_result(tmp_path, "run-001", pack)

    _write_current_planning_evidence(tmp_path)
    (run_dir / "requirement-consent.json").write_text(json.dumps({
        "schema": 1, "run_id": "run-001", "decision": "approve", "reviewer": "human",
        "reason": "No coverage.", "requirements": [],
    }), encoding="utf-8")
    result = evaluate_planning_gate_pack(tmp_path, "run-001", pack)
    assert isinstance(result["executions"], list)
    assert result["executions"][2]["status"] == "fail"
    with pytest.raises(PlanningGateError):
        validate_planning_gate_result(tmp_path, "run-001", pack)

    (run_dir / "requirement-consent.json").write_text(json.dumps({
        "schema": 1, "run_id": "run-001", "decision": "approve", "reviewer": "human",
        "reason": "Wrong coverage.", "requirements": ["SR-999"],
    }), encoding="utf-8")
    result = evaluate_planning_gate_pack(tmp_path, "run-001", pack)
    assert isinstance(result["executions"], list)
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
    assert isinstance(result["executions"], list)
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
