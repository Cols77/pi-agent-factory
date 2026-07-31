from __future__ import annotations

from pathlib import Path

from factory.orchestrator.backends import AgentBackend, GateRunner
from factory.evidence.types import EvidenceContext
from factory.orchestrator.ledger import Task
from factory.orchestrator.prompts import compose_prompt
from factory.orchestrator.status import NullStatusReporter, StatusReporter
from factory.orchestrator.transcripts import write_role_transcript
from factory.orchestrator.types import AgentResult, AgentRole, NodeEvent, NodeOutcome
from factory.validation.manifest_validator import validate_manifest


def _note_backend_failure(extra: dict, result: AgentResult) -> dict:
    """Finding 1+2 (final review): surface `result.ok is False` as a distinct
    diagnostic signal in NodeEvent.extra, separate from a legitimately bad/empty
    agent output, without changing retry/circuit-breaker control flow or outcomes.
    """
    if not result.ok:
        extra["backend_ok"] = False
        extra["backend_raw"] = result.raw
    return extra


def _summarize_manifest(manifest: dict | None) -> str:
    """One-line manifest summary for the handoff/summary status: the actual file
    basenames the context gatherer provided. Coherence is no longer self-reported
    (it is derived by validate_manifest), so it is not shown here."""
    if manifest is None:
        return "no manifest"
    ctx = manifest.get("context", {})
    raw = ctx.get("source_files", [])
    files = raw if isinstance(raw, list) else []
    if not files:
        return "no source files"
    names = [Path(str(p)).name for p in files]
    shown = ", ".join(names[:3])
    if len(names) > 3:
        shown += f" (+{len(names) - 3})"
    return f"provided: {shown}"


def _summarize_review(findings: list) -> str:
    """Extract a one-line summary of review findings for the handoff status."""
    if not findings:
        return "DoD not met"
    return "requested: " + "; ".join(str(f)[:60] for f in findings[:3])


def run_context_gatherer(
    backend: AgentBackend,
    task: Task,
    repo_root: Path,
    max_attempts: int = 2,
    transcript_dir: Path | None = None,
    status: StatusReporter = NullStatusReporter(),
    gates: GateRunner | None = None,
) -> tuple[NodeOutcome, dict | None, NodeEvent]:
    errors: list[str] = []
    result: AgentResult | None = None
    # Captured as soon as the backend streams pi's `session` event, so the
    # dashboard can open the live session while the agent is still running
    # (Feature A) instead of only after the process exits.
    captured_session_id: str | None = None
    for attempt in range(1, max_attempts + 1):
        status.report(
            task_id=task.id, node="context-gather", node_state="running",
            attempt=attempt, max_attempts=max_attempts,
        )

        def _on_session_id(sid: str) -> None:
            nonlocal captured_session_id
            captured_session_id = sid
            status.report(
                task_id=task.id, node="context-gather", node_state="running",
                attempt=attempt, max_attempts=max_attempts, session_id=sid,
            )

        def _on_snippet(text: str) -> None:
            status.report(
                task_id=task.id, node="context-gather", node_state="running",
                attempt=attempt, max_attempts=max_attempts, snippet=text,
                session_id=captured_session_id,
            )

        feedback = "\n".join(errors) if errors else None
        result = backend.run(
            AgentRole.CONTEXT_GATHERER,
            compose_prompt(AgentRole.CONTEXT_GATHERER, task, skills_dir=repo_root / ".pi" / "skills", feedback=feedback),
            on_snippet=_on_snippet, on_session_id=_on_session_id,
        )
        if transcript_dir is not None:
            write_role_transcript(transcript_dir, "context-gather", attempt, result.raw)
        manifest = result.output
        if manifest.get("already_done"):
            reason = manifest.get("already_done_reason") or "task deliverables already exist"
            status.report(
                task_id=task.id, node="context-gather", node_state="already-done",
                attempt=attempt, max_attempts=max_attempts,
                handoff="→ review: task appears already complete",
                session_id=result.session_id, summary=reason,
            )
            return (
                NodeOutcome.ALREADY_DONE,
                manifest,
                NodeEvent("context-gather", "already-done", attempt, {}),
            )
        if manifest.get("reject"):
            extra = _note_backend_failure({"reason": manifest["reject"]}, result)
            status.report(
                task_id=task.id, node="context-gather", node_state="reject",
                attempt=attempt, max_attempts=max_attempts,
                handoff=f"rejected: {manifest['reject']}",
            )
            return NodeOutcome.REJECT, None, NodeEvent("context-gather", "reject", attempt, extra)
        ctx = EvidenceContext(repo_root=repo_root, gates=gates, kb_dir=repo_root / "kb")
        errors = validate_manifest(manifest, repo_root, task=task, ctx=ctx)
        if not errors:
            extra = _note_backend_failure({}, result)
            handoff = _summarize_manifest(manifest)
            status.report(
                task_id=task.id, node="context-gather", node_state="pass",
                attempt=attempt, max_attempts=max_attempts,
                handoff=f"→ dev: {handoff}",
                session_id=result.session_id, summary=_summarize_manifest(manifest),
            )
            return NodeOutcome.PASS, manifest, NodeEvent("context-gather", "pass", attempt, extra)
        status.report(
            task_id=task.id, node="context-gather", node_state="running",
            attempt=attempt, max_attempts=max_attempts,
            handoff=f"validation errors: {'; '.join(errors[:3])}",
        )
    extra = {"errors": errors}
    if result is not None:
        extra = _note_backend_failure(extra, result)
    status.report(
        task_id=task.id, node="context-gather", node_state="reject",
        attempt=max_attempts, max_attempts=max_attempts,
        handoff=f"failed after {max_attempts} attempts", outcome="rejected",
    )
    return NodeOutcome.REJECT, None, NodeEvent("context-gather", "reject", max_attempts, extra)


