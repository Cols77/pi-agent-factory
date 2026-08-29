from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from coherence.planning.check import check_planning_input
from coherence.planning.gates import validate_sr_consent
from coherence.planning.handoff import build_downstream_menu, build_handoff, validate_handoff, write_handoff
from coherence.planning.intent import read_intent
from coherence.planning.loop import FreshReviewLoop, LoopStatus
from coherence.planning.model import PlanningInput
from coherence.planning.resolution import read_resolution_events
from coherence.planning.run import planning_report_digest
from coherence.planning.semantic import SemanticReviewReport, build_review_packet
from coherence.planning.session import append_session_answer, resume_session, start_session
from coherence.planning.workflow import PlanningWorkflow, WorkflowStage
from coherence.gate.model import Decision, DecisionFile
from factory.orchestrator.backends import FakeAgentBackend
from factory.orchestrator.types import AgentRole
from substrate.agents.model import AgentResult, InterruptionReason

pytestmark = pytest.mark.integration
FIXTURE = Path(__file__).parents[2] / "fixtures" / "planning-dogfood"
CONSENT_PHRASE = "I explicitly consent to adopt exactly these candidate SRs."


def _consumer(tmp_path: Path) -> tuple[Path, Path, Path]:
    root = tmp_path / "consumer"
    (root / ".intent").mkdir(parents=True)
    (root / "docs/superpowers/specs").mkdir(parents=True)
    (root / "docs/superpowers/plans").mkdir(parents=True)
    shutil.copy(FIXTURE / "intent.json", root / ".intent/intent.json")
    spec = root / "docs/superpowers/specs/intent-spec.md"
    plan = root / "docs/superpowers/plans/intent-plan.md"
    shutil.copy(FIXTURE / "spec.md", spec)
    shutil.copy(FIXTURE / "plan.md", plan)
    tasks = root / "tasks"
    tasks.mkdir()
    for number, title in ((1, "first"), (2, "second")):
        (tasks / f"T-{number:03d}-{title}.md").write_text(
            f"---\nid: T-{number:03d}\ntitle: {title.title()} Task\nstatus: todo\n"
            "source_plan: docs/superpowers/plans/intent-plan.md\n"
            f"source_task: {number}\n---\n", encoding="utf-8")
    requirements = root / "requirements"
    requirements.mkdir()
    for req_id in ("SR-001", "SR-002"):
        (requirements / f"{req_id}.md").write_text(
            f"---\nid: {req_id}\ntitle: {req_id} requirement\nstatement: {req_id} statement\n"
            "domain: behavioral\nupstream: []\nsource: docs/superpowers/specs/intent-spec.md#goal\n---\n",
            encoding="utf-8")
    feature = root / "docs/features/FEAT-017.md"
    feature.parent.mkdir(parents=True)
    feature.write_text("---\nid: FEAT-017\ntitle: Planning Bootstrap\nrequirements: [SR-001, SR-002]\n---\n", encoding="utf-8")
    bundle = root / "bundles/FEAT-017.json"
    bundle.parent.mkdir()
    bundle.write_text(json.dumps({"id": "FEAT-017", "members": ["feat:FEAT-017", "sr:SR-001", "sr:SR-002"]}), encoding="utf-8")
    return root, spec, plan


def _input(root: Path, spec: Path, plan: Path, run_id: str = "run-001") -> PlanningInput:
    return PlanningInput(root / ".intent/intent.json", spec, plan, root, run_id)


def _review_result(packet, *, verdict: str = "clean", findings: list[dict] | None = None) -> AgentResult:
    payload = packet.to_dict()
    payload.update({"packet_sha256": packet.sha256, "findings": findings or [], "human_prompts": [], "notes": [], "verdict": verdict})
    return AgentResult(ok=True, output=payload, raw=json.dumps(payload))


def _packet_from_prompt(root: Path, prompt: str):
    payload = json.loads(prompt.split("\n", 1)[1].split("\nPrior escalation:", 1)[0])
    return build_review_packet(
        run_id=payload["run_id"], stage=payload["stage"], iteration=payload["iteration"],
        artifact_paths=[root / item["path"] for item in payload["artifacts"]], project_root=root,
        context=payload["context"], sr_context_digest=payload["sr_context_digest"], model=payload["model"],
        reviewer_role=payload["reviewer_role"], reviewer_session_id=None)


