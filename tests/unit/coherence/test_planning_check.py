from __future__ import annotations

import json
from pathlib import Path

import pytest

from coherence.planning import PlanningInput, check_planning_input

pytestmark = pytest.mark.unit


INTENT = {
    "schema": 1,
    "prompt": "Build a deterministic planner",
    "answers": [
        {"id": "goal", "text": "Build a deterministic planner"},
        {"id": "constraint-files", "text": "Files remain canonical"},
    ],
}

SPEC = """---
id: intent-spec
title: Intent Specification
status: draft
---
# Intent Specification

The goal is to build a deterministic planner.
The constraint-files rule says files remain canonical.
"""

PLAN = """---
spec_ref: intent-spec.md
---
# Deterministic Planner Plan

### Task 1: First Task

**Files:**
- Create: `src/first.py`

**Interfaces:**
- Produces: `goal` support.

### Task 2: Second Task

**Files:**
- Create: `src/second.py`

**Interfaces:**
- Produces: `constraint-files` support.
"""


def _write_fixture(root: Path, *, task_numbers: tuple[int, ...] = (1, 2)) -> PlanningInput:
    intent_path = root / ".intent" / "intent.json"
    spec_path = root / "docs" / "superpowers" / "specs" / "intent-spec.md"
    plan_path = root / "docs" / "superpowers" / "plans" / "intent-plan.md"
    for path in (intent_path, spec_path, plan_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    intent_path.write_text(json.dumps(INTENT), encoding="utf-8")
    spec_path.write_text(SPEC, encoding="utf-8")
    plan_path.write_text(PLAN, encoding="utf-8")

    tasks_dir = root / "tasks"
    tasks_dir.mkdir()
    titles = {1: "first", 2: "second"}
    for number in task_numbers:
        (tasks_dir / f"T-{number:03d}-{titles[number]}.md").write_text(
            "---\n"
            f"id: T-{number:03d}\n"
            f"title: {titles[number].title()} Task\n"
            "status: todo\n"
            "source_plan: docs/superpowers/plans/intent-plan.md\n"
            f"source_task: {number}\n"
            "---\n",
            encoding="utf-8",
        )
    return PlanningInput(
        intent_path=intent_path,
        spec_path=spec_path,
        plan_path=plan_path,
        project_root=root,
        run_id="run-001",
    )


def test_missing_generated_task_fails_plan_task_parity(tmp_path: Path) -> None:
    report = check_planning_input(_write_fixture(tmp_path, task_numbers=(1,)))

    assert report.ok is False
    assert any(
        finding.code == "PLAN_TASK_PARITY" and finding.severity == "error"
        for finding in report.findings
    )


def test_complete_fixture_is_valid_but_requires_review(tmp_path: Path) -> None:
    report = check_planning_input(_write_fixture(tmp_path))

    assert report.ok is True
    assert report.review_required is True
    assert report.suggestion is None
    assert report.findings == ()


def test_invalid_intent_is_fail_closed(tmp_path: Path) -> None:
    input_data = _write_fixture(tmp_path)
    payload = json.loads(input_data.intent_path.read_text(encoding="utf-8"))
    payload["schema"] = 2
    input_data.intent_path.write_text(json.dumps(payload), encoding="utf-8")

    report = check_planning_input(input_data)

    assert report.ok is False
    assert any(finding.code == "INTENT_INVALID" for finding in report.findings)


def test_uncovered_intent_and_unsupported_claim_are_reported(tmp_path: Path) -> None:
    input_data = _write_fixture(tmp_path)
    input_data.spec_path.write_text(
        "---\nid: intent-spec\ntitle: Intent Specification\nstatus: draft\n---\n"
        "goal only. claim:unanswered\n",
        encoding="utf-8",
    )

    report = check_planning_input(input_data)

    assert report.ok is False
    assert any(finding.code == "INTENT_UNCOVERED" for finding in report.findings)
    assert any(finding.code == "SPEC_UNSUPPORTED_CLAIM" for finding in report.findings)


def test_report_has_sorted_artifact_hashes_and_stable_fields(tmp_path: Path) -> None:
    report = check_planning_input(_write_fixture(tmp_path))

    assert [artifact["path"] for artifact in report.artifacts] == sorted(
        artifact["path"] for artifact in report.artifacts
    )
    assert {artifact["path"] for artifact in report.artifacts} == {
        ".intent/intent.json",
        "docs/superpowers/plans/intent-plan.md",
        "docs/superpowers/specs/intent-spec.md",
    }
    assert all(isinstance(artifact["sha256"], str) for artifact in report.artifacts)
    assert report.schema == 1
    assert report.run_id == "run-001"
    assert isinstance(report.next_actions, tuple)


def test_checker_catches_missing_input_without_writing_files(tmp_path: Path) -> None:
    input_data = _write_fixture(tmp_path)
    input_data.plan_path.unlink()
    before = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))

    report = check_planning_input(input_data)

    after = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))
    assert report.ok is False
    assert any(finding.code == "INPUT_READ_ERROR" for finding in report.findings)
    assert after == before


__all__ = []
