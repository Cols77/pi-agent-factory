"""Fixture-scoped reference for the pre-migration requirements doctor.

This module intentionally does not import ``factory.doctor`` or
``coherence.doctor``.  It keeps the old command contract independently
executable so parity tests cannot pass merely because the legacy module aliases
the canonical implementation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import frontmatter

_ID_RE = re.compile(r"SR-(\d+)")
_TASK_ID_RE = re.compile(r"T-(\d+)")


def _next_id(requirements_dir: Path) -> str:
    numbers = [
        int(match.group(1))
        for path in requirements_dir.glob("SR-*.md")
        if (match := _ID_RE.search(path.name))
    ]
    return f"SR-{(max(numbers) + 1) if numbers else 1:03d}"


def _mint(
    project_root: Path, source: str, title: str, statement: str, domain: str
) -> Path:
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


def _checksum(post: frontmatter.Post) -> str:
    binding = post["binding"]
    canonical = "\n".join(
        [
            str(post["statement"]).strip(),
            str(binding.get("harness", "")),
            str(binding["experiment"]),
            str(binding["metric"]),
            str(binding["assert"]),
            str(binding.get("trials", 1)),
            repr(binding.get("window")),
        ]
    )
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def _promote(
    project_root: Path,
    req_id: str,
    harness: str,
    experiment: str,
    metric: str,
    assert_expr: str,
    trials: int,
    window: dict | None,
) -> tuple[Path, bool]:
    path = project_root / "requirements" / f"{req_id}.md"
    if not path.is_file():
        raise ValueError(f"no such requirement: {req_id}")
    post = frontmatter.load(str(path))
    binding = dict(post.get("binding") or {})
    binding.update(
        {"experiment": experiment, "metric": metric, "assert": assert_expr, "trials": trials}
    )
    binding["harness"] = harness
    if window is not None:
        binding["window"] = window
    post["binding"] = binding
    path.write_text(frontmatter.dumps(post), encoding="utf-8")

    post = frontmatter.load(str(path))
    post["checksum"] = _checksum(post)
    path.write_text(frontmatter.dumps(post), encoding="utf-8")
    return path, False


def _next_task_id(tasks_dir: Path) -> str:
    numbers = [
        int(match.group(1))
        for path in tasks_dir.glob("T-*.md")
        if (match := _TASK_ID_RE.search(path.name))
    ]
    return f"T-{(max(numbers) + 1) if numbers else 1:03d}"


def _task(project_root: Path, satisfies: str, title: str, dod: list[str], body: str) -> Path:
    if not (project_root / "requirements" / f"{satisfies}.md").is_file():
        raise ValueError(f"no such requirement: {satisfies}")
    if not dod:
        raise ValueError("a task needs at least one dod entry")
    tasks_dir = project_root / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    task_id = _next_task_id(tasks_dir)
    post = frontmatter.Post(body, id=task_id, title=title, status="todo", dod=list(dod), satisfies=[satisfies])
    path = tasks_dir / f"{task_id}.md"
    path.write_text(frontmatter.dumps(post), encoding="utf-8")
    return path


def _context(project_root: Path) -> dict:
    specs_dir = project_root / "docs" / "superpowers" / "specs"
    specs = (
        [path.relative_to(project_root).as_posix() for path in sorted(specs_dir.glob("*.md"))]
        if specs_dir.is_dir()
        else []
    )
    requirements = []
    requirements_dir = project_root / "requirements"
    for path in sorted(requirements_dir.glob("SR-*.md")) if requirements_dir.is_dir() else []:
        post = frontmatter.load(str(path))
        binding = post.get("binding")
        requirements.append(
            {
                "id": post["id"],
                "title": post["title"],
                "statement": post["statement"],
                "domain": post["domain"],
                "source": post.get("source"),
                "state": "proposed" if binding is None else "active",
                "binding": None
                if binding is None
                else {
                    "harness": binding.get("harness"),
                    "experiment": binding["experiment"],
                    "metric": binding["metric"],
                    "assert": binding["assert"],
                },
            }
        )
    return {
        "specs": specs,
        "requirements": requirements,
        "config": {"present": False, "harnesses": {}},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="factory-doctor-reference")
    sub = parser.add_subparsers(dest="cmd", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--project-root", default=Path("."), type=Path)

    context = sub.add_parser("context", parents=[common])
    context.add_argument("--json", action="store_true", dest="as_json")

    mint = sub.add_parser("mint", parents=[common])
    mint.add_argument("--source", required=True)
    mint.add_argument("--title", required=True)
    mint.add_argument("--statement", required=True)
    mint.add_argument("--domain", default="behavioral")

    promote = sub.add_parser("promote", parents=[common])
    promote.add_argument("id")
    promote.add_argument("--harness", required=True)
    promote.add_argument("--experiment", required=True)
    promote.add_argument("--metric", required=True)
    promote.add_argument("--assert", dest="assert_expr", required=True)
    promote.add_argument("--trials", type=int, default=1)
    promote.add_argument("--window-json", dest="window_json", default=None)

    task = sub.add_parser("task", parents=[common])
    task.add_argument("--satisfies", required=True)
    task.add_argument("--title", required=True)
    task.add_argument("--dod", action="append", required=True)
    task.add_argument("--body", default="")

    args = parser.parse_args(argv)
    try:
        if args.cmd == "context":
            print(json.dumps(_context(args.project_root), indent=2) if args.as_json else "")
        elif args.cmd == "mint":
            path = _mint(args.project_root, args.source, args.title, args.statement, args.domain)
            print(f"minted {path.stem} at {path}")
        elif args.cmd == "promote":
            window = json.loads(args.window_json) if args.window_json else None
            path, implemented = _promote(
                args.project_root,
                args.id,
                args.harness,
                args.experiment,
                args.metric,
                args.assert_expr,
                args.trials,
                window,
            )
            print(f"promoted {args.id} at {path}")
            state = "implemented" if implemented else "NOT implemented in the declared scorers module"
            print(f"metric {args.metric!r}: {state}")
        elif args.cmd == "task":
            path = _task(args.project_root, args.satisfies, args.title, args.dod, args.body)
            print(f"wrote {path.stem} at {path}")
    except ValueError as exc:
        print(str(exc))
        return 1
    return 0


__all__ = ["main"]