def test_clean_consumer_dogfood_captures_fix_consent_and_handoff(tmp_path: Path) -> None:
    root, spec, plan = _consumer(tmp_path)
    start_session(root, "run-001", "Build a deterministic planner")
    append_session_answer(root, "run-001", "goal", "What is the goal?", "Build a deterministic planner")
    assert check_planning_input(_input(root, spec, plan)).ok

    artifact = root / "docs/superpowers/specs/intent-spec.md"
    calls = 0
    class ScriptedBackend(FakeAgentBackend):
        def run(self, role, prompt, **kwargs):
            nonlocal calls
            calls += 1
            packet = _packet_from_prompt(root, prompt)
            if calls == 1:
                return _review_result(packet, verdict="findings", findings=[{
                    "id": "fix-spec", "evidence": "spec.md", "confidence": 1.0,
                    "disposition": "resolve_in_loop", "artifact_paths": ["docs/superpowers/specs/intent-spec.md"]}])
            return _review_result(packet)

    loop = FreshReviewLoop(
        project_root=root, backend=ScriptedBackend({}), model={"provider": "fixture", "model": "reviewer"},
        reviewer_role=AgentRole.PLANNING_ALIGNMENT,
        fixer=lambda path, finding: path.write_text(path.read_text(encoding="utf-8") + "\nEvidence added.\n", encoding="utf-8"),
        gate=lambda _: True)
    packet = loop.build_packet("run-001", "spec_alignment", 1, [artifact], {"intent": "captured"}, "0" * 64)
    result = loop.run(packet)
    assert result.status is LoopStatus.CLEAN and result.iterations == 2
    assert len(read_resolution_events(root, "run-001")) == 1

    # The consumer then runs the real three-checkpoint lifecycle over the
    # fixture's valid spec, plan/tasks, and derived FEAT/SR/bundle artifacts.
    observed: list[tuple[str, dict, dict]] = []
    gate_calls: list[str] = []

    def lifecycle_review(packet):
        observed.append((packet.stage, packet.context, dict(packet.context["sr_context"])))
        return SemanticReviewReport(1, packet.run_id, packet.stage, packet.iteration, packet.sha256,
                                    packet.artifacts, packet.context, packet.sr_context_digest, packet.model,
                                    packet.reviewer_role, packet.reviewer_session_id, (), (), (), "clean")

    lifecycle = PlanningWorkflow(
        root, "run-001", reviewer_model={"provider": "fixture", "model": "reviewer"},
        reviewer=lifecycle_review, deterministic_gate=lambda project: gate_calls.append(str(project)) is None,
    )
    lifecycle_status = lifecycle.run_lifecycle(
        spec_artifacts=[root / "docs/superpowers/specs/intent-spec.md"],
        plan_artifacts=[root / "docs/superpowers/plans/intent-plan.md", root / "tasks/T-001-first.md", root / "tasks/T-002-second.md"],
        derivation_artifacts=[root / "docs/superpowers/specs/intent-spec.md", root / "docs/superpowers/plans/intent-plan.md",
                             root / "tasks/T-001-first.md", root / "tasks/T-002-second.md", root / "docs/features/FEAT-017.md",
                             root / "bundles/FEAT-017.json"],
        intent_context={"intent": "Build a deterministic planner", "unresolved_questions": []},
        plan_context={"tasks": ["T-001", "T-002"], "source_plan": "docs/superpowers/plans/intent-plan.md"},
        derivation_context={"candidate_srs": ["SR-001", "SR-002"], "feature": "FEAT-017",
                            "bundle": "FEAT-017", "closure": ["feat:FEAT-017", "sr:SR-001", "sr:SR-002"]},
        sr_context={"SR-001": {"status": "proposed", "statement": "SR-001 statement"},
                    "SR-002": {"status": "proposed", "statement": "SR-002 statement"}},
    )
    assert lifecycle_status.ok and not lifecycle_status.blocked
    assert [stage for stage, _, _ in observed] == [stage.value for stage in WorkflowStage]
    assert observed[1][1]["tasks"] == ["T-001", "T-002"]
    assert observed[2][1]["closure"] == ["feat:FEAT-017", "sr:SR-001", "sr:SR-002"]
    assert observed[2][2]["SR-002"]["status"] == "proposed"
    assert len(gate_calls) == 6  # preflight and postflight for each checkpoint

    consent = root / ".factory/planning/run-001/sr-consent.json"
    consent.parent.mkdir(parents=True, exist_ok=True)
    consent.write_text(json.dumps({"schema": 2, "run_id": "run-001", "decision": "approve", "reviewer": "human",
        "phrase": CONSENT_PHRASE, "candidate_srs": ["SR-001", "SR-002"], "derivation_report_sha256": "0" * 64,
        "artifact_hashes": {}}), encoding="utf-8")
    assert validate_sr_consent(root, "run-001", ["SR-001", "SR-002"], "0" * 64, {})[0]
    report = check_planning_input(_input(root, spec, plan))
    payload = build_handoff(root, report, workflow="standard-development", gate_summary={"status": "pass"})
    path, _ = write_handoff(root, payload)
    assert validate_handoff(root, path)["starts_automatically"] is False
    assert json.loads(consent.read_text(encoding="utf-8"))["phrase"] == CONSENT_PHRASE
    assert [item["id"] for item in build_downstream_menu()] == ["standard-development", "health-recovery", "feature-planning"]


