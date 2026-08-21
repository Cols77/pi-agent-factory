from __future__ import annotations

import re
from pathlib import Path

import frontmatter

from coherence.doctor.context import gather_context
from coherence.register.cli import _next_id
from coherence.register.write import write_binding

_TASK_ID_RE = re.compile(r"T-(\d+)")


def mint(
    project_root: Path, source: str, title: str, statement: str, domain: str = "behavioral"
) -> Path:
    """Write an accepted candidate as a proposed requirement."""
    if not (project_root / source).is_file():
        raise ValueError(f"no such source: {source}")
    requirements_dir = project_root / "requirements"
    requirements_dir.mkdir(parents=True, exist_ok=True)
    req_id = _next_id(requirements_dir)
    post = frontmatter.Post(
        "\n## Rationale\n",
        id=req_id,
        title=title,
        statement=statement,
        domain=domain,
        upstream=[],
        source=source,
    )
    path = requirements_dir / f"{req_id}.md"
    path.write_text(frontmatter.dumps(post), encoding="utf-8")
    return path


def promote(
    project_root: Path,
    req_id: str,
    harness: str,
    experiment: str,
    metric: str,
    assert_expr: str,
    trials: int = 1,
    window: dict | None = None,
) -> tuple[Path, bool]:
    """Fill a proposed requirement's binding and report metric availability."""
    path = project_root / "requirements" / f"{req_id}.md"
    if not path.is_file():
        raise ValueError(f"no such requirement: {req_id}")
    write_binding(
        path,
        experiment=experiment,
        metric=metric,
        assert_expr=assert_expr,
        harness=harness,
        trials=trials,
        window=window,
    )
    declared = gather_context(project_root)["config"]["harnesses"].get(harness, {})
    return path, metric in declared.get("metrics", [])


def _next_task_id(tasks_dir: Path) -> str:
    nums = [int(m.group(1)) for p in tasks_dir.glob("T-*.md") if (m := _TASK_ID_RE.search(p.name))]
    return f"T-{(max(nums) + 1) if nums else 1:03d}"


def emit_task(
    project_root: Path, satisfies: str, title: str, dod: list[str], body: str = ""
) -> Path:
    """Write an agent-authored task linked to the requirement it serves."""
    if not (project_root / "requirements" / f"{satisfies}.md").is_file():
        raise ValueError(f"no such requirement: {satisfies}")
    if not dod:
        raise ValueError("a task needs at least one dod entry")
    tasks_dir = project_root / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    task_id = _next_task_id(tasks_dir)
    post = frontmatter.Post(
        body, id=task_id, title=title, status="todo", dod=list(dod), satisfies=[satisfies]
    )
    path = tasks_dir / f"{task_id}.md"
    path.write_text(frontmatter.dumps(post), encoding="utf-8")
    return path


__all__ = ["emit_task", "mint", "promote"]

