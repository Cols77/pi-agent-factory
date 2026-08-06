from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from factory.evidence.artifacts import ArtifactStore
from factory.evidence.finalize import finalize_run_evidence
from factory.kb.retrieval import list_kb_titles, select_entries
from factory.orchestrator.backends import AgentBackend, GateRunner
from factory.orchestrator.execution import RunExecution
from factory.orchestrator.git_ops import GitOps, SubprocessGitOps
from factory.orchestrator.human_review import HumanReviewGate, format_review_feedback
from factory.orchestrator.ledger import (
    Task,
    TaskNotFoundError,
    TaskNotTodoError,
    get_task,
    load_tasks,
    next_todo,
    set_status,
)
from factory.orchestrator.deliverables import parse_deliverables
from factory.orchestrator.nodes import (
    run_context_gatherer,
    run_dev,
    run_review,
    run_validation,
)
from factory.orchestrator.prompts import compose_prompt
from factory.orchestrator.journal import RunCheckpoint
from factory.orchestrator.review_guide import (
    read_requirements_report,
    read_validation,
    write_review_guide,
)
from factory.orchestrator.session import build_record, write_session
from factory.orchestrator.status import NullStatusReporter, StatusReporter
from factory.orchestrator.transcripts import write_role_transcript
from factory.orchestrator.types import AgentRole, NodeEvent, NodeOutcome, TaskResult
from factory.preflight.checks import run_completion_preflight
from factory.validation.kb_validator import parse_entry


def _load_kb_entries(kb_dir: Path, ids: list[str]) -> list[dict]:
    if not kb_dir.exists():
        return []
    wanted = set(ids)
    out = []
    for path in sorted(kb_dir.glob("kb-*.md")):
        entry = parse_entry(path)
        if str(entry.get("id")) in wanted:
            out.append(entry)
    return out


def _commit_message(task: Task) -> str:
    return f"{task.id}: {task.title}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _report_node(
    status: StatusReporter,
    task_id: str,
    ev: NodeEvent,
    max_attempts: int,
    outcome: str | None = None,
) -> None:
    status.report(
        task_id=task_id,
        node=ev.node,
        node_state=ev.result,
        attempt=ev.attempts,
        max_attempts=max_attempts,
        outcome=outcome,
    )