def test_three_checkpoint_projection_accepts_warning_and_preserves_full_context(tmp_path: Path) -> None:
    paths = []
    root, _, _ = _consumer(tmp_path)
    paths = [root / name for name in (".intent/intent.json", "docs/superpowers/specs/intent-spec.md",
                                      "docs/superpowers/plans/intent-plan.md", "tasks/T-001-first.md",
                                      "docs/features/FEAT-017.md", "bundles/FEAT-017.json")]
    seen: list[str] = []
    seen_sr_context: list[dict] = []
    def reviewer(packet):
        seen.append(packet.stage)
        seen_sr_context.append(packet.context["sr_context"])
        finding = ({"id": "accepted-warning", "evidence": "review", "confidence": 1.0,
                    "disposition": "resolve_in_loop", "artifact_paths": [packet.artifacts[0]["path"]]},)
        from coherence.planning.semantic import SemanticReviewReport
        return SemanticReviewReport(1, packet.run_id, packet.stage, packet.iteration, packet.sha256, packet.artifacts,
            packet.context, packet.sr_context_digest, packet.model, packet.reviewer_role, packet.reviewer_session_id,
            finding, (), ("informational",), "findings")
    warning = DecisionFile(gate_id="planning", artifact_ref="intent-spec.md",
                           decisions=(Decision("coverage:run-1:warning:accepted-warning", "accept"),),
                           decided_at="2026-08-29T00:00:00Z", decided_by="human")
    workflow = PlanningWorkflow(root, "run-1", reviewer_model={"provider": "fixture", "model": "reviewer"}, reviewer=reviewer)
    workflow.accept_warning(warning.decisions[0].item_id.rsplit(":", 1)[-1])
    status = workflow.run_lifecycle(spec_artifacts=paths[1:2], plan_artifacts=paths[1:4], derivation_artifacts=paths[1:],
        intent_context={"intent": "full", "unresolved_questions": []}, plan_context={"tasks": ["T-001"]},
        derivation_context={"candidate_srs": ["SR-001"], "duplicate_context": "retained"},
        sr_context={"SR-001": {"status": "proposed", "statement": "full"}, "SR-002": {"status": "deferred", "statement": "contradiction reviewed"}})
    assert status.ok is True
    assert seen == [stage.value for stage in WorkflowStage]
    assert status.to_dict()["stages"][-1]["status"] == "clean"
    assert warning.to_dict()["decisions"][0]["action"] == "accept"
    assert seen_sr_context == [{"SR-001": {"status": "proposed", "statement": "full"},
                               "SR-002": {"status": "deferred", "statement": "contradiction reviewed"}}] * 3


def test_escalation_repeated_finding_and_interrupted_resume_are_fail_closed(tmp_path: Path) -> None:
    root, spec, _ = _consumer(tmp_path)
    start_session(root, "run-001", "request")
    append_session_answer(root, "run-001", "goal", "Question?", "Answer")
    journal = root / ".factory/planning/run-001/capture/events.jsonl"
    before = journal.read_text(encoding="utf-8")
    assert resume_session(root, "run-001").next_sequence == 3
    assert journal.read_text(encoding="utf-8") == before

    artifact = root / "docs/superpowers/specs/intent-spec.md"
    calls = 0
    class RepeatingBackend(FakeAgentBackend):
        def run(self, role, prompt, **kwargs):
            nonlocal calls
            calls += 1
            packet = _packet_from_prompt(root, prompt)
            finding = {"id": "repeat", "evidence": "spec.md", "confidence": 1.0,
                       "disposition": "resolve_in_loop", "artifact_paths": ["docs/superpowers/specs/intent-spec.md"]}
            return _review_result(packet, verdict="findings", findings=[finding])
    loop = FreshReviewLoop(project_root=root, backend=RepeatingBackend({}), model={"provider": "fixture", "model": "reviewer"},
        reviewer_role=AgentRole.PLANNING_ALIGNMENT, fixer=lambda path, finding: path.write_text(path.read_text(encoding="utf-8") + "x", encoding="utf-8"), max_iterations=3)
    result = loop.run(loop.build_packet("run-001", "spec_alignment", 1, [artifact], {"intent": "captured"}, "0" * 64))
    assert result.status is LoopStatus.ESCALATED and result.error == "repeated finding" and calls == 2


