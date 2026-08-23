"""Build CI's required command list from the compiled project obligations."""
from __future__ import annotations

from pathlib import Path

from coherence.policy.compiler import compile_obligations


class NoBlockingObligationError(RuntimeError):
    """The project has no complete blocking CI obligation set."""


def required_ci_commands(root: Path) -> list[str]:
    """Return compiled blocking CI commands followed by structural checks."""
    obligations = compile_obligations(root, "project")
    selected = [
        obligation
        for obligation in obligations
        if obligation.kind == "ci_verification" and obligation.requiredness == "blocking"
    ]
    if not selected:
        raise NoBlockingObligationError("no blocking ci_verification obligations found")

    commands: list[str] = []
    for obligation in selected:
        if not obligation.resolve_cmd or any(not command.strip() for command in obligation.resolve_cmd):
            raise NoBlockingObligationError(
                f"blocking obligation {obligation.id} has no complete resolve_cmd"
            )
        commands.extend(obligation.resolve_cmd)

    return commands + [
        "coherence trace check",
        "coherence register check",
    ]
