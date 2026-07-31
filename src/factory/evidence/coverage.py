from __future__ import annotations

from pathlib import Path

from factory.orchestrator.deliverables import modified_deliverables


def _gathered_refs(context: dict) -> set[str]:
    """All paths the manifest gathered, anchor-stripped: source_files + spec + plan."""
    refs: set[str] = set()
    for key in ("source_files", "spec", "plan"):
        for ref in context.get(key, []) or []:
            refs.add(str(ref).split("#", 1)[0])
    return refs


def coverage_errors(task_body: str, context: dict, repo_root: Path) -> list[str]:
    """Factory-derived coverage floor (agent-independent): every `Modify:`
    deliverable the task declares must be gathered into context AND resolve on
    disk. Create:/Test: are excluded (the task brings those into existence)."""
    gathered = _gathered_refs(context)
    errors: list[str] = []
    for path in modified_deliverables(task_body):
        if path not in gathered:
            errors.append(f"deliverable not gathered into context: {path} (declared Modify:)")
        elif not (repo_root / path).exists():
            errors.append(f"gathered deliverable missing on disk: {path}")
    return errors
