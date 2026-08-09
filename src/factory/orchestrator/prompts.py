from __future__ import annotations

from pathlib import Path

from factory.orchestrator.ledger import Task
from factory.orchestrator.roles import ROLE_PROMPTS, ROLE_SKILLS
from factory.orchestrator.skills import load_skill_block
from factory.orchestrator.types import AgentRole, NodeEvent


def compose_prompt(
    role: AgentRole,
    task: Task,
    manifest: dict | None = None,
    kb_entries: list[dict] | None = None,
    feedback: str | None = None,
    *,
    events: list[NodeEvent] | None = None,
    final_outcome: str | None = None,
    existing_kb_titles: list[tuple[str, str]] | None = None,
    skills_dir: Path,
) -> str:
    lines: list[str] = []
    lines.append(f"# Role: {role.value}")
    lines.append(ROLE_PROMPTS[role])
    lines.append("")
    lines.append("## Loaded skills")
    for skill in ROLE_SKILLS[role]:
        lines.append(load_skill_block(skills_dir, skill))
    lines.append("")
    lines.append(f"## Task {task.id}: {task.title}")
    lines.append(task.body.strip())
    lines.append("")
    lines.append("## Definition of Done")
    for crit in task.dod:
        lines.append(f"- {crit}")

    if manifest is not None:
        lines.append("")
        lines.append("## Context (from manifest)")
        ctx = manifest.get("context")
        if not isinstance(ctx, dict):
            ctx = {}
        for f in ctx.get("source_files", []):
            lines.append(f"- {f}")

    if kb_entries:
        lines.append("")
        lines.append("## Known issues (knowledge base)")
        for e in kb_entries:
            lines.append(f"- {e.get('id')}: {e.get('title')}")

    if feedback:
        lines.append("")
        lines.append("## Feedback to address")
        lines.append(feedback)

    if events:
        lines.append("")
        lines.append("## What happened this run")
        for ev in events:
            plural = "attempt" if ev.attempts == 1 else "attempts"
            lines.append(f"- {ev.node}: {ev.result} ({ev.attempts} {plural})")
            reason = ev.extra.get("reason")
            if reason:
                lines.append(f"  - reason: {reason}")
            finding_details = ev.extra.get("finding_details")
            if isinstance(finding_details, list):
                for finding in finding_details:
                    lines.append(f"  - finding: {finding}")
        if final_outcome:
            lines.append(f"- Final outcome: {final_outcome}")

    if existing_kb_titles:
        lines.append("")
        lines.append("## Existing knowledge base entries")
        for kb_id, title in existing_kb_titles:
            lines.append(f"- {kb_id}: {title}")

    return "\n".join(lines)