def run_dev(
    backend: AgentBackend,
    gates: GateRunner,
    task: Task,
    manifest: dict,
    kb_entries: list[dict],
    repo_root: Path,
    max_iters: int = 3,
    feedback: str | None = None,
    transcript_dir: Path | None = None,
    status: StatusReporter = NullStatusReporter(),
) -> tuple[NodeOutcome, NodeEvent]:
    result: AgentResult | None = None
    captured_session_id: str | None = None
    for attempt in range(1, max_iters + 1):
        status.report(
            task_id=task.id, node="dev", node_state="running",
            attempt=attempt, max_attempts=max_iters,
        )

        def _on_session_id(sid: str) -> None:
            nonlocal captured_session_id
            captured_session_id = sid
            status.report(
                task_id=task.id, node="dev", node_state="running",
                attempt=attempt, max_attempts=max_iters, session_id=sid,
            )

        def _on_snippet(text: str) -> None:
            status.report(
                task_id=task.id, node="dev", node_state="running",
                attempt=attempt, max_attempts=max_iters, snippet=text,
                session_id=captured_session_id,
            )

        result = backend.run(
            AgentRole.DEV,
            compose_prompt(
                AgentRole.DEV, task, manifest, kb_entries, feedback,
                skills_dir=repo_root / ".pi" / "skills",
            ),
            on_snippet=_on_snippet, on_session_id=_on_session_id,
        )
        if transcript_dir is not None:
            write_role_transcript(transcript_dir, "dev", attempt, result.raw)
        if gates.run("unit") == 0:
            extra = _note_backend_failure({"tests": "green"}, result)
            status.report(
                task_id=task.id, node="dev", node_state="pass",
                attempt=attempt, max_attempts=max_iters,
                handoff="→ validation: unit tests green",
                session_id=result.session_id, summary="changed files; unit tests pass",
            )
            return NodeOutcome.PASS, NodeEvent("dev", "pass", attempt, extra)
        status.report(
            task_id=task.id, node="dev", node_state="running",
            attempt=attempt, max_attempts=max_iters,
            handoff=f"unit tests failed, retry {attempt}/{max_iters}",
        )
    extra = {"reason": "unit tests red"}
    if result is not None:
        extra = _note_backend_failure(extra, result)
    status.report(
        task_id=task.id, node="dev", node_state="escalate",
        attempt=max_iters, max_attempts=max_iters,
        handoff="escalated: unit tests still red", outcome="escalated",
    )
    return NodeOutcome.ESCALATE, NodeEvent("dev", "escalate", max_iters, extra)


