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
from coherence.planning.session import append_session_answer, legal_actions_session, start_session
from tests.unit.coherence.test_planning_gates import (
    _FULL_PLANNING_SOURCES,
    _refresh_full_review,
)

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


@pytest.mark.parametrize("field", ["implemented_by", "verified_by"])
def test_non_string_relation_paths_cannot_escape_gate_freshness(tmp_path: Path, field: str) -> None:
    from coherence.planning.cli import _read_report
    from tests.unit.coherence.test_planning_gates import _refresh_full_review, _write_current_planning_evidence

    _write_current_planning_evidence(tmp_path)
    run_dir = tmp_path / ".factory/planning/run-001"
    task_path = tmp_path / "tasks/T-001.md"
    task_path.parent.mkdir()
    task_path.write_text("---\nid: T-001\ntitle: Behavior\nstatus: todo\ndod: []\n---\n", encoding="utf-8")
    (tmp_path / "source.json").write_text("{}", encoding="utf-8")
    numeric_target = tmp_path / "123"
    numeric_target.write_text("original validation evidence", encoding="utf-8")
    other_field = "verified_by" if field == "implemented_by" else "implemented_by"
    requirement = tmp_path / "requirements/SR-001.md"
    valid_metadata = (
        "---\nid: SR-001\ntitle: Behavior\nstatement: Behavior is traced.\ndomain: behavioral\nupstream: []\n"
        f"source: docs/spec.md#Goal\n{other_field}:\n  - path: source.json\n{field}:\n  - path: '123'\n---\n"
    )
    requirement.write_text(valid_metadata, encoding="utf-8")
    _refresh_full_review(tmp_path)
    raw_report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    raw_report["artifacts"].append({"path": "tasks/T-001.md", "sha256": _sha(task_path)})
    (run_dir / "report.json").write_text(json.dumps(raw_report), encoding="utf-8")
    decision = json.loads((run_dir / "review-decision.json").read_text(encoding="utf-8"))
    decision.update(report_sha256=planning_report_digest(raw_report), reviewed_artifacts=[item["path"] for item in raw_report["artifacts"]])
    (run_dir / "review-decision.json").write_text(json.dumps(decision), encoding="utf-8")
    tasks = {"tasks/T-001.md": GeneratedTaskReviewInput("T-001", ("source.json",), True, False, ("SR-001",))}
    record = write_cross_artifact_review(tmp_path, "run-001", tasks)
    assert isinstance(record["artifact_hashes"], dict)
    assert record["artifact_hashes"]["123"] == _sha(numeric_target)

    requirement.write_text(valid_metadata.replace("path: '123'", "path: 123"), encoding="utf-8")
    write_sr_decision(tmp_path, "run-001", "SR-001", _sha(requirement), "approve", "human", CONSENT_PHRASE, "Reviewed current requirement.")
    with pytest.raises(PlanningGateError):
        write_cross_artifact_review(tmp_path, "run-001", tasks)

    # Reproduce the old record shape: resolver accepted str(123), while the
    # producer silently excluded that target from its freshness hashes.
    record["artifact_hashes"]["requirements/SR-001.md"] = _sha(requirement)
    del record["artifact_hashes"]["123"]
    (run_dir / "cross-artifact-review.json").write_text(json.dumps(record), encoding="utf-8")
    pack = compile_planning_gate_pack("FEAT-017", "v1")
    report = _read_report(run_dir / "report.json", "run-001")
    for content in ("original validation evidence", "mutated validation evidence"):
        numeric_target.write_text(content, encoding="utf-8")
        result = evaluate_planning_gate_pack(tmp_path, "run-001", pack)
        assert isinstance(result["executions"], list)
        assert result["executions"][-1]["status"] == "fail"
        with pytest.raises(HandoffError):
            build_handoff(tmp_path, report)

    requirement.write_text(valid_metadata, encoding="utf-8")
    write_sr_decision(tmp_path, "run-001", "SR-001", _sha(requirement), "approve", "human", CONSENT_PHRASE, "Reviewed string path.")
    _refresh_full_review(tmp_path)
    write_cross_artifact_review(tmp_path, "run-001", tasks)
    evaluate_planning_gate_pack(tmp_path, "run-001", pack)
    build_handoff(tmp_path, report)
    numeric_target.write_text("another mutation", encoding="utf-8")
    with pytest.raises(HandoffError):
        build_handoff(tmp_path, report)

    backslash_target = tmp_path / "dir" / "target"
    backslash_target.parent.mkdir()
    backslash_target.write_text("backslash target", encoding="utf-8")
    requirement.write_text(valid_metadata.replace("path: '123'", r"path: dir\target"), encoding="utf-8")
    with pytest.raises(PlanningGateError):
        write_cross_artifact_review(tmp_path, "run-001", tasks)
    result = evaluate_planning_gate_pack(tmp_path, "run-001", pack)
    assert result["executions"][-1]["status"] == "fail"
    with pytest.raises(HandoffError):
        build_handoff(tmp_path, report)


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
        "upstream: []\nsource: docs/spec.md#Goal\n"
        "implemented_by:\n  - path: src/feature.py\n    symbol: feature:behavior\n"
        "verified_by:\n  - path: tests/test_feature.py\n    test: tests/test_feature.py::test_behavior\n---\n",
        encoding="utf-8",
    )
    # Rewriting a planning source invalidates the reviewed report: re-bind the manifest,
    # report, and review decision to the current bytes before attesting consent.
    _refresh_full_review(tmp_path, run_id)
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
    """Stage a run whose complete planning source set is current and reviewable.

    Review currency is derived from the full source set, so the fixture must author
    canonically-formed sources and publish a manifest covering every one of them
    before the review evidence can be considered current.
    """
    from tests.unit.coherence.test_planning_gates import _refresh_artifact_evidence

    run_id = "review-negative"
    start_session(root, run_id, "Review evidence")
    # Capture the intent through the session API: the projector replays the journal and
    # rejects a hand-written intent.json as a stale snapshot.
    append_session_answer(root, run_id, "goal", "What is being reviewed?", "Review evidence")
    req = root / "requirements/SR-001.md"
    feature = root / "docs/features/FEAT-017.md"
    spec = root / "docs/spec.md"
    plan = root / "docs/plan.md"
    intent = root / ".intent/intent.json"
    req.parent.mkdir(parents=True)
    feature.parent.mkdir(parents=True)
    intent.parent.mkdir(parents=True, exist_ok=True)
    req.write_text(
        "---\nid: SR-001\ntitle: Review Evidence\nstatement: The evidence is reviewed.\n"
        "domain: behavioral\nupstream: []\nsource: docs/spec.md#Goal\n---\nRequirement.\n",
        encoding="utf-8",
    )
    feature.write_text(
        "---\nid: FEAT-017\ntitle: Review evidence coverage\nrequirements: [SR-001]\n---\n",
        encoding="utf-8",
    )
    spec.write_text(
        "---\nid: SPEC-1\ntitle: Review Specification\nstatus: draft\n---\n"
        "# Goal\nThe goal is reviewed.\n",
        encoding="utf-8",
    )
    plan.write_text(
        "---\nspec_ref: SPEC-1\n---\n# Plan\n\n### Task 1: Review\n\n**Files:**\n"
        "- Create: `docs/review.md`\n\n**Interfaces:**\n- Produces: `goal` support.\n",
        encoding="utf-8",
    )
    bundle = root / "bundles/FEAT-017.json"
    bundle.parent.mkdir(parents=True, exist_ok=True)
    bundle.write_text(
        json.dumps({"id": "FEAT-017", "members": ["feat:FEAT-017", "sr:SR-001"]}),
        encoding="utf-8",
    )
    write_sr_decision(root, run_id, "SR-001", _sha(req), "approve", "human", CONSENT_PHRASE, "Reviewed.")
    run_dir = root / ".factory/planning" / run_id
    run_dir.joinpath("spec-review.json").write_text('{"status":"pass"}', encoding="utf-8")
    run_dir.joinpath("plan-review.json").write_text('{"status":"pass"}', encoding="utf-8")
    artifacts = [
        {"path": "docs/plan.md", "sha256": _sha(plan)},
        {"path": "docs/spec.md", "sha256": _sha(spec)},
    ]
    report = {"schema": 1, "run_id": run_id, "ok": True, "artifacts": artifacts,
              "findings": [], "next_actions": [], "review_required": True, "suggestion": None}
    run_dir.joinpath("report.json").write_text(json.dumps(report), encoding="utf-8")
    _refresh_artifact_evidence(root, run_id)
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


