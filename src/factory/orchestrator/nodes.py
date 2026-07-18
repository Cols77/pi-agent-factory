from __future__ import annotations

from pathlib import Path

from factory.orchestrator.backends import AgentBackend, GateRunner
from factory.orchestrator.ledger import Task
from factory.orchestrator.prompts import compose_prompt
from factory.orchestrator.types import AgentRole, NodeEvent, NodeOutcome
from factory.validation.manifest_validator import validate_manifest


def run_context_gatherer(
    backend: AgentBackend, task: Task, repo_root: Path, max_attempts: int = 2
) -> tuple[NodeOutcome, dict | None, NodeEvent]:
    errors: list[str] = []
    for attempt in range(1, max_attempts + 1):
        result = backend.run(AgentRole.CONTEXT_GATHERER, compose_prompt(AgentRole.CONTEXT_GATHERER, task))
        manifest = result.output
        if manifest.get("reject"):
            return NodeOutcome.REJECT, None, NodeEvent("context-gather", "reject", attempt,
                                                       {"reason": manifest["reject"]})
        errors = validate_manifest(manifest, repo_root)
        if not errors and manifest.get("coherence", {}).get("proven"):
            return NodeOutcome.PASS, manifest, NodeEvent("context-gather", "pass", attempt)
    return NodeOutcome.REJECT, None, NodeEvent("context-gather", "reject", max_attempts, {"errors": errors})


def run_dev(
    backend: AgentBackend,
    gates: GateRunner,
    task: Task,
    manifest: dict,
    kb_entries: list[dict],
    max_iters: int = 3,
    feedback: str | None = None,
) -> tuple[NodeOutcome, NodeEvent]:
    for attempt in range(1, max_iters + 1):
        backend.run(AgentRole.DEV, compose_prompt(AgentRole.DEV, task, manifest, kb_entries, feedback))
        if gates.run("unit") == 0:
            return NodeOutcome.PASS, NodeEvent("dev", "pass", attempt, {"tests": "green"})
    return NodeOutcome.ESCALATE, NodeEvent("dev", "escalate", max_iters, {"reason": "unit tests red"})
