from __future__ import annotations

from pathlib import Path

from coherence.measurement.harness import Harness
from coherence.measurement.report import run_requirement_validation
from coherence.register.register import Requirement, load_register
from factory.config import load_config

__all__ = ["select_requirement_ids", "validate_task_requirements"]


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

    own_ids = set(satisfies)  # the task's own justified SRs -- see select_requirement_ids
    ids = select_requirement_ids(reqs, satisfies, full_sweep=full_sweep)
    report = run_requirement_validation(ids, reqs, harness_for, repo_root)
    # Invariant kernel rule 1: an execution error, missing executable or invalid
    # result on a task's OWN justified SR cannot become pass -- it blocks, exactly
    # like a ran-and-failed assertion. An "error" entry on an SR the task did not
    # name (only swept in by full_sweep's periodic cadence) is still a setup gap
    # unrelated to this task's claim, surfaced as a warning, not a hard failure.
    reds = any(e.get("passed") is False for e in report["requirements"])
    own_errors = any("error" in e and e.get("id") in own_ids for e in report["requirements"])
    ok = not (reds or own_errors)
    return report, ok