@pytest.mark.parametrize("kind", ["spec", "plan"])
@pytest.mark.parametrize("same_bytes", [False, True])
def test_repointed_manifest_cannot_reuse_review_of_another_path(
    tmp_path: Path, kind: str, same_bytes: bool,
) -> None:
    run_id = "review-negative"
    run_dir = _review_fixture(tmp_path)
    report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    (run_dir / "review-decision.json").write_text(json.dumps({
        "schema": 1, "run_id": run_id, "decision": "approve", "reviewer": "human",
        "reason": "Reviewed.", "reviewed_artifacts": [item["path"] for item in report["artifacts"]],
        "report_sha256": planning_report_digest(report),
    }), encoding="utf-8")
    assert legal_actions_session(tmp_path, run_id)["legal_next_actions"] == ["run-planning-gates"]

    replacement = tmp_path / f"docs/replacement-{kind}.md"
    replacement.write_text(kind if same_bytes else "Unreviewed replacement.", encoding="utf-8")
    artifacts = [
        {"kind": "requirements", "path": "requirements/SR-001.md"},
        {"kind": "spec", "path": "docs/spec.md"},
        {"kind": "plan", "path": "docs/plan.md"},
    ]
    for artifact in artifacts:
        if artifact["kind"] == kind:
            artifact["path"] = replacement.relative_to(tmp_path).as_posix()
    write_artifact_manifest(tmp_path, run_id, build_artifact_manifest(tmp_path, run_id, artifacts))

    projection = legal_actions_session(tmp_path, run_id)
    assert projection["legal_next_actions"] != ["run-planning-gates"]
    assert projection["blocked"] is True


