from __future__ import annotations

from pathlib import Path

from factory.kb.retrieval import select_entries
from factory.orchestrator.backends import AgentBackend, GateRunner
from factory.orchestrator.ledger import Task
from factory.orchestrator.nodes import (
    run_context_gatherer,
    run_dev,
    run_review,
    run_validation,
)
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


def run_task(
    task: Task,
    backend: AgentBackend,
    gates: GateRunner,
    repo_root: Path,
    *,
    max_dev_iters: int = 3,
    max_review_cycles: int = 3,
) -> TaskResult:
    events: list[NodeEvent] = []

    c_outcome, manifest, c_ev = run_context_gatherer(backend, task, repo_root)
    events.append(c_ev)
    if c_outcome == NodeOutcome.REJECT or manifest is None:
        return TaskResult(task.id, task.title, "rejected", 1, events, False, None)

    kb_ids = select_entries(repo_root / "kb", manifest["context"].get("source_files", []), [])
    kb_entries = _load_kb_entries(repo_root / "kb", kb_ids)

    feedback: str | None = None
    iterations = 0
    for _ in range(max_review_cycles):
        iterations += 1

        d_outcome, d_ev = run_dev(backend, gates, task, manifest, kb_entries, max_dev_iters, feedback)
        events.append(d_ev)
        if d_outcome == NodeOutcome.ESCALATE:
            return TaskResult(task.id, task.title, "escalated", iterations, events, False, manifest)

        v_outcome, v_ev = run_validation(gates)
        events.append(v_ev)
        if v_outcome == NodeOutcome.FAIL:
            feedback = "functional/sim tests failed"
            continue

        r_outcome, r_ev, findings = run_review(backend, gates, task)
        events.append(r_ev)
        if r_outcome == NodeOutcome.PASS:
            return TaskResult(task.id, task.title, "completed", iterations, events, True, manifest)
        feedback = "\n".join(findings) if findings else "review requested changes"

    return TaskResult(task.id, task.title, "escalated", iterations, events, False, manifest)
