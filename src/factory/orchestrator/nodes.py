from __future__ import annotations

from pathlib import Path

from factory.orchestrator.backends import AgentBackend, GateRunner
from factory.orchestrator.ledger import Task
from factory.orchestrator.prompts import compose_prompt
from factory.orchestrator.status import NullStatusReporter, StatusReporter
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


def run_context_gatherer(
    backend: AgentBackend,
    task: Task,
    repo_root: Path,
    max_attempts: int = 2,
    status: StatusReporter = NullStatusReporter(),
) -> tuple[NodeOutcome, dict | None, NodeEvent]:
    errors: list[str] = []
    result: AgentResult | None = None
    for attempt in range(1, max_attempts + 1):
        status.report(
            task_id=task.id, node="context-gather", node_state="running",
            attempt=attempt, max_attempts=max_attempts,
        )

        def _on_snippet(text: str) -> None:
            status.report(
                task_id=task.id, node="context-gather", node_state="running",
                attempt=attempt, max_attempts=max_attempts, snippet=text,
            )

        result = backend.run(
            AgentRole.CONTEXT_GATHERER, compose_prompt(AgentRole.CONTEXT_GATHERER, task),
            on_snippet=_on_snippet,
        )
        manifest = result.output
        if manifest.get("reject"):
            extra = _note_backend_failure({"reason": manifest["reject"]}, result)
            return NodeOutcome.REJECT, None, NodeEvent("context-gather", "reject", attempt, extra)
        errors = validate_manifest(manifest, repo_root)
        if not errors and manifest.get("coherence", {}).get("proven"):
            extra = _note_backend_failure({}, result)
            return NodeOutcome.PASS, manifest, NodeEvent("context-gather", "pass", attempt, extra)
    extra = {"errors": errors}
    if result is not None:
        extra = _note_backend_failure(extra, result)
    return NodeOutcome.REJECT, None, NodeEvent("context-gather", "reject", max_attempts, extra)


def run_dev(
    backend: AgentBackend,
    gates: GateRunner,
    task: Task,
    manifest: dict,
    kb_entries: list[dict],
    max_iters: int = 3,
    feedback: str | None = None,
    status: StatusReporter = NullStatusReporter(),
) -> tuple[NodeOutcome, NodeEvent]:
    result: AgentResult | None = None
    for attempt in range(1, max_iters + 1):
        status.report(
            task_id=task.id, node="dev", node_state="running",
            attempt=attempt, max_attempts=max_iters,
        )

        def _on_snippet(text: str) -> None:
            status.report(
                task_id=task.id, node="dev", node_state="running",
                attempt=attempt, max_attempts=max_iters, snippet=text,
            )

        result = backend.run(
            AgentRole.DEV, compose_prompt(AgentRole.DEV, task, manifest, kb_entries, feedback),
            on_snippet=_on_snippet,
        )
        if gates.run("unit") == 0:
            extra = _note_backend_failure({"tests": "green"}, result)
            return NodeOutcome.PASS, NodeEvent("dev", "pass", attempt, extra)
    extra = {"reason": "unit tests red"}
    if result is not None:
        extra = _note_backend_failure(extra, result)
    return NodeOutcome.ESCALATE, NodeEvent("dev", "escalate", max_iters, extra)


def run_validation(
    gates: GateRunner, task_id: str = "", status: StatusReporter = NullStatusReporter()
) -> tuple[NodeOutcome, NodeEvent]:
    status.report(task_id=task_id, node="validation", node_state="running", attempt=1, max_attempts=1)
    if gates.run("sim") == 0:
        return NodeOutcome.PASS, NodeEvent("validation", "pass")
    return NodeOutcome.FAIL, NodeEvent("validation", "fail")


def run_review(
    backend: AgentBackend,
    gates: GateRunner,
    task: Task,
    status: StatusReporter = NullStatusReporter(),
) -> tuple[NodeOutcome, NodeEvent, list[str]]:
    status.report(task_id=task.id, node="review", node_state="running", attempt=1, max_attempts=1)

    def _on_snippet(text: str) -> None:
        status.report(
            task_id=task.id, node="review", node_state="running",
            attempt=1, max_attempts=1, snippet=text,
        )

    result = backend.run(AgentRole.REVIEW, compose_prompt(AgentRole.REVIEW, task), on_snippet=_on_snippet)
    out = result.output
    findings = list(out.get("findings", []))
    dod_met = bool(out.get("dod_met"))
    gate = gates.run("full")
    if gate == 0 and dod_met and not findings:
        extra = _note_backend_failure({}, result)
        return NodeOutcome.PASS, NodeEvent("review", "pass", 1, extra), []
    extra = _note_backend_failure({"findings": len(findings), "gate": gate}, result)
    return (
        NodeOutcome.CHANGES,
        NodeEvent("review", "changes-requested", 1, extra),
        findings,
    )
