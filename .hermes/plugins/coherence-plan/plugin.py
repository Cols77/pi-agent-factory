"""Thin Hermes adapter for the Coherence planning projection.

The safety-critical logic (safe run-id grammar, argv-only command building,
JSON contract parsing, exit-code handling, and text rendering) lives in
``coherence.planning.legal_actions_adapter`` so it is not duplicated -- and
cannot silently re-diverge -- between this Hermes adapter and any other host
adapter (e.g. Claude Code's `.claude/commands/coherence-plan.md`). This file
only supplies the Hermes-specific framing: how the raw command text arrives,
the Hermes-specific usage message, and registration with the Hermes host.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from coherence.planning.legal_actions_adapter import is_safe_run_id, legal_actions_report


def _run(raw_args: str) -> str:
    run_id = raw_args.strip()
    if not is_safe_run_id(run_id):
        return "usage: /coherence-plan <run-id>"
    return legal_actions_report(Path.cwd(), run_id)


def register(ctx: Any) -> None:
    """Register the namespaced command without relying on optional host state."""
    ctx.register_command(
        "coherence-plan",
        _run,
        description="Inspect Coherence-authorized planning actions for a run",
    )
