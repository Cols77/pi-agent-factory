from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict
import subprocess
from pathlib import Path

from factory.orchestrator.backends import GATE_NOT_APPLICABLE, AgentBackend, GateRunner
from factory.orchestrator.continuation import build_continuation_context
from factory.evidence.types import EvidenceContext
from factory.orchestrator.ledger import Task
from factory.orchestrator.prompts import compose_prompt
from factory.orchestrator.status import NullStatusReporter, StatusReporter
from factory.orchestrator.transcripts import write_role_transcript
from factory.orchestrator.types import (
    AgentResult,
    AgentRole,
    InterruptionReason,
    NodeEvent,
    NodeOutcome,
)
from factory.validation.manifest_validator import validate_manifest
from factory.validation.pipeline import validate_task_requirements
from factory.validation.report import write_validation_report


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


def _event_results(events: list[NodeEvent] | None) -> dict[str, str]:
    if not events:
        return {}
    return {event.node: event.result for event in events}


def _run_with_context_limit_continuation(
    backend: AgentBackend,
    role: AgentRole,
    prompt: str,
    task: Task,
    repo_root: Path,
    *,
    node: str,
    attempt: int,
    checkpoint: Mapping[str, object],
    gate_results: Mapping[str, object],
    transcript_dir: Path | None = None,
    on_snippet: Callable[[str], None] | None = None,
    on_session_id: Callable[[str], None] | None = None,
    max_continuations: int = 2,
) -> AgentResult:
    result = backend.run(role, prompt, on_snippet=on_snippet, on_session_id=on_session_id)
    if transcript_dir is not None:
        write_role_transcript(transcript_dir, node, attempt, result.raw)
    for continuation in range(1, max_continuations + 1):
        if result.interruption is not InterruptionReason.CONTEXT_LIMIT:
            break
        continuation_prompt = prompt + "\n\n" + build_continuation_context(
            task,
            {
                **checkpoint,
                "continuation": continuation,
                "prior_session_id": result.session_id,
            },
            result.raw,
            _working_diff(repo_root),
            gate_results,
        )
        result = backend.run(role, continuation_prompt, on_snippet=on_snippet, on_session_id=on_session_id)
        if transcript_dir is not None:
            write_role_transcript(transcript_dir, f"{node}-continuation", attempt * 10 + continuation, result.raw)
    return result


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
            task_id=task.id,
            node="context-gather",
            node_state="running",
            attempt=attempt,
            max_attempts=max_attempts,
        )

        def _on_session_id(sid: str) -> None:
            nonlocal captured_session_id
            captured_session_id = sid
            status.report(
                task_id=task.id,
                node="context-gather",
                node_state="running",
                attempt=attempt,
                max_attempts=max_attempts,
                session_id=sid,
            )

        def _on_snippet(text: str) -> None:
            status.report(
                task_id=task.id,
                node="context-gather",
                node_state="running",
                attempt=attempt,
                max_attempts=max_attempts,
                snippet=text,
                session_id=captured_session_id,
            )

        feedback = "\n".join(errors) if errors else None
        role_prompt = compose_prompt(
            AgentRole.CONTEXT_GATHERER,
            task,
            skills_dir=repo_root / ".pi" / "skills",
            feedback=feedback,
        )
        result = _run_with_context_limit_continuation(
            backend,
            AgentRole.CONTEXT_GATHERER,
            role_prompt,
            task,
            repo_root,
            node="context-gather",
            attempt=attempt,
            checkpoint={
                "node": "context-gather",
                "attempt": attempt,
                "remaining": {"context-gather": max(0, max_attempts - attempt)},
                "completed": [],
            },
            gate_results={"manifest_validation": "not run after interruption"},
            transcript_dir=transcript_dir,
            on_snippet=_on_snippet,
            on_session_id=_on_session_id,
        )
        manifest = result.output
        if manifest.get("already_done"):
            reason = manifest.get("already_done_reason") or "task deliverables already exist"
            status.report(
                task_id=task.id,
                node="context-gather",
                node_state="already-done",
                attempt=attempt,
                max_attempts=max_attempts,
                handoff="→ review: task appears already complete",
                session_id=result.session_id,
                summary=reason,
            )
            return (
                NodeOutcome.ALREADY_DONE,
                manifest,
                NodeEvent("context-gather", "already-done", attempt, {}),
            )
        if manifest.get("reject"):
            extra = _note_backend_failure({"reason": manifest["reject"]}, result)
            status.report(
                task_id=task.id,
                node="context-gather",
                node_state="reject",
                attempt=attempt,
                max_attempts=max_attempts,
                handoff=f"rejected: {manifest['reject']}",
            )
            return NodeOutcome.REJECT, None, NodeEvent("context-gather", "reject", attempt, extra)
        ctx = EvidenceContext(repo_root=repo_root, gates=gates, kb_dir=repo_root / "kb")
        errors = validate_manifest(manifest, repo_root, task=task, ctx=ctx)
        if not errors:
            extra = _note_backend_failure({}, result)
            handoff = _summarize_manifest(manifest)
            status.report(
                task_id=task.id,
                node="context-gather",
                node_state="pass",
                attempt=attempt,
                max_attempts=max_attempts,
                handoff=f"→ dev: {handoff}",
                session_id=result.session_id,
                summary=_summarize_manifest(manifest),
            )
            return NodeOutcome.PASS, manifest, NodeEvent("context-gather", "pass", attempt, extra)
        status.report(
            task_id=task.id,
            node="context-gather",
            node_state="running",
            attempt=attempt,
            max_attempts=max_attempts,
            handoff=f"validation errors: {'; '.join(errors[:3])}",
        )
    extra = {"errors": errors}
    if result is not None:
        extra = _note_backend_failure(extra, result)
    status.report(
        task_id=task.id,
        node="context-gather",
        node_state="reject",
        attempt=max_attempts,
        max_attempts=max_attempts,
        handoff=f"failed after {max_attempts} attempts",
        outcome="rejected",
    )
    return NodeOutcome.REJECT, None, NodeEvent("context-gather", "reject", max_attempts, extra)