def run_validation(
    gates: GateRunner, task_id: str = "", status: StatusReporter = NullStatusReporter()
) -> tuple[NodeOutcome, NodeEvent]:
    status.report(task_id=task_id, node="validation", node_state="running", attempt=1, max_attempts=1,
                 handoff="running sim + integration gates")
    if gates.run("sim") != 0:
        status.report(task_id=task_id, node="validation", node_state="fail", attempt=1, max_attempts=1,
                     handoff="sim tests failed")
        return NodeOutcome.FAIL, NodeEvent("validation", "fail")
    if gates.run("integration") != 0:
        status.report(task_id=task_id, node="validation", node_state="fail", attempt=1, max_attempts=1,
                     handoff="integration tests failed")
        return NodeOutcome.FAIL, NodeEvent("validation", "fail")
    status.report(task_id=task_id, node="validation", node_state="pass", attempt=1, max_attempts=1,
                 handoff="→ review: sim + integration tests green")
    return NodeOutcome.PASS, NodeEvent("validation", "pass")


def run_review(
    backend: AgentBackend,
    gates: GateRunner,
    task: Task,
    kb_entries: list[dict],
    repo_root: Path,
    transcript_dir: Path | None = None,
    status: StatusReporter = NullStatusReporter(),
) -> tuple[NodeOutcome, NodeEvent, list[str]]:
    status.report(task_id=task.id, node="review", node_state="running", attempt=1, max_attempts=1)
    captured_session_id: str | None = None

    def _on_session_id(sid: str) -> None:
        nonlocal captured_session_id
        captured_session_id = sid
        status.report(
            task_id=task.id, node="review", node_state="running",
            attempt=1, max_attempts=1, session_id=sid,
        )

    def _on_snippet(text: str) -> None:
        status.report(
            task_id=task.id, node="review", node_state="running",
            attempt=1, max_attempts=1, snippet=text,
            session_id=captured_session_id,
        )

    result = backend.run(
        AgentRole.REVIEW,
        compose_prompt(AgentRole.REVIEW, task, kb_entries=kb_entries, skills_dir=repo_root / ".pi" / "skills"),
        on_snippet=_on_snippet, on_session_id=_on_session_id,
    )
    if transcript_dir is not None:
        write_role_transcript(transcript_dir, "review", 1, result.raw)
    out = result.output
    findings = list(out.get("findings", []))
    dod_met = bool(out.get("dod_met"))
    confidence = out.get("confidence") if isinstance(out.get("confidence"), str) else None
    verify = out.get("verify") if isinstance(out.get("verify"), list) else []
    gate = gates.run("full")
    if gate == 0 and dod_met and not findings:
        extra = _note_backend_failure({"confidence": confidence, "verify": verify}, result)
        status.report(
            task_id=task.id, node="review", node_state="pass",
            attempt=1, max_attempts=1,
            handoff="✓ task complete, DoD met, gates pass", outcome="completed",
            session_id=result.session_id, summary="DoD met; gates pass",
        )
        return NodeOutcome.PASS, NodeEvent("review", "pass", 1, extra), []
    finding_summary = f"{len(findings)} finding(s)" if findings else "DoD not met"
    extra = _note_backend_failure({"findings": len(findings), "gate": gate, "confidence": confidence, "verify": verify}, result)
    status.report(
        task_id=task.id, node="review", node_state="changes-requested",
        attempt=1, max_attempts=1,
        handoff=f"→ dev: {finding_summary}, gate={'pass' if gate == 0 else 'fail'}",
        session_id=result.session_id, summary=_summarize_review(findings),
    )
    return (
        NodeOutcome.CHANGES,
        NodeEvent("review", "changes-requested", 1, extra),
        findings,
    )
