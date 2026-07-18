from __future__ import annotations

from factory.orchestrator.ledger import Task
from factory.orchestrator.roles import ROLE_PROMPTS, ROLE_SKILLS
from factory.orchestrator.types import AgentRole


def compose_prompt(
    role: AgentRole,
    task: Task,
    manifest: dict | None = None,
    kb_entries: list[dict] | None = None,
    feedback: str | None = None,
) -> str:
    lines: list[str] = []
    lines.append(f"# Role: {role.value}")
    lines.append(ROLE_PROMPTS[role])
    lines.append("")
    lines.append("## Loaded skills")
    for skill in ROLE_SKILLS[role]:
        lines.append(f"- {skill}")
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
        for f in manifest.get("context", {}).get("source_files", []):
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

    return "\n".join(lines)
