"""Shared repo-scaffold builders for factory.system query/CLI tests.

Not a test module itself (no `pytestmark`) -- pytest does not collect it
because it defines no `test_*` functions.
"""
from __future__ import annotations

import json
from pathlib import Path

from factory.evidence.manifests import write_run_manifest as _write_evidence_manifest

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


def review_record(
    *,
    task_id: str = "T-001",
    decision: str = "approve",
    reviewed_at: str | None = "2026-08-08T12:00:00Z",
    start_commit: str = "a" * 40,
) -> dict:
    """One entry as `factory.evidence.finalize._review_evidence` leaves it in
    `manifest["reviews"]` -- version/reviewed_at/task_id/start_commit/
    decision/annotations/reviewed_files/patch (a published blob ref; the
    standalone transcript file's `diff` field is popped in favor of this by
    `finalize.py`, never `manifest["reviews"]` shape). This is the shape
    `query_timeline` (design SS4.3) actually reads.
    """
    return {
        "version": 1,
        "reviewed_at": reviewed_at,
        "task_id": task_id,
        "start_commit": start_commit,
        "decision": decision,
        "annotations": [],
        "reviewed_files": [],
        "patch": {
            "sha256": "f" * 64,
            "size": 10,
            "media_type": "text/x-diff",
            "local": True,
            "publication": "local",
            "uri": None,
        },
    }


def write_run_manifest(
    repo_root: Path,
    *,
    run_id: str = "run-001",
    task_id: str = "T-001",
    reviews: list[dict] | None = None,
    outcome: str = "completed",
    started_at: str = "2026-08-08T08:00:00Z",
    ended_at: str = "2026-08-08T09:00:00Z",
) -> Path:
    """Write a schema-valid run evidence manifest via the real
    `factory.evidence.manifests.write_run_manifest` writer -- guarantees the
    fixture matches the shape `factory.evidence.finalize` actually produces
    (design SS4.3's durable evidence, `evidence/runs/<run_id>.json`, a flat
    file -- never a `evidence/runs/<run_id>/reviews/*.json` directory; no
    producer in this repo ever writes that layout). `reviews` defaults to an
    empty list -- a real, valid manifest for a task that has not yet had a
    review round, a legitimate state rather than a corruption or absence.
    """
    manifest = {
        "schema_version": 2,
        "run_id": run_id,
        "task_id": task_id,
        "started_at": started_at,
        "ended_at": ended_at,
        "start_commit": "a" * 40,
        "result_commit": "b" * 40,
        "outcome": outcome,
        "inputs": {
            "task": {"path": f"tasks/{task_id}-slug.md", "sha256": "c" * 64},
            "requirements": [],
            "factory_config_sha256": "d" * 64,
        },
        "dependencies": [],
        "implementation": {
            "changed_files": [],
            "patch": {"sha256": "e" * 64, "size": 0, "media_type": "text/x-diff"},
        },
        "validation": [],
        "reviews": reviews if reviews is not None else [],
        "decisions": [],
        "publication": {"state": "local", "errors": []},
    }
    return _write_evidence_manifest(repo_root / "evidence", manifest)


def write_decision_artifact(
    repo_root: Path,
    *,
    task_id: str = "T-001",
    run_id: str = "run-001",
    reviewed_at: str | None = "2026-08-08T12:00:00Z",
    decision: str = "approve",
) -> Path:
    """Convenience: one run manifest holding exactly one review record for
    `task_id`. Thin wrapper over `write_run_manifest` + `review_record` for
    the common single-decision case most tests need; returns the manifest
    path (the citation source `query_timeline` actually cites).
    """
    return write_run_manifest(
        repo_root,
        run_id=run_id,
        task_id=task_id,
        reviews=[review_record(task_id=task_id, decision=decision, reviewed_at=reviewed_at)],
    )


def write_raw_manifest_json(repo_root: Path, *, run_id: str = "run-001", payload: dict | str) -> Path:
    """Write `evidence/runs/<run_id>.json` directly, bypassing
    `write_run_manifest`'s schema validation -- for corrupt-JSON and
    schema-invalid-content edge cases the real writer would refuse to write.
    """
    path = repo_root / "evidence" / "runs" / f"{run_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    text = payload if isinstance(payload, str) else json.dumps(payload)
    path.write_text(text, encoding="utf-8")
    return path