def test_human_escalation_returns_prompt_then_next_loop_resumes_after_answer(tmp_path: Path) -> None:
    root, _, _ = _consumer(tmp_path)
    artifact = root / "docs/superpowers/specs/intent-spec.md"
    class HumanBackend(FakeAgentBackend):
        calls = 0
        def run(self, role, prompt, **kwargs):
            self.calls += 1
            packet = _packet_from_prompt(root, prompt)
            return _review_result(packet, verdict="escalate" if self.calls == 1 else "clean")
    loop = FreshReviewLoop(project_root=root, backend=HumanBackend({}), model={"provider": "fixture", "model": "reviewer"},
        reviewer_role=AgentRole.PLANNING_ALIGNMENT)
    packet = loop.build_packet("run-human", "spec_alignment", 1, [artifact], {"unresolved_questions": []}, "0" * 64)
    result = loop.run(packet)
    assert result.status is LoopStatus.ESCALATED
    assert result.error == "reviewer escalation"
    assert not (root / ".factory/planning/run-human/sr-consent.json").exists()
    start_session(root, "run-answer", "request")
    append_session_answer(root, "run-answer", "owner", "Who owns the decision?", "human", source="user")
    assert resume_session(root, "run-answer").next_sequence == 3
    assert read_intent(root / ".intent/intent.json", project_root=root).answers[-1].text == "human"
    resumed = FreshReviewLoop(project_root=root, backend=loop.backend,
                              model={"provider": "fixture", "model": "reviewer"})
    resumed_result = resumed.run(resumed.build_packet("run-human", "spec_alignment", 2, [artifact],
                                                       {"unresolved_questions": []}, "0" * 64))
    assert resumed_result.status is LoopStatus.CLEAN


def test_interrupted_reviewer_fails_closed_and_stale_artifact_is_rejected(tmp_path: Path) -> None:
    root, _, _ = _consumer(tmp_path)
    artifact = root / "docs/superpowers/specs/intent-spec.md"

    class InterruptedBackend(FakeAgentBackend):
        def run(self, role, prompt, **kwargs):
            return AgentResult(ok=False, output={}, interruption=InterruptionReason.CONTEXT_LIMIT)

    interrupted = FreshReviewLoop(project_root=root, backend=InterruptedBackend({}),
                                  model={"provider": "fixture", "model": "reviewer"})
    result = interrupted.run(interrupted.build_packet("run-interrupted", "spec_alignment", 1, [artifact], {}, "0" * 64))
    assert result.status is LoopStatus.ESCALATED
    assert "interrupted" in (result.error or "")

    stale_packet = interrupted.build_packet("run-stale", "spec_alignment", 1, [artifact], {}, "0" * 64)
    artifact.write_text(artifact.read_text(encoding="utf-8") + "\nchanged\n", encoding="utf-8")
    stale = interrupted.run(stale_packet)
    assert stale.error == "stale artifact"


def test_repository_self_hosting_reports_unrelated_debt_without_claiming_clean() -> None:
    root = Path(__file__).parents[3]
    intent = root / ".intent/intent.json"
    spec = root / "docs/superpowers/specs/2026-08-27-feat17-planning-bootstrap-design.md"
    plan = root / "docs/superpowers/plans/2026-08-27-feat17-planning-workflow-plan.md"
    report = check_planning_input(_input(root, spec, plan, "self-hosting"))
    assert report.ok is False
    assert any(item.code == "PLAN_TASK_PARITY" for item in report.findings)
    assert planning_report_digest(report) == planning_report_digest(report.to_dict())
    assert read_intent(intent, project_root=root).prompt
