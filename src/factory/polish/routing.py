from __future__ import annotations

import json
import re
from pathlib import Path

import frontmatter

from factory.polish.finding import Finding

_ID_RE = re.compile(r"T-(\d+)")


def _next_task_id(tasks_dir: Path) -> str:
    nums = [
        int(m.group(1))
        for p in tasks_dir.glob("T-*.md")
        if (m := _ID_RE.search(p.name))
    ]
    return f"T-{(max(nums) + 1) if nums else 1:03d}"


def route(finding: Finding, tasks_dir: Path) -> Path:
    tasks_dir.mkdir(parents=True, exist_ok=True)
    task_id = _next_task_id(tasks_dir)
    title = f"polish[{finding.usecase}]: {finding.description[:60]}"
    dod = [f"the {finding.usecase} use case no longer exhibits: {finding.description}"]

    lines = [
        f"From a `factory polish` session on use case **{finding.usecase}**.",
        "",
        finding.description,
    ]
    if finding.snapshot:
        lines += ["", "## Reproduction snapshot", "```json", json.dumps(finding.snapshot, indent=2), "```"]
    if finding.artifacts:
        lines += ["", "## Artifacts", *[f"- {a}" for a in finding.artifacts]]

    post = frontmatter.Post("\n".join(lines), id=task_id, title=title, status="todo", dod=dod)
    if finding.sr:
        post["satisfies"] = [finding.sr]

    path = tasks_dir / f"{task_id}.md"
    path.write_text(frontmatter.dumps(post), encoding="utf-8")
    return path
