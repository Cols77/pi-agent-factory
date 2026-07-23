from __future__ import annotations

from pathlib import Path

from factory.kb.retrieval import list_kb_titles, select_entries
from factory.orchestrator.backends import AgentBackend, GateRunner
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
from factory.orchestrator.nodes import (
    run_context_gatherer,
    run_dev,
    run_review,
    run_validation,
)
from factory.orchestrator.prompts import compose_prompt
from factory.orchestrator.session import build_record, write_session
from factory.orchestrator.status import NullStatusReporter, StatusReporter
from factory.orchestrator.transcripts import write_role_transcript
from factory.orchestrator.types import AgentRole, NodeEvent, NodeOutcome, TaskResult
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


def _report_node(
    status: StatusReporter, task_id: str, ev: NodeEvent, max_attempts: int, outcome: str | None = None
) -> None:
    status.report(
        task_id=task_id, node=ev.node, node_state=ev.result,
        attempt=ev.attempts, max_attempts=max_attempts, outcome=outcome,
    )


def run_task(
    task: Task,
    backend: AgentBackend,
    gates: GateRunner,
    repo_root: Path,
    *,
    max_dev_iters: int = 3,
    max_review_cycles: int = 3,
    status: StatusReporter = NullStatusReporter(),
    human_review: HumanReviewGate | None = None,
    git_ops: GitOps = SubprocessGitOps(),
    transcript_dir: Path | None = None,
) -> TaskResult:
    events: list[NodeEvent] = []
    start_commit = git_ops.head_commit(repo_root)

    c_outcome, manifest, c_ev = run_context_gatherer(
        backend, task, repo_root, transcript_dir=transcript_dir, status=status
    )
    events.append(c_ev)
    if c_outcome == NodeOutcome.REJECT or manifest is None:
        _report_node(status, task.id, c_ev, c_ev.attempts, outcome="rejected")
        return TaskResult(task.id, task.title, "rejected", 1, events, False, None)
    _report_node(status, task.id, c_ev, c_ev.attempts)

    kb_ids = select_entries(repo_root / "kb", manifest["context"].get("source_files", []), [])
    kb_entries = _load_kb_entries(repo_root / "kb", kb_ids)

    feedback: str | None = None
    iterations = 0
    for _ in range(max_review_cycles):
        iterations += 1

        d_outcome, d_ev = run_dev(
            backend, gates, task, manifest, kb_entries, repo_root, max_dev_iters, feedback,
            transcript_dir=transcript_dir, status=status,
        )
        events.append(d_ev)
        if d_outcome == NodeOutcome.ESCALATE:
            _report_node(status, task.id, d_ev, max_dev_iters, outcome="escalated")
            return TaskResult(task.id, task.title, "escalated", iterations, events, False, manifest)
        _report_node(status, task.id, d_ev, max_dev_iters)

        v_outcome, v_ev = run_validation(gates, task.id, status=status)
        events.append(v_ev)
        _report_node(status, task.id, v_ev, 1)
        if v_outcome == NodeOutcome.FAIL:
            feedback = "functional/sim tests failed"
            continue

        review_changed_files = git_ops.changed_files(repo_root, start_commit)
        review_kb_ids = select_entries(repo_root / "kb", review_changed_files, [])
        review_kb_entries = _load_kb_entries(repo_root / "kb", review_kb_ids)

        r_outcome, r_ev, findings = run_review(
            backend, gates, task, review_kb_entries, repo_root,
            transcript_dir=transcript_dir, status=status,
        )
        events.append(r_ev)
        if r_outcome == NodeOutcome.PASS:
            if human_review is not None:
                assert start_commit is not None
                status.report(
                    task_id=task.id, node="human-review", node_state="blocked",
                    attempt=1, max_attempts=1, handoff="waiting for you to review the diff",
                    start_commit=start_commit,
                )
                decision = human_review.request_review(task.id, start_commit)
                if decision.decision == "approve":
                    git_ops.commit_all(repo_root, "review: address direct edits during human review")
                    _report_node(status, task.id, r_ev, 1, outcome="completed")
                    return TaskResult(task.id, task.title, "completed", iterations, events, True, manifest)
                _report_node(status, task.id, r_ev, 1)
                feedback = format_review_feedback(decision.comments)
                continue
            _report_node(status, task.id, r_ev, 1, outcome="completed")
            return TaskResult(task.id, task.title, "completed", iterations, events, True, manifest)
        _report_node(status, task.id, r_ev, 1)
        feedback = "\n".join(findings) if findings else "review requested changes"

    last_event = events[-1]
    status.report(
        task_id=task.id, node=last_event.node, node_state=last_event.result,
        attempt=iterations, max_attempts=max_review_cycles, outcome="escalated"
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
) -> Path | None:
    tasks = load_tasks(repo_root / "tasks")
    if task_id is not None:
        task = get_task(tasks, task_id)
        if task is None:
            raise TaskNotFoundError(task_id)
        if task.status != "todo":
            raise TaskNotTodoError(task_id, task.status)
    else:
        task = next_todo(tasks)
        if task is None:
            return None

    result = run_task(
        task, backend, gates, repo_root, status=status, human_review=human_review,
        git_ops=git_ops, transcript_dir=transcript_dir,
    )
    # Only mark done on success. Rejected/escalated tasks go back to todo
    # so they can be retried (possibly with a different agent or after fixes).
    set_status(task, "done" if result.outcome == "completed" else "todo")

    sid = session_id or _default_session_id()
    record = build_record(sid, model_backend, [result], git_info or {})
    path = write_session(repo_root / "sessions", record)

    status.report(task_id=task.id, node="session-review", node_state="running", attempt=1, max_attempts=1)
    session_review_prompt = compose_prompt(
        AgentRole.SESSION_REVIEW, task,
        events=result.events, existing_kb_titles=list_kb_titles(repo_root / "kb"),
        skills_dir=repo_root / ".pi" / "skills",
    )
    session_review_result = backend.run(AgentRole.SESSION_REVIEW, session_review_prompt)
    if transcript_dir is not None:
        write_role_transcript(transcript_dir, "session-review", 1, session_review_result.raw)
    status.report(
        task_id=task.id, node="session-review", node_state="pass",
        attempt=1, max_attempts=1, outcome="completed",
    )

    return path


def _default_session_id() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
