from __future__ import annotations

from pathlib import Path

from factory.polish.config import load_config
from factory.requirements.register import Requirement, load_register
from factory.validation.harness import Harness
from factory.validation.report import run_requirement_validation


def select_requirement_ids(
    reqs: list[Requirement], satisfies: list[str], *, full_sweep: bool = False
) -> list[str]:
    # A proposed requirement has no binding, so there is nothing to run -- not even
    # when a task names it directly.
    runnable = {r.id for r in reqs if r.binding is not None}
    ids: list[str] = []
    for r in reqs:
        if r.binding is None:
            continue
        if full_sweep or r.binding.cadence == "every_iteration":
            ids.append(r.id)
    for sid in satisfies:  # a task's own SRs always run, even if periodic
        if sid in runnable and sid not in ids:
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
    # Only a requirement that RAN and failed its assertion (passed is False) makes
    # the suite not-ok. A requirement that could NOT run — an "error" entry, e.g. no
    # harness declared in .factory/factory.yaml yet — is a setup gap the caller
    # surfaces as a warning, not a hard failure.
    ok = not any(e.get("passed") is False for e in report["requirements"])
    return report, ok