def run_task(
    task: Task,
    backend: AgentBackend,
    gates: GateRunner,
    repo_root: Path,
    *,
    max_dev_iters: int = 3,
    max_review_cycles: int = 3,
    max_human_rounds: int = 3,
    status: StatusReporter = NullStatusReporter(),
    human_review: HumanReviewGate | None = None,
    git_ops: GitOps = SubprocessGitOps(),
    transcript_dir: Path | None = None,
    start_commit: str | None = None,
    execution: RunExecution | None = None,
    resume: RunCheckpoint | None = None,
) -> TaskResult:
    events: list[NodeEvent] = []
    start_commit = start_commit or git_ops.head_commit(repo_root)

    context_record = next(
        (
            item
            for item in reversed(resume.completed if resume is not None else [])
            if item.get("node") == "context-gather"
        ),
        None,
    )
    if resume is not None and resume.node != "context-gather" and context_record is not None:
        context_data = context_record.get("data", {})
        manifest = context_data.get("manifest")
        c_outcome = NodeOutcome(context_data.get("outcome", "pass"))
        raw_event = context_data.get("event", {})
        c_ev = NodeEvent(**raw_event) if raw_event else NodeEvent("context-gather", "pass")
    else:
        c_outcome, manifest, c_ev = run_context_gatherer(
            backend, task, repo_root, transcript_dir=transcript_dir, status=status, gates=gates
        )
        if execution is not None:
            execution.record(
                node="context-gather",
                state="completed" if manifest is not None else "failed",
                attempt=c_ev.attempts,
                next_node="dev" if manifest is not None else "closed",
                remaining={"dev": max_dev_iters, "review": max_review_cycles},
                data={"outcome": c_outcome.value, "manifest": manifest, "event": asdict(c_ev)},
            )
    events.append(c_ev)
    if c_outcome == NodeOutcome.REJECT or manifest is None:
        _report_node(status, task.id, c_ev, c_ev.attempts, outcome="rejected")
        return TaskResult(task.id, task.title, "rejected", 1, events, False, None)
    _report_node(status, task.id, c_ev, c_ev.attempts)

    # ALREADY_DONE: the task's work already exists. Skip the dev node on the
    # first pass and go straight to validation + review (so the sim/review
    # gates still confirm it). If those gates fail, i>0 lets dev run normally
    # on the next iteration -- a wrong "already done" self-corrects.
    already_done = c_outcome == NodeOutcome.ALREADY_DONE

    kb_ids = select_entries(repo_root / "kb", manifest["context"].get("source_files", []), [])
    kb_entries = _load_kb_entries(repo_root / "kb", kb_ids)

    feedback: str | None = None
    iterations = 0
    first_dev = True  # already_done skips ONLY the very first dev attempt
    resume_at = resume.node if resume is not None else None
    addressed: list[str] = []

    # Outer loop = human rounds; each human reject grants a FRESH inner (LLM)
    # review budget. --auto (no human) runs the inner loop once, then completes
    # or escalates -- there is no human to fall back to.
    outer_rounds = max_human_rounds if human_review is not None else 1
    for _human_round in range(outer_rounds):
        # Inner loop = dev -> validation -> LLM review, until the reviewer passes
        # or the budget is exhausted.
        llm_passed = False
        r_ev: NodeEvent | None = None
        review_findings: list[str] = []
        for _cycle in range(max_review_cycles):
            iterations += 1

            resume_skips_dev = first_dev and resume_at in {"validation", "review", "human-review"}
            if not (already_done and first_dev) and not resume_skips_dev:
                d_outcome, d_ev = run_dev(
                    backend,
                    gates,
                    task,
                    manifest,
                    kb_entries,
                    repo_root,
                    max_dev_iters,
                    feedback,
                    transcript_dir=transcript_dir,
                    status=status,
                )
                events.append(d_ev)
                if execution is not None:
                    execution.record(
                        node="dev",
                        state="completed" if d_outcome is not NodeOutcome.ESCALATE else "failed",
                        attempt=d_ev.attempts,
                        next_node="validation" if d_outcome is not NodeOutcome.ESCALATE else "closed",
                        remaining={
                            "dev": max(0, max_dev_iters - d_ev.attempts),
                            "review": max(0, max_review_cycles - _cycle),
                        },
                        data={"outcome": d_outcome.value, "event": asdict(d_ev)},
                    )
                if d_outcome == NodeOutcome.ESCALATE:
                    _report_node(status, task.id, d_ev, max_dev_iters, outcome="escalated")
                    return TaskResult(
                        task.id, task.title, "escalated", iterations, events, False, manifest
                    )
                _report_node(status, task.id, d_ev, max_dev_iters)
            first_dev = False
            resume_at = None

            v_outcome, v_ev = run_validation(
                gates,
                task.id,
                status=status,
                repo_root=repo_root,
                satisfies=task.satisfies,
                transcript_dir=transcript_dir,
            )
            events.append(v_ev)
            if execution is not None:
                execution.record(
                    node="validation",
                    state="completed",
                    attempt=v_ev.attempts,
                    next_node="dev" if v_outcome is NodeOutcome.FAIL else "review",
                    remaining={
                        "dev": max(0, max_dev_iters - iterations),
                        "review": max(0, max_review_cycles - _cycle),
                    },
                    data={"outcome": v_outcome.value, "event": asdict(v_ev)},
                )
            _report_node(status, task.id, v_ev, 1)
            if v_outcome == NodeOutcome.FAIL:
                reds = v_ev.extra.get("failed_requirements")
                feedback = (
                    "requirements failed: " + ", ".join(reds)
                    if reds
                    else "functional/sim tests failed"
                )
                continue

            review_changed_files = git_ops.changed_files(repo_root, start_commit)
            review_kb_ids = select_entries(repo_root / "kb", review_changed_files, [])
            review_kb_entries = _load_kb_entries(repo_root / "kb", review_kb_ids)

            r_outcome, r_ev, review_findings = run_review(
                backend,
                gates,
                task,
                review_kb_entries,
                repo_root,
                transcript_dir=transcript_dir,
                status=status,
                events=list(events),
            )
            events.append(r_ev)
            if execution is not None:
                execution.record(
                    node="review",
                    state="completed",
                    attempt=r_ev.attempts,
                    next_node=(
                        "human-review"
                        if r_outcome is NodeOutcome.PASS and human_review is not None
                        else "code-commit"
                        if r_outcome is NodeOutcome.PASS
                        else "dev"
                    ),
                    remaining={
                        "dev": max(0, max_dev_iters - iterations),
                        "review": max(0, max_review_cycles - _cycle - 1),
                    },
                    data={
                        "outcome": r_outcome.value,
                        "findings": review_findings,
                        "event": asdict(r_ev),
                    },
                )
            if r_outcome == NodeOutcome.PASS:
                llm_passed = True
                break
            _report_node(status, task.id, r_ev, 1)
            feedback = "\n".join(review_findings) if review_findings else "review requested changes"
            addressed.extend(f"review (round {_cycle + 1}): {f}" for f in review_findings)

        # --auto: no human to fall back to -- complete on an LLM pass, else escalate.
        if human_review is None:
            if llm_passed:
                assert r_ev is not None
                git_ops.commit_all(repo_root, _commit_message(task))
                if execution is not None:
                    execution.record(
                        node="code-commit",
                        state="completed",
                        attempt=1,
                        next_node="evidence-finalize",
                        remaining={},
                        data={"commit": git_ops.head_commit(repo_root)},
                    )
                _report_node(status, task.id, r_ev, 1, outcome="completed")
                return TaskResult(
                    task.id, task.title, "completed", iterations, events, True, manifest
                )
            break  # escalate below

        # Human is in the loop: surface to them whether or NOT the LLM confirmed,
        # so the reviewer can never silently escalate them out.
        assert start_commit is not None
        if llm_passed:
            handoff = (
                "task appears already complete -- approve to mark done"
                if already_done
                else "waiting for you to review the diff"
            )
        else:
            outstanding = "; ".join(review_findings[:3]) if review_findings else "DoD not met"
            handoff = (
                f"reviewer couldn't confirm -- outstanding: {outstanding} "
                "(approve to accept, reject to send back)"
            )
        if transcript_dir is not None:
            guide = {
                "confidence": r_ev.extra.get("confidence") if r_ev is not None else None,
                "verify": r_ev.extra.get("verify", []) if r_ev is not None else [],
                "validation": read_validation(transcript_dir),
                "requirements": read_requirements_report(transcript_dir),
                "addressed": list(dict.fromkeys(addressed)),  # dedup, keep order
            }
            write_review_guide(transcript_dir / "review-guide.json", guide)
        status.report(
            task_id=task.id,
            node="human-review",
            node_state="blocked",
            attempt=1,
            max_attempts=1,
            handoff=handoff,
            start_commit=start_commit,
            already_done=already_done,
            deliverables=parse_deliverables(task.body) if already_done else [],
        )
        if execution is not None:
            execution.record(
                node="human-review",
                state="started",
                attempt=_human_round + 1,
                next_node="human-review",
                remaining={"human": max(0, outer_rounds - _human_round)},
            )
        decision = human_review.request_review(task.id, start_commit)
        if execution is not None:
            execution.record(
                node="human-review",
                state="completed",
                attempt=_human_round + 1,
                next_node="code-commit" if decision.decision == "approve" else "dev",
                remaining={"human": max(0, outer_rounds - _human_round - 1)},
                data={
                    "decision": decision.decision,
                    "annotations": [asdict(item) for item in decision.annotations],
                },
            )
        if decision.decision == "approve":
            git_ops.commit_all(repo_root, _commit_message(task))
            if execution is not None:
                execution.record(
                    node="code-commit",
                    state="completed",
                    attempt=1,
                    next_node="evidence-finalize",
                    remaining={},
                    data={"commit": git_ops.head_commit(repo_root)},
                )
            status.report(
                task_id=task.id,
                node="human-review",
                node_state="approved",
                attempt=1,
                max_attempts=1,
                handoff="approved",
                start_commit=start_commit,
            )
            if r_ev is not None:
                _report_node(status, task.id, r_ev, 1, outcome="completed")
            return TaskResult(task.id, task.title, "completed", iterations, events, True, manifest)

        # Reject: send the human's comments back to dev; the next outer round
        # gets a fresh inner budget. After a human round, dev always runs (an
        # already-done task is no longer treated as pre-complete).
        status.report(
            task_id=task.id,
            node="human-review",
            node_state="changes-requested",
            attempt=1,
            max_attempts=1,
            handoff="rejected: dev will retry",
            start_commit=start_commit,
        )
        if r_ev is not None:
            _report_node(status, task.id, r_ev, 1)
        feedback = format_review_feedback(decision.annotations)
        addressed.extend(
            f"your comment (round {_human_round + 1}) on "
            f"{a.file}{':' + str(a.line) if a.line is not None else ''}: {a.body}"
            for a in decision.annotations
        )
        already_done = False

    # Escalate: --auto reviewer never passed, or the human rejected every round.
    last_event = events[-1]
    status.report(
        task_id=task.id,
        node=last_event.node,
        node_state=last_event.result,
        attempt=iterations,
        max_attempts=max_review_cycles,
        outcome="escalated",
    )
    return TaskResult(task.id, task.title, "escalated", iterations, events, False, manifest)