def test_refreshed_manifest_cannot_hide_mutated_reviewed_bytes(tmp_path: Path) -> None:
    from tests.unit.coherence.test_planning_gates import _FULL_PLANNING_SOURCES

    run_dir = _review_fixture(tmp_path)
    report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    (run_dir / "review-decision.json").write_text(json.dumps({
        "schema": 1, "run_id": "review-negative", "decision": "approve", "reviewer": "human",
        "reason": "Reviewed.", "reviewed_artifacts": [item["path"] for item in report["artifacts"]],
        "report_sha256": planning_report_digest(report),
    }), encoding="utf-8")
    (tmp_path / "docs/spec.md").write_text("mutated", encoding="utf-8")
    # A refreshed manifest naming the same complete source set cannot launder the
    # mutation: the reviewed bytes no longer match the report the decision attests.
    write_artifact_manifest(tmp_path, "review-negative", build_artifact_manifest(
        tmp_path, "review-negative",
        [{"kind": kind, "path": path} for kind, path in _FULL_PLANNING_SOURCES],
    ))
    projection = legal_actions_session(tmp_path, "review-negative")
    assert projection["blocked"] is True
    assert projection["legal_next_actions"] != ["run-planning-gates"]


def test_legal_actions_progress_through_absent_durable_evidence(tmp_path: Path) -> None:
    run_id = "staged-proof"
    start_session(tmp_path, run_id, "Stage the closure")
    append_session_answer(tmp_path, run_id, "goal", "What is being staged?", "Stage the closure")
    assert legal_actions_session(tmp_path, run_id)["legal_next_actions"] == ["author-requirements"]
    requirement = tmp_path / "requirements/SR-001.md"
    feature = tmp_path / "docs/features/FEAT-017.md"
    requirement.parent.mkdir(parents=True)
    feature.parent.mkdir(parents=True)
    requirement.write_text(
        "---\nid: SR-001\ntitle: Staged Requirement\nstatement: The closure is staged.\n"
        "domain: behavioral\nupstream: []\nsource: docs/spec.md#Goal\n---\nRequirement.\n",
        encoding="utf-8",
    )
    feature.write_text(
        "---\nid: FEAT-017\ntitle: Staged closure\nrequirements: [SR-001]\n---\n", encoding="utf-8",
    )
    bundle = tmp_path / "bundles/FEAT-017.json"
    bundle.parent.mkdir(parents=True, exist_ok=True)
    bundle.write_text(
        json.dumps({"id": "FEAT-017", "members": ["feat:FEAT-017", "sr:SR-001"]}), encoding="utf-8",
    )
    write_artifact_manifest(tmp_path, run_id, build_artifact_manifest(tmp_path, run_id, [
        {"kind": "requirements", "path": "requirements/SR-001.md"},
    ]))
    assert legal_actions_session(tmp_path, run_id)["legal_next_actions"] == ["record-sr-consent"]
    write_sr_decision(tmp_path, run_id, "SR-001", _sha(requirement), "approve", "human", CONSENT_PHRASE, "Reviewed.")
    spec = tmp_path / "docs/spec.md"
    plan = tmp_path / "docs/plan.md"
    spec.write_text(
        "---\nid: SPEC-1\ntitle: Staged Specification\nstatus: draft\n---\n"
        "# Goal\nThe goal is staged.\n", encoding="utf-8",
    )
    plan.write_text(
        "---\nspec_ref: SPEC-1\n---\n# Plan\n\n### Task 1: Stage\n\n**Files:**\n"
        "- Create: `docs/staged.md`\n\n**Interfaces:**\n- Produces: `goal` support.\n", encoding="utf-8",
    )
    write_artifact_manifest(tmp_path, run_id, build_artifact_manifest(tmp_path, run_id, [
        {"kind": "requirements", "path": "requirements/SR-001.md"},
        {"kind": "spec", "path": "docs/spec.md"}, {"kind": "plan", "path": "docs/plan.md"},
    ]))
    assert legal_actions_session(tmp_path, run_id)["legal_next_actions"] == ["review-spec"]

    # Human review is only current once the complete planning source set is published,
    # so the run is completed here before the review stages are attested.
    run_dir = tmp_path / ".factory/planning" / run_id
    run_dir.joinpath("spec-review.json").write_text('{"status":"pass"}', encoding="utf-8")
    write_artifact_manifest(tmp_path, run_id, build_artifact_manifest(tmp_path, run_id, [
        {"kind": kind, "path": path} for kind, path in _FULL_PLANNING_SOURCES
    ]))
    paths = sorted(path for _, path in _FULL_PLANNING_SOURCES)
    report = {
        "schema": 1, "run_id": run_id, "ok": True,
        "artifacts": [{"path": path, "sha256": _sha(tmp_path / path)} for path in paths],
        "findings": [], "next_actions": [], "review_required": True, "suggestion": None,
    }
    (run_dir / "report.json").write_text(json.dumps(report), encoding="utf-8")
    (run_dir / "review-decision.json").write_text(json.dumps({
        "schema": 1, "run_id": run_id, "decision": "approve", "reviewer": "human",
        "reason": "Reviewed.", "reviewed_artifacts": paths,
        "report_sha256": planning_report_digest(report),
    }), encoding="utf-8")
    assert legal_actions_session(tmp_path, run_id)["legal_next_actions"] == ["review-plan"]
    run_dir.joinpath("plan-review.json").write_text('{"status":"pass"}', encoding="utf-8")
    assert legal_actions_session(tmp_path, run_id)["legal_next_actions"] == ["run-planning-gates"]


