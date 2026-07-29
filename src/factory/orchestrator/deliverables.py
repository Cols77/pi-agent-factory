from __future__ import annotations

import re
from pathlib import Path

# Matches lines like "- Create: `path`", "- Modify: `path`", "- Test: `path`"
# (case-insensitive verb, optional leading list marker/whitespace).
_LINE = re.compile(r"^\s*[-*]?\s*(?:create|modify|test)\s*:\s*`([^`]+)`", re.IGNORECASE)
# Only the CREATE/TEST lines -- paths the task brings into existence, whose
# presence signals the work is already done. Modify: is excluded (its file
# exists regardless of whether the task ran).
_CREATED_LINE = re.compile(r"^\s*[-*]?\s*(?:create|test)\s*:\s*`([^`]+)`", re.IGNORECASE)
# Only the MODIFY lines -- pre-existing files the task will change. These are
# the paths that MUST already exist and be gathered into context (unlike
# Create:/Test:, which the task brings into existence).
_MODIFIED_LINE = re.compile(r"^\s*[-*]?\s*modify\s*:\s*`([^`]+)`", re.IGNORECASE)


def _parse(task_body: str, pattern: re.Pattern[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for line in task_body.splitlines():
        m = pattern.match(line)
        if m:
            path = m.group(1).strip()
            if path and path not in seen:
                seen.add(path)
                out.append(path)
    return out


def parse_deliverables(task_body: str) -> list[str]:
    """Extract deliverable file paths from a task body's Create/Modify/Test
    lines, in order of appearance, de-duplicated."""
    return _parse(task_body, _LINE)


def created_deliverables(task_body: str) -> list[str]:
    """Paths the task declares it will CREATE (Create:/Test: lines only) -- the
    ones whose existence signals the work is already done. Modify: is excluded
    (its file exists regardless)."""
    return _parse(task_body, _CREATED_LINE)


def modified_deliverables(task_body: str) -> list[str]:
    """Paths the task declares it will MODIFY (Modify: lines only) -- pre-existing
    files that must be gathered into context. Create:/Test: are excluded (the task
    brings those into existence)."""
    return _parse(task_body, _MODIFIED_LINE)


def deliverables_exist(task_body: str, repo_root: Path) -> bool:
    """True if the task declares at least one Create:/Test: deliverable and ALL
    of them already exist under repo_root -- a cheap, deterministic 'this task's
    work is already done' signal, used to hide a task from factory-run's picker
    and from next_todo so already-built work isn't suggested for execution."""
    created = created_deliverables(task_body)
    return bool(created) and all((repo_root / p).exists() for p in created)