def run_next(
    repo_root: Path,
    backend: AgentBackend,
    gates: GateRunner,
    *,
    # Finding 3 (final review), corrected 2026-07-20: PiAgentBackend DOES pass
    # --provider/--model through to the real `pi` CLI when the caller supplies
    # them (see pi_backend.py's _build_command, and __main__.py's --provider/
    # --model flags) -- verified live via `pi -p` with an explicit override.
    # This default only covers the case where the caller supplies neither, in
    # which case the run falls back to Pi's own ambient/default model
    # selection, so "pi:unspecified" still honestly labels that fallback path
    # (as opposed to a model that was actively chosen but not recorded).
    model_backend: str = "pi:unspecified",
    session_id: str | None = None,
    git_info: dict | None = None,
    status: StatusReporter = NullStatusReporter(),
    task_id: str | None = None,
    human_review: HumanReviewGate | None = None,
    git_ops: GitOps = SubprocessGitOps(),
    transcript_dir: Path | None = None,
    force: bool = False,
    artifact_store: ArtifactStore | None = None,
    evidence_dir: Path | None = None,
    checkpoint_runs: bool = False,
    resume: RunCheckpoint | None = None,
) -> Path | None:
    tasks = load_tasks(repo_root / "tasks")
    if resume is not None and task_id is None:
        task_id = resume.task_id
    if task_id is not None:
        task = get_task(tasks, task_id)
        if task is None:
            raise TaskNotFoundError(task_id)
        # `force` re-runs a task that isn't `todo` (e.g. one left `done` or
        # `in-progress` after a manual intervention), so the pipeline can be
        # resumed instead of dead-ending with TaskNotTodoError (RC3).
        if task.status != "todo" and not force and resume is None:
            raise TaskNotTodoError(task_id, task.status)
    else:
        # Pick the next todo task by STATUS only. A task whose Create:/Test:
        # deliverables happen to exist on disk is NOT necessarily complete (it may
        # have stopped at dev-fail with files committed); hiding it here silently
        # swallows unfinished work. Genuinely-done work is handled at run time by
        # the context-gatherer's already-done routing, which verifies via the gates.
        task = next_todo(tasks)
        if task is None:
            return None

    sid = resume.run_id if resume is not None else session_id or _default_session_id()
    started_at = _utc_now()
    start_commit = resume.start_commit if resume is not None else git_ops.head_commit(repo_root)
    execution = (
        RunExecution.create(repo_root, sid, task.id, start_commit, git_ops)
        if checkpoint_runs or resume is not None
        else None
    )
    if execution is not None and resume is None:
        execution.record(
            node="context-gather",
            state="started",
            attempt=1,
            next_node="context-gather",
            remaining={"dev": 3, "review": 3},
        )
    result = run_task(
        task,
        backend,
        gates,
        repo_root,
        status=status,
        human_review=human_review,
        git_ops=git_ops,
        transcript_dir=transcript_dir,
        start_commit=start_commit,
        execution=execution,
        resume=resume,
    )
    result.start_commit = start_commit
    result.result_commit = git_ops.head_commit(repo_root)
    if result.outcome == "completed" and transcript_dir is not None:
        completion = run_completion_preflight(
            repo_root,
            task,
            transcript_dir,
            require_review=human_review is not None and artifact_store is not None,
        )
        if not completion.ok:
            issue_data = [
                {
                    "code": issue.code,
                    "severity": issue.severity.value,
                    "detail": issue.detail,
                }
                for issue in completion.issues
            ]
            event = NodeEvent(
                "completion-preflight",
                "fail",
                1,
                {"issues": issue_data},
            )
            result.events.append(event)
            result.outcome = "escalated"
            result.dod_met = False
            if execution is not None:
                execution.record(
                    node="completion-preflight",
                    state="failed",
                    attempt=1,
                    next_node="closed",
                    remaining={},
                    data={"issues": issue_data},
                )
    # Only mark done on success. Rejected/escalated tasks go back to todo
    # so they can be retried (possibly with a different agent or after fixes).
    set_status(task, "done" if result.outcome == "completed" else "todo")

    if (artifact_store is None) != (evidence_dir is None):
        raise ValueError("artifact_store and evidence_dir must be configured together")
    if artifact_store is not None and evidence_dir is not None:
        runtime_dir = transcript_dir or (
            repo_root / "sessions" / ".factory-transcripts" / sid
        )
        manifest_path = finalize_run_evidence(
            repo_root=repo_root,
            run_id=sid,
            task=task,
            result=result,
            transcript_dir=runtime_dir,
            store=artifact_store,
            evidence_dir=evidence_dir,
            git_ops=git_ops,
            started_at=started_at,
            ended_at=_utc_now(),
        )
        git_ops.commit_paths(
            repo_root,
            [task.path, manifest_path],
            f"evidence: record {task.id} run {sid}",
        )
        if execution is not None:
            execution.artifacts.append(manifest_path.relative_to(repo_root).as_posix())
            execution.record(
                node="evidence-finalize",
                state="completed",
                attempt=1,
                next_node="session-review",
                remaining={},
                data={"manifest": manifest_path.relative_to(repo_root).as_posix()},
            )

    record = build_record(sid, model_backend, [result], git_info or {})
    path = write_session(repo_root / "sessions", record)

    captured_session_id: str | None = None
    status.report(
        task_id=task.id, node="session-review", node_state="running", attempt=1, max_attempts=1
    )
    session_review_prompt = compose_prompt(
        AgentRole.SESSION_REVIEW,
        task,
        events=result.events,
        existing_kb_titles=list_kb_titles(repo_root / "kb"),
        skills_dir=repo_root / ".pi" / "skills",
    )

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

    session_review_result = backend.run(
        AgentRole.SESSION_REVIEW, session_review_prompt, on_session_id=_on_session_id
    )
    if transcript_dir is not None:
        write_role_transcript(transcript_dir, "session-review", 1, session_review_result.raw)
    if execution is not None:
        execution.record(
            node="session-review",
            state="completed",
            attempt=1,
            next_node="closed",
            remaining={},
            session_id=session_review_result.session_id,
        )
    status.report(
        task_id=task.id,
        node="session-review",
        node_state="pass",
        attempt=1,
        max_attempts=1,
        outcome="completed",
        session_id=session_review_result.session_id,
    )

    return path


def _default_session_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
