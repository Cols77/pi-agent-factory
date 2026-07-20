from __future__ import annotations

import re
from dataclasses import dataclass

_TASK_HEADER = re.compile(r"^### Task (\d+): (.+)$", re.MULTILINE)
_FILES_BLOCK = re.compile(r"\*\*Files:\*\*\n(.*?)(?=\n\n\*\*Interfaces:\*\*)", re.DOTALL)
_PRODUCES_LINE = re.compile(r"^- Produces:\s*(.+)$", re.MULTILINE)


@dataclass
class ParsedPlanTask:
    number: int
    title: str
    files_block: str
    produces: list[str]


def parse_plan_tasks(text: str) -> list[ParsedPlanTask]:
    """Parse every `### Task N: Title` section out of a writing-plans-format
    plan document. Pure: no file I/O, no side effects. Returns an empty list
    if no task sections are found -- callers decide whether that's an error.
    """
    headers = list(_TASK_HEADER.finditer(text))
    tasks: list[ParsedPlanTask] = []
    for i, m in enumerate(headers):
        start = m.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        chunk = text[start:end]

        files_match = _FILES_BLOCK.search(chunk)
        files_block = files_match.group(1).strip() if files_match else ""
        produces = [p.strip() for p in _PRODUCES_LINE.findall(chunk)]

        tasks.append(
            ParsedPlanTask(
                number=int(m.group(1)),
                title=m.group(2).strip(),
                files_block=files_block,
                produces=produces,
            )
        )
    return tasks
