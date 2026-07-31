from __future__ import annotations

from pathlib import Path

from factory.polish.config import load_config
from factory.requirements.register import Requirement, load_register
from factory.validation.harness import Harness
from factory.validation.report import run_requirement_validation


def select_requirement_ids(
    reqs: list[Requirement], satisfies: list[str], *, full_sweep: bool = False
) -> list[str]:
    ids: list[str] = []
    for r in reqs:
        if full_sweep or r.binding.cadence == "every_iteration":
            ids.append(r.id)
    for sid in satisfies:  # a task's own SRs always run, even if periodic
        if sid not in ids:
            ids.append(sid)
    return ids


def validate_task_requirements(
    repo_root: Path, satisfies: list[str], *, full_sweep: bool = False
) -> tuple[dict, bool]:
    reqs = load_register(repo_root / "requirements")
    harnesses = load_config(repo_root).harnesses

    def harness_for(name: str) -> Harness:
        h = harnesses.get(name)
        if h is None:
            raise ValueError(f"no harness {name!r} declared in .factory/factory.yaml")
        return h

    ids = select_requirement_ids(reqs, satisfies, full_sweep=full_sweep)
    report = run_requirement_validation(ids, reqs, harness_for, repo_root)
    ok = all(e.get("passed") is True for e in report["requirements"])
    return report, ok
