from __future__ import annotations

import re

_HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*#?\s*$", re.MULTILINE)


def _without_fenced_code(text: str) -> str:
    """Blank fenced code blocks so examples cannot become authority headings."""
    lines = text.splitlines()
    output: list[str] = []
    fence: str | None = None
    for line in lines:
        stripped = line.lstrip()
        if fence is None:
            if stripped.startswith("```") or stripped.startswith("~~~"):
                fence = stripped[0]
                output.append("")
            else:
                output.append(line)
            continue
        if stripped.startswith(fence * 3):
            fence = None
        output.append("")
    return "\n".join(output)


def _anchor_matches(heading: str, anchor: str) -> bool:
    if heading == anchor:
        return True
    if not heading.startswith(anchor):
        return False
    return heading[len(anchor)] in " \t.:;,)]}-"


def authority_anchor_matches(spec_body: str, anchor: str) -> bool:
    """Return whether a real Markdown heading resolves the supplied anchor."""
    if not anchor.strip():
        return False
    headings = _HEADING_RE.findall(_without_fenced_code(spec_body))
    return any(_anchor_matches(heading, anchor.strip()) for heading in headings)


__all__ = ["authority_anchor_matches"]
