from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from coherence.planning import PlanningInput, check_planning_input
from coherence.planning.run import (
    build_downstream_suggestion,
    read_review_decision,
    write_planning_run,
)

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


def _write_fixture(root: Path) -> PlanningInput:
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
    for number, title in ((2, "Second"), (1, "First")):
        (tasks_dir / f"T-{number:03d}-{title.lower()}.md").write_text(
            "---\n"
            f"id: T-{number:03d}\n"
            f"title: {title} Task\n"
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


def _approval(report: object) -> dict[str, object]:
    assert hasattr(report, "artifacts")
    artifacts = getattr(report, "artifacts")
    return {
        "schema": 1,
        "run_id": "run-001",
        "decision": "approve",
        "reviewer": "human",
        "reason": "Reviewed the generated planning artifacts.",
        "reviewed_artifacts": [artifact["path"] for artifact in artifacts],
    }


def test_writes_report_with_fixed_field_order(tmp_path: Path) -> None:
    report = check_planning_input(_write_fixture(tmp_path))

    path = write_planning_run(tmp_path, report)

    assert path == tmp_path / ".factory" / "planning" / "run-001" / "report.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert list(payload) == [
        "schema",
        "run_id",
        "ok",
        "artifacts",
        "findings",
        "next_actions",
        "review_required",
        "suggestion",
    ]
    assert payload["suggestion"] is None
    assert not list(path.parent.glob("*.tmp"))


def test_approval_is_explicit_and_builds_sorted_downstream_suggestion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_data = _write_fixture(tmp_path)
    report = check_planning_input(input_data)
    write_planning_run(tmp_path, report)
    decision_path = tmp_path / ".factory" / "planning" / "run-001" / "review-decision.json"
    decision_path.write_text(json.dumps(_approval(report)), encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    decision = read_review_decision(decision_path, report)

    assert decision is not None
    assert build_downstream_suggestion(report) is None
    assert build_downstream_suggestion(report, decision) == {
        "action": "suggest_downstream",
        "workflow": "standard",
        "plan": "docs/superpowers/plans/intent-plan.md",
        "tasks": ["T-001", "T-002"],
        "prerequisites": ["human_review", "requirement_consent"],
        "starts_automatically": False,
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"decision": "reject"},
        {"decision": "defer"},
        {"reviewer": "agent"},
        {"reason": "  "},
        {"schema": 2},
        {"run_id": "run-002"},
        {"reviewed_artifacts": ["not-an-artifact"]},
    ],
)
def test_invalid_or_non_approval_decisions_never_suggest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, changes: dict[str, object]
) -> None:
    report = check_planning_input(_write_fixture(tmp_path))
    write_planning_run(tmp_path, report)
    decision_payload = _approval(report)
    decision_payload.update(changes)
    decision_path = tmp_path / ".factory" / "planning" / "run-001" / "review-decision.json"
    decision_path.write_text(json.dumps(decision_payload), encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    decision = read_review_decision(decision_path, report)

    if changes.get("decision") in {"reject", "defer"}:
        assert decision is not None
    else:
        assert decision is None
    assert build_downstream_suggestion(report, decision) is None


def test_malformed_decision_never_suggests(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    report = check_planning_input(_write_fixture(tmp_path))
    write_planning_run(tmp_path, report)
    decision_path = tmp_path / ".factory" / "planning" / "run-001" / "review-decision.json"
    decision_path.write_text("{not-json", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    decision = read_review_decision(decision_path, report)

    assert decision is None
    assert build_downstream_suggestion(report, decision) is None


def test_changed_artifact_hash_blocks_approved_suggestion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_data = _write_fixture(tmp_path)
    report = check_planning_input(input_data)
    write_planning_run(tmp_path, report)
    decision_path = tmp_path / ".factory" / "planning" / "run-001" / "review-decision.json"
    decision_path.write_text(json.dumps(_approval(report)), encoding="utf-8")
    input_data.spec_path.write_text(SPEC + "\nChanged after review.\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    decision = read_review_decision(decision_path, report)

    assert decision is not None
    assert build_downstream_suggestion(report, decision) is None


@pytest.mark.parametrize("run_id", ["../escape", "bad\x00id"])
def test_run_id_cannot_escape_planning_directory(tmp_path: Path, run_id: str) -> None:
    report = check_planning_input(_write_fixture(tmp_path))

    with pytest.raises(ValueError):
        write_planning_run(tmp_path, replace(report, run_id=run_id))


def test_symlinked_artifact_outside_root_blocks_approved_suggestion(tmp_path: Path) -> None:
    input_data = _write_fixture(tmp_path)
    report = check_planning_input(input_data)
    outside = tmp_path.parent / "planning-outside-spec.md"
    outside.write_text(SPEC, encoding="utf-8")
    linked = tmp_path / "docs" / "specs" / "linked-spec.md"
    try:
        linked.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation is unavailable on this Windows runner")

    artifacts = tuple(
        {
            "path": "docs/specs/linked-spec.md" if artifact["path"] == "docs/specs/intent-spec.md" else artifact["path"],
            "sha256": hashlib.sha256(outside.read_bytes()).hexdigest()
            if artifact["path"] == "docs/specs/intent-spec.md"
            else artifact["sha256"],
        }
        for artifact in report.artifacts
    )
    report = replace(report, artifacts=artifacts)
    write_planning_run(tmp_path, report)
    decision = _approval(report)

    assert build_downstream_suggestion(report, decision, root=tmp_path) is None




__all__ = []