@pytest.mark.parametrize("mutation", ["missing", "repointed", "malformed", "empty"])
def test_manifest_changes_invalidate_published_gate_and_handoff(
    tmp_path: Path, mutation: str,
) -> None:
    from coherence.planning.cli import _read_report
    from coherence.planning.gates import validate_planning_gate_result
    from coherence.planning.handoff import validate_handoff
    from tests.unit.coherence.test_planning_gates import _FULL_PLANNING_SOURCES, _write_current_planning_evidence

    run_id = "run-001"
    _write_current_planning_evidence(tmp_path, run_id)
    # The initial state must be a complete, currently-validated planning closure; the
    # mutation under test is applied to this manifest afterwards.
    manifest_path = write_artifact_manifest(tmp_path, run_id, build_artifact_manifest(
        tmp_path, run_id, [{"kind": kind, "path": path} for kind, path in _FULL_PLANNING_SOURCES],
    ))
    pack = compile_planning_gate_pack("FEAT-017", "v1")
    evaluate_planning_gate_pack(tmp_path, run_id, pack)
    report = _read_report(tmp_path / ".factory/planning/run-001/report.json", run_id)
    handoff_path, _ = write_handoff(tmp_path, build_handoff(tmp_path, report))
    assert legal_actions_session(tmp_path, run_id)["legal_next_actions"] == ["inspect-handoff"]

    if mutation == "missing":
        manifest_path.unlink()
    elif mutation == "malformed":
        manifest_path.write_text("{}", encoding="utf-8")
    else:
        replacement = tmp_path / "docs/replacement.md"
        replacement.write_text("Unreviewed replacement.", encoding="utf-8")
        artifacts = [] if mutation == "empty" else [{"kind": "plan", "path": "docs/replacement.md"}]
        write_artifact_manifest(tmp_path, run_id, build_artifact_manifest(tmp_path, run_id, artifacts))

    evaluated = evaluate_planning_gate_pack(tmp_path, run_id, pack)
    assert evaluated["executions"][1]["status"] == "fail"
    evaluated_again = evaluate_planning_gate_pack(tmp_path, run_id, pack)
    assert evaluated_again["executions"][1]["status"] == "fail"
    with pytest.raises(PlanningGateError):
        validate_planning_gate_result(tmp_path, run_id, pack)
    with pytest.raises(HandoffError):
        build_handoff(tmp_path, report)
    with pytest.raises(HandoffError):
        validate_handoff(tmp_path, handoff_path)
    projection = legal_actions_session(tmp_path, run_id)
    assert projection["blocked"] is True
    assert projection["legal_next_actions"] == []
    handoff_path.unlink()
    assert legal_actions_session(tmp_path, run_id)["legal_next_actions"] != ["create-handoff"]


