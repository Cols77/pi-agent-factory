from __future__ import annotations

import json

from factory.orchestrator.ledger import Task


def _bounded(value: str, limit: int = 20_000) -> str:
    if len(value) <= limit:
        return value
    return value[-limit:] + "\n[earlier content omitted]"


def build_continuation_context(
    task: Task,
    checkpoint: dict,
    prior_output: str,
    diff: str,
    gate_results: dict[str, object],
) -> str:
    """Build deterministic context for a fresh agent after context exhaustion."""
    return "\n".join(
        [
            "# Factory continuation after explicit context-limit interruption",
            "",
            "This is a fresh agent session for the same factory attempt.",
            "Inspect the repository and recorded state before acting. Do not repeat completed work.",
            "Do not claim provenance, decisions, or validation that are absent below.",
            "",
            f"## Task {task.id}: {task.title}",
            task.body,
            "",
            "## Deterministic checkpoint",
            json.dumps(checkpoint, indent=2, sort_keys=True),
            "",
            "## Current working-tree diff",
            _bounded(diff) or "(no tracked diff)",
            "",
            "## Recorded gate results",
            json.dumps(gate_results, indent=2, sort_keys=True),
            "",
            "## Prior interrupted output",
            _bounded(prior_output),
            "",
            "Continue only the remaining work and emit the role's required structured result.",
        ]
    )
