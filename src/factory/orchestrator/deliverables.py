from __future__ import annotations

import re

# Matches lines like "- Create: `path`", "- Modify: `path`", "- Test: `path`"
# (case-insensitive verb, optional leading list marker/whitespace).
_LINE = re.compile(r"^\s*[-*]?\s*(?:create|modify|test)\s*:\s*`([^`]+)`", re.IGNORECASE)


def parse_deliverables(task_body: str) -> list[str]:
    """Extract deliverable file paths from a task body's Create/Modify/Test
    lines, in order of appearance, de-duplicated."""
    out: list[str] = []
    seen: set[str] = set()
    for line in task_body.splitlines():
        m = _LINE.match(line)
        if m:
            path = m.group(1).strip()
            if path and path not in seen:
                seen.add(path)
                out.append(path)
    return out
