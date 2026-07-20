from __future__ import annotations

from pathlib import Path

from factory.kb.retrieval import select_entries
from factory.orchestrator.backends import AgentBackend, GateRunner
from factory.orchestrator.ledger import Task, load_tasks, next_todo, set_status
from factory.orchestrator.nodes import (
    run_context_gatherer,
    run_dev,
    run_review,
    run_validation,
)
from factory.orchestrator.session import build_record, write_session
from factory.orchestrator.status import NullStatusReporter, StatusReporter
from factory.orchestrator.types import NodeEvent, NodeOutcome, TaskResult
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
) -> TaskResult:
    events: list[NodeEvent] = []

    c_outcome, manifest, c_ev = run_context_gatherer(backend, task, repo_root, status=status)
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
            backend, gates, task, manifest, kb_entries, max_dev_iters, feedback, status=status
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

        r_outcome, r_ev, findings = run_review(backend, gates, task, status=status)
        events.append(r_ev)
        if r_outcome == NodeOutcome.PASS:
            _report_node(status, task.id, r_ev, 1, outcome="completed")
            return TaskResult(task.id, task.title, "completed", iterations, events, True, manifest)
        _report_node(status, task.id, r_ev, 1)
        feedback = "\n".join(findings) if findings else "review requested changes"

    status.report(
        task_id=task.id, node="review", node_state="changes-requested",
        attempt=iterations, max_attempts=max_review_cycles, outcome="escalated",
    )
    return TaskResult(task.id, task.title, "escalated", iterations, events, False, manifest)


def run_next(
    repo_root: Path,
    backend: AgentBackend,
    gates: GateRunner,
    *,
    # Finding 3 (final review): PiAgentBackend never passes --model to the real
    # `pi` CLI (it runs on Pi's own ambient/default model selection), so naming a
    # specific model here would be a false claim baked into the session record.
    # "pi:unspecified" honestly reflects "ran via Pi's own model selection, not
    # explicitly chosen by the orchestrator" instead of a model that was never
    # actually selected.
    model_backend: str = "pi:unspecified",
    session_id: str | None = None,
    git_info: dict | None = None,
    status: StatusReporter = NullStatusReporter(),
) -> Path | None:
    tasks = load_tasks(repo_root / "tasks")
    task = next_todo(tasks)
    if task is None:
        return None

    result = run_task(task, backend, gates, repo_root, status=status)
    set_status(task, "done" if result.outcome == "completed" else result.outcome)

    sid = session_id or _default_session_id()
    record = build_record(sid, model_backend, [result], git_info or {})
    return write_session(repo_root / "sessions", record)


def _default_session_id() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
