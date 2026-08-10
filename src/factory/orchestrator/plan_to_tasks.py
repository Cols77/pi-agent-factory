from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import frontmatter

_TASK_HEADER = re.compile(r"^### Task (\d+): (.+)$", re.MULTILINE)
_FILES_BLOCK = re.compile(r"\*\*Files:\*\*\n(.*?)(?=\n\n\*\*Interfaces:\*\*)", re.DOTALL)
_PRODUCES_LINE = re.compile(r"^- Produces:\s*(.+)$", re.MULTILINE)
_ID_RE = re.compile(r"^T-(\d+)$")


def _mask_fenced_blocks(text: str) -> str:
    """Blank out fenced code block contents, preserving every character
    offset and every newline so that slices taken against the ORIGINAL text
    stay aligned. A plan legitimately embeds plan-shaped markdown in a fence
    (a test fixture, an example); those `### Task N:` lines are content, not
    sections, and matching them produces phantom tasks (T-020).
    """
    out: list[str] = []
    fence: str | None = None
    for line in text.split("\n"):
        stripped = line.lstrip()
        marker = "```" if stripped.startswith("```") else "~~~" if stripped.startswith("~~~") else None
        if fence is None:
            if marker is None:
                out.append(line)
            else:
                fence = marker
                out.append(" " * len(line))
            continue
        out.append(" " * len(line))
        # Only a matching marker closes the fence, so ``` inside a ~~~ block
        # (and vice versa) does not end it early.
        if marker == fence:
            fence = None
    return "\n".join(out)


_FIXED_DOD_ITEM = "All steps in this task complete; tests/gates pass; committed"


@dataclass
class ParsedPlanTask:
    number: int
    title: str
    files_block: str
    produces: list[str]
    body: str = ""


class NoTasksFoundError(RuntimeError):
    def __init__(self, plan_path: str) -> None:
        super().__init__(f"no '### Task N:' sections found in {plan_path}")
        self.plan_path = plan_path


def parse_plan_tasks(text: str) -> list[ParsedPlanTask]:
    """Parse every `### Task N: Title` section out of a writing-plans-format
    plan document. Pure: no file I/O, no side effects. Returns an empty list
    if no task sections are found -- callers decide whether that's an error.
    """
    headers = list(_TASK_HEADER.finditer(_mask_fenced_blocks(text)))
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
                body=chunk.strip(),
            )
        )
    return tasks


def _slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug or "task"


def _max_existing_id(tasks_dir: Path) -> int:
    max_n = 0
    if not tasks_dir.exists():
        return max_n
    for path in tasks_dir.glob("T-*.md"):
        post = frontmatter.load(str(path))
        m = _ID_RE.match(str(post.get("id", "")))
        if m:
            max_n = max(max_n, int(m.group(1)))
    return max_n


def _already_parsed_task_numbers(tasks_dir: Path, source_plan: str) -> set[int]:
    done: set[int] = set()
    if not tasks_dir.exists():
        return done
    for path in tasks_dir.glob("T-*.md"):
        post = frontmatter.load(str(path))
        if post.get("source_plan") == source_plan and "source_task" in post.metadata:
            done.add(int(post["source_task"]))  # type: ignore[arg-type]
    return done


def _write_task_file(tasks_dir: Path, task_id: str, task: ParsedPlanTask, source_plan: str) -> Path:
    dod = list(task.produces)
    dod.append(_FIXED_DOD_ITEM)
    body = f"{task.files_block}\n\nFull steps: {source_plan}, Task {task.number}.\n"
    post = frontmatter.Post(
        body,
        id=task_id,
        title=task.title,
        status="todo",
        dod=dod,
        source_plan=source_plan,
        source_task=task.number,
    )
    path = tasks_dir / f"{task_id}-{_slugify(task.title)}.md"
    path.write_text(frontmatter.dumps(post), encoding="utf-8")
    return path


def run(plan_path: Path, repo_root: Path) -> list[str]:
    """Parse plan_path and write one tasks/T-*.md per task section found.
    Returns the list of newly-created task ids (empty if this plan was
    already fully parsed -- idempotent on rerun). Raises NoTasksFoundError,
    writing nothing, if the plan has zero '### Task N:' sections."""
    text = plan_path.read_text(encoding="utf-8")
    parsed = parse_plan_tasks(text)
    if not parsed:
        raise NoTasksFoundError(str(plan_path))

    tasks_dir = repo_root / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)

    source_plan = plan_path.resolve().relative_to(repo_root.resolve()).as_posix()
    already_done = _already_parsed_task_numbers(tasks_dir, source_plan)
    next_n = _max_existing_id(tasks_dir) + 1

    created: list[str] = []
    for task in parsed:
        if task.number in already_done:
            continue
        task_id = f"T-{next_n:03d}"
        next_n += 1
        _write_task_file(tasks_dir, task_id, task, source_plan)
        created.append(task_id)
    return created


def main() -> None:
    parser = argparse.ArgumentParser(prog="factory.orchestrator.plan_to_tasks")
    parser.add_argument("plan_file")
    parser.add_argument("--repo", default=".")
    args = parser.parse_args()

    repo_root = Path(args.repo).resolve()
    plan_path = Path(args.plan_file).resolve()

    try:
        created = run(plan_path, repo_root)
    except NoTasksFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if not created:
        print("no new tasks (already parsed)")
    else:
        print("created: " + ", ".join(created))


if __name__ == "__main__":
    main()