def _working_diff(repo_root: Path) -> str:
    result = subprocess.run(
        ["git", "diff", "--binary", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout if result.returncode == 0 else "(working diff unavailable)"


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
    events: list[NodeEvent] | None = None,
) -> tuple[NodeOutcome, NodeEvent]:
    result: AgentResult | None = None
    captured_session_id: str | None = None
    for attempt in range(1, max_iters + 1):
        status.report(
            task_id=task.id,
            node="dev",
            node_state="running",
            attempt=attempt,
            max_attempts=max_iters,
        )

        def _on_session_id(sid: str) -> None:
            nonlocal captured_session_id
            captured_session_id = sid
            status.report(
                task_id=task.id,
                node="dev",
                node_state="running",
                attempt=attempt,
                max_attempts=max_iters,
                session_id=sid,
            )

        def _on_snippet(text: str) -> None:
            status.report(
                task_id=task.id,
                node="dev",
                node_state="running",
                attempt=attempt,
                max_attempts=max_iters,
                snippet=text,
                session_id=captured_session_id,
            )

        role_prompt = compose_prompt(
            AgentRole.DEV,
            task,
            manifest,
            kb_entries,
            feedback,
            skills_dir=repo_root / ".pi" / "skills",
        )
        result = backend.run(
            AgentRole.DEV,
            role_prompt,
            on_snippet=_on_snippet,
            on_session_id=_on_session_id,
        )
        if transcript_dir is not None:
            write_role_transcript(transcript_dir, "dev", attempt, result.raw)
        # A provider context limit interrupts this attempt; it does not spend a
        # fresh dev retry. Continue in a new Pi session from deterministic disk
        # state, while retaining a small bound against repeated provider failure.
        for continuation in range(1, 3):
            if result.interruption is not InterruptionReason.CONTEXT_LIMIT:
                break
            continuation_prompt = role_prompt + "\n\n" + build_continuation_context(
                task,
                {
                    "node": "dev",
                    "attempt": attempt,
                    "continuation": continuation,
                    "remaining": {"dev": max(0, max_iters - attempt)},
                    "completed": [asdict(event) for event in events] if events else [],
                    "prior_session_id": result.session_id,
                },
                result.raw,
                _working_diff(repo_root),
                {"unit": "not run after interruption"},
            )
            result = backend.run(
                AgentRole.DEV,
                continuation_prompt,
                on_snippet=_on_snippet,
                on_session_id=_on_session_id,
            )
            if transcript_dir is not None:
                write_role_transcript(
                    transcript_dir,
                    "dev-continuation",
                    attempt * 10 + continuation,
                    result.raw,
                )
        if gates.run("unit") == 0:
            extra = _note_backend_failure({"tests": "green"}, result)
            status.report(
                task_id=task.id,
                node="dev",
                node_state="pass",
                attempt=attempt,
                max_attempts=max_iters,
                handoff="→ validation: unit tests green",
                session_id=result.session_id,
                summary="changed files; unit tests pass",
            )
            return NodeOutcome.PASS, NodeEvent("dev", "pass", attempt, extra)
        status.report(
            task_id=task.id,
            node="dev",
            node_state="running",
            attempt=attempt,
            max_attempts=max_iters,
            handoff=f"unit tests failed, retry {attempt}/{max_iters}",
        )
    extra = {"reason": "unit tests red"}
    if result is not None:
        extra = _note_backend_failure(extra, result)
    status.report(
        task_id=task.id,
        node="dev",
        node_state="escalate",
        attempt=max_iters,
        max_attempts=max_iters,
        handoff="escalated: unit tests still red",
        outcome="escalated",
    )
    return NodeOutcome.ESCALATE, NodeEvent("dev", "escalate", max_iters, extra)


def run_validation(
    gates: GateRunner,
    task_id: str = "",
    status: StatusReporter = NullStatusReporter(),
    *,
    repo_root: Path | None = None,
    satisfies: list[str] | None = None,
    transcript_dir: Path | None = None,
) -> tuple[NodeOutcome, NodeEvent]:
    status.report(
        task_id=task_id,
        node="validation",
        node_state="running",
        attempt=1,
        max_attempts=1,
        handoff="running sim + integration gates",
    )
    # GATE_NOT_APPLICABLE means the project provides no such suite -- skip it.
    # Only a gate that actually ran and failed fails the node.
    sim_result = gates.run("sim")
    if sim_result not in (0, GATE_NOT_APPLICABLE):
        status.report(
            task_id=task_id,
            node="validation",
            node_state="fail",
            attempt=1,
            max_attempts=1,
            handoff="sim tests failed",
        )
        return NodeOutcome.FAIL, NodeEvent("validation", "fail")
    if gates.run("integration") not in (0, GATE_NOT_APPLICABLE):
        status.report(
            task_id=task_id,
            node="validation",
            node_state="fail",
            attempt=1,
            max_attempts=1,
            handoff="integration tests failed",
        )
        return NodeOutcome.FAIL, NodeEvent("validation", "fail")

    warns: list[str] = []
    if repo_root is not None:
        report, ok = validate_task_requirements(repo_root, satisfies or [])
        if transcript_dir is not None:
            write_validation_report(transcript_dir / "validation-report.json", report)
        # reds = requirements that RAN and failed (block). warns = requirements that
        # could not run (no harness/scenario defined yet) — surface, don't block.
        reds = [e["id"] for e in report["requirements"] if e.get("passed") is False]
        warns = [e["id"] for e in report["requirements"] if "error" in e]
        if reds:
            status.report(
                task_id=task_id,
                node="validation",
                node_state="fail",
                attempt=1,
                max_attempts=1,
                handoff=f"requirements failed: {', '.join(reds)}",
            )
            return NodeOutcome.FAIL, NodeEvent(
                "validation",
                "fail",
                1,
                {"failed_requirements": reds, "requirement_warnings": warns},
            )
        if warns:
            status.report(
                task_id=task_id,
                node="validation",
                node_state="running",
                attempt=1,
                max_attempts=1,
                handoff=(
                    f"⚠ not validated (no harness/scenario defined): {', '.join(warns)} — "
                    "declare a harness in .factory/factory.yaml or run /specify-requirements"
                ),
            )

    status.report(
        task_id=task_id,
        node="validation",
        node_state="pass",
        attempt=1,
        max_attempts=1,
        handoff="→ review: sim + integration gates green",
    )
    return NodeOutcome.PASS, NodeEvent("validation", "pass", 1, {"requirement_warnings": warns})


def run_review(
    backend: AgentBackend,
    gates: GateRunner,
    task: Task,
    kb_entries: list[dict],
    repo_root: Path,
    transcript_dir: Path | None = None,
    status: StatusReporter = NullStatusReporter(),
    events: list[NodeEvent] | None = None,
) -> tuple[NodeOutcome, NodeEvent, list[str]]:
    status.report(task_id=task.id, node="review", node_state="running", attempt=1, max_attempts=1)
    captured_session_id: str | None = None

    def _on_session_id(sid: str) -> None:
        nonlocal captured_session_id
        captured_session_id = sid
        status.report(
            task_id=task.id,
            node="review",
            node_state="running",
            attempt=1,
            max_attempts=1,
            session_id=sid,
        )

    def _on_snippet(text: str) -> None:
        status.report(
            task_id=task.id,
            node="review",
            node_state="running",
            attempt=1,
            max_attempts=1,
            snippet=text,
            session_id=captured_session_id,
        )

    result = _run_with_context_limit_continuation(
        backend,
        AgentRole.REVIEW,
        compose_prompt(
            AgentRole.REVIEW,
            task,
            kb_entries=kb_entries,
            skills_dir=repo_root / ".pi" / "skills",
            # Tells the reviewer the gates already ran, so it stops asking the
            # human to run suites the validation node executed before it started.
            events=events,
        ),
        task,
        repo_root,
        node="review",
        attempt=1,
        checkpoint={
            "node": "review",
            "attempt": 1,
            "remaining": {"review": 1},
            "completed": [asdict(event) for event in events] if events else [],
        },
        gate_results=_event_results(events),
        transcript_dir=transcript_dir,
        on_snippet=_on_snippet,
        on_session_id=_on_session_id,
    )
    out = result.output
    findings = list(out.get("findings", []))
    dod_met = bool(out.get("dod_met"))
    confidence = out.get("confidence") if isinstance(out.get("confidence"), str) else None
    verify = out.get("verify") if isinstance(out.get("verify"), list) else []
    gate = gates.run("full")
    if gate == 0 and dod_met and not findings:
        extra = _note_backend_failure({"confidence": confidence, "verify": verify}, result)
        status.report(
            task_id=task.id,
            node="review",
            node_state="pass",
            attempt=1,
            max_attempts=1,
            handoff="✓ task complete, DoD met, gates pass",
            outcome="completed",
            session_id=result.session_id,
            summary="DoD met; gates pass",
        )
        return NodeOutcome.PASS, NodeEvent("review", "pass", 1, extra), []
    finding_summary = f"{len(findings)} finding(s)" if findings else "DoD not met"
    extra = _note_backend_failure(
        {"findings": len(findings), "gate": gate, "confidence": confidence, "verify": verify},
        result,
    )
    status.report(
        task_id=task.id,
        node="review",
        node_state="changes-requested",
        attempt=1,
        max_attempts=1,
        handoff=f"→ dev: {finding_summary}, gate={'pass' if gate == 0 else 'fail'}",
        session_id=result.session_id,
        summary=_summarize_review(findings),
    )
    return (
        NodeOutcome.CHANGES,
        NodeEvent("review", "changes-requested", 1, extra),
        findings,
    )


def run_session_review(
    backend: AgentBackend,
    task: Task,
    repo_root: Path,
    *,
    events: list[NodeEvent] | None = None,
    existing_kb_titles: list[tuple[str, str]] | None = None,
    transcript_dir: Path | None = None,
    status: StatusReporter = NullStatusReporter(),
) -> AgentResult:
    captured_session_id: str | None = None

    def _on_session_id(sid: str) -> None:
        nonlocal captured_session_id
        captured_session_id = sid
        status.report(
            task_id=task.id,
            node="session-review",
            node_state="running",
            attempt=1,
            max_attempts=1,
            session_id=sid,
        )

    def _on_snippet(text: str) -> None:
        status.report(
            task_id=task.id,
            node="session-review",
            node_state="running",
            attempt=1,
            max_attempts=1,
            snippet=text,
            session_id=captured_session_id,
        )

    prompt = compose_prompt(
        AgentRole.SESSION_REVIEW,
        task,
        events=events,
        existing_kb_titles=existing_kb_titles,
        skills_dir=repo_root / ".pi" / "skills",
    )
    return _run_with_context_limit_continuation(
        backend,
        AgentRole.SESSION_REVIEW,
        prompt,
        task,
        repo_root,
        node="session-review",
        attempt=1,
        checkpoint={
            "node": "session-review",
            "attempt": 1,
            "remaining": {"session-review": 1},
            "completed": [asdict(event) for event in events] if events else [],
        },
        gate_results=_event_results(events),
        transcript_dir=transcript_dir,
        on_snippet=_on_snippet,
        on_session_id=_on_session_id,
    )
