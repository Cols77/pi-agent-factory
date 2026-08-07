"""Shared repo-scaffold builders for factory.system query/CLI tests.

Not a test module itself (no `pytestmark`) -- pytest does not collect it
because it defines no `test_*` functions.
"""
from __future__ import annotations

import json
from pathlib import Path

_SR_BOUND = """---
id: {id}
title: "{title}"
statement: "{statement}"
domain: behavioral
upstream: []
binding:
  harness: sim-testbench
  experiment: demo_experiment
  metric: demo_rate
  trials: 1
  assert: ">= 0.5"
checksum: null
---
Rationale.
"""

_SR_PROPOSED = """---
id: {id}
title: "{title}"
statement: "{statement}"
domain: behavioral
---
Rationale.
"""

_TASK = """---
id: {id}
title: "{title}"
status: {status}
dod:
  - done
{satisfies}---
body
"""

_SPEC = "# {title}\n\nSpec body.\n"

_PLAN = "# {title}\n\n- [ ] step one (unchecked, and unreliable per design SS3.4)\n- [ ] step two\n"


def write_bundle(bundles_dir: Path, bundle_id: str, label: str, members: list[str]) -> Path:
    bundles_dir.mkdir(parents=True, exist_ok=True)
    path = bundles_dir / f"{bundle_id}.json"
    path.write_text(json.dumps({"id": bundle_id, "label": label, "members": members}), encoding="utf-8")
    return path


def write_bundle_raw(bundles_dir: Path, filename_stem: str, payload: dict | str) -> Path:
    """Write a bundle file whose filename is independent of `payload["id"]`.

    Lets tests construct an id/filename mismatch (or plain-invalid JSON, if
    `payload` is a raw string) without `write_bundle`'s filename==id coupling.
    """
    bundles_dir.mkdir(parents=True, exist_ok=True)
    path = bundles_dir / f"{filename_stem}.json"
    text = payload if isinstance(payload, str) else json.dumps(payload)
    path.write_text(text, encoding="utf-8")
    return path


def write_sr(
    requirements_dir: Path,
    sr_id: str,
    *,
    title: str = "SR title",
    statement: str = "When X happens, the system shall Y.",
    proposed: bool = False,
) -> Path:
    requirements_dir.mkdir(parents=True, exist_ok=True)
    template = _SR_PROPOSED if proposed else _SR_BOUND
    path = requirements_dir / f"{sr_id}.md"
    path.write_text(template.format(id=sr_id, title=title, statement=statement), encoding="utf-8")
    return path


def write_task(
    tasks_dir: Path,
    task_id: str,
    *,
    title: str = "Task title",
    status: str = "todo",
    satisfies: list[str] | None = None,
) -> Path:
    tasks_dir.mkdir(parents=True, exist_ok=True)
    path = tasks_dir / f"{task_id}-slug.md"
    satisfies_block = f"satisfies: {json.dumps(satisfies)}\n" if satisfies else ""
    path.write_text(
        _TASK.format(id=task_id, title=title, status=status, satisfies=satisfies_block),
        encoding="utf-8",
    )
    return path


def write_spec(repo_root: Path, filename: str, *, title: str = "Spec title") -> Path:
    specs_dir = repo_root / "docs" / "superpowers" / "specs"
    specs_dir.mkdir(parents=True, exist_ok=True)
    path = specs_dir / filename
    path.write_text(_SPEC.format(title=title), encoding="utf-8")
    return path


def write_plan(repo_root: Path, filename: str, *, title: str = "Plan title") -> Path:
    plans_dir = repo_root / "docs" / "superpowers" / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    path = plans_dir / filename
    path.write_text(_PLAN.format(title=title), encoding="utf-8")
    return path


def write_validation_report(repo_root: Path, entries: list[dict]) -> Path:
    path = repo_root / "validation" / "validation-report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"requirements": entries}), encoding="utf-8")
    return path


def write_corrupt_validation_report(repo_root: Path) -> Path:
    """A validation report that exists on disk but `load_validation` cannot
    parse -- distinct from no report at all (see queries._validation_report_is_corrupt)."""
    path = repo_root / "validation" / "validation-report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not valid json at all", encoding="utf-8")
    return path


def write_decision_artifact(
    repo_root: Path,
    *,
    task_id: str = "T-001",
    run_id: str = "run-001",
    sequence: int = 1,
    reviewed_at: str | None = "2026-08-08T12:00:00Z",
    decision: str = "approve",
) -> Path:
    """A signed-review decision record (design SS4.3) -- the archive shape
    `factory.orchestrator.human_review.FileHumanReviewGate._archive` writes:
    `evidence/runs/<run_id>/reviews/review-<sequence:03>.json`. This is
    Task 3's timeline source; the filename's `<sequence>` counter is a
    genuinely recorded ordering signal independent of `reviewed_at` (see
    `FileHumanReviewGate._archive`'s own `sequence = 1; while ...:
    sequence += 1` loop) -- never a guess.
    """
    path = (
        repo_root
        / "evidence"
        / "runs"
        / run_id
        / "reviews"
        / f"review-{sequence:03d}.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "reviewed_at": reviewed_at,
                "task_id": task_id,
                "start_commit": "abc123",
                "decision": decision,
                "annotations": [],
                "reviewed_files": [],
            }
        ),
        encoding="utf-8",
    )
    return path


def write_decision_artifact_raw(
    repo_root: Path, *, run_id: str = "run-001", filename: str, payload: dict | str
) -> Path:
    """Write a decision-artifact file whose filename/content is fully caller
    controlled -- for corrupt-JSON and non-numbered-filename edge cases that
    `write_decision_artifact` cannot express.
    """
    path = repo_root / "evidence" / "runs" / run_id / "reviews" / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    text = payload if isinstance(payload, str) else json.dumps(payload)
    path.write_text(text, encoding="utf-8")
    return path