def test_coordinated_closure_is_non_executing_and_ends_at_inspect_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from coherence.planning.cli import main as planning_main

    run_id = "closure-proof"
    start_session(tmp_path, run_id, "Prove the planning closure")
    append_session_answer(tmp_path, run_id, "goal", "What does the closure prove?", "Prove the planning closure")

    requirement = tmp_path / "requirements" / "SR-001.md"
    feature = tmp_path / "docs" / "features" / "FEAT-017.md"
    spec = tmp_path / "docs" / "spec.md"
    plan = tmp_path / "docs" / "plan.md"
    task = tmp_path / "tasks" / "T-001-proof.md"
    bundle = tmp_path / "bundles" / "FEAT-017.json"
    for path in (requirement, feature, spec, plan, task, bundle):
        path.parent.mkdir(parents=True, exist_ok=True)
    requirement.write_text(
        "---\nid: SR-001\ntitle: Closure Proof\nstatement: The closure is proven.\n"
        "domain: behavioral\nupstream: []\nsource: docs/spec.md#Goal\n---\nCurrent requirement.\n",
        encoding="utf-8",
    )
    feature.write_text(
        "---\nid: FEAT-017\ntitle: Closure proof coverage\nrequirements: [SR-001]\n---\n", encoding="utf-8",
    )
    spec.write_text(
        "---\nid: SPEC-1\ntitle: Closure Specification\nstatus: draft\n---\n"
        "# Goal\nThe goal is proven.\n", encoding="utf-8",
    )
    plan.write_text(
        "---\nspec_ref: SPEC-1\n---\n# Closure Plan\n\n### Task 1: Proof\n\n**Files:**\n"
        "- Create: `docs/closure.md`\n\n**Interfaces:**\n- Produces: `goal` support.\n",
        encoding="utf-8",
    )
    task.write_text("---\nid: T-001\ntitle: Documentation\nstatus: todo\ndod: []\n---\nDocument the plan.\n", encoding="utf-8")
    bundle.write_text(
        json.dumps({"id": "FEAT-017", "members": ["feat:FEAT-017", "sr:SR-001"]}), encoding="utf-8",
    )

    artifacts = [
        {"kind": kind, "path": path.relative_to(tmp_path).as_posix()}
        for kind, path in (
            ("intent", tmp_path / ".intent" / "intent.json"), ("requirements", requirement),
            ("feature", feature), ("spec", spec), ("plan", plan), ("bundle", bundle),
        )
    ]
    artifacts.sort(key=lambda item: item["path"])
    assert planning_main([
        "write-artifact-manifest", "--project-root", str(tmp_path), "--run-id", run_id,
        "--artifacts-json", json.dumps([
            {**item, "sha256": _sha(tmp_path / item["path"])} for item in artifacts
        ]), "--json",
    ]) == 0
    write_sr_decision(
        tmp_path, run_id, "SR-001", _sha(requirement), "approve", "human", CONSENT_PHRASE,
        "Independently reviewed the current requirement.",
    )
    (tmp_path / ".factory" / "planning" / run_id / "requirement-consent.json").write_text(
        json.dumps({"schema": 1, "run_id": run_id, "decision": "approve", "reviewer": "human",
                    "reason": "Reviewed requirements.", "requirements": ["SR-001"]}),
        encoding="utf-8",
    )

    # The generated task is not a planning source kind, but the review requires it to be
    # covered by the report, so it is listed as a reviewed artifact alongside the sources.
    reviewed = sorted(
        [{"path": item["path"], "sha256": _sha(tmp_path / item["path"])} for item in artifacts]
        + [{"path": "tasks/T-001-proof.md", "sha256": _sha(task)}],
        key=lambda item: item["path"],
    )
    report = PlanningReport(
        1, run_id, True,
        tuple(reviewed),
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
        "reviewed_artifacts": [item["path"] for item in reviewed],
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
