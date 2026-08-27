from __future__ import annotations

import json
from pathlib import Path

import frontmatter
import pytest

pytestmark = pytest.mark.unit

_EXPECTED_SRS = {"SR-043", "SR-044", "SR-050", "SR-051", "SR-052", "SR-053", "SR-054"}
_PLAN = "docs/superpowers/plans/2026-08-27-feat17-planning-workflow-plan.md"


def test_feat17_trace_contract_names_all_requirements_and_implementation_task() -> None:
    root = Path(__file__).parents[3]
    dossier = frontmatter.load(str(root / "docs" / "features" / "FEAT-017.md"))
    bundle = json.loads((root / "bundles" / "FEAT-017.json").read_text(encoding="utf-8"))
    task_path = root / "tasks" / "T-032-feat17-planning-workflow.md"
    task = frontmatter.load(str(task_path))

    assert set(dossier["requirements"]) == _EXPECTED_SRS
    assert {member.removeprefix("sr:") for member in bundle["members"] if member.startswith("sr:")} == _EXPECTED_SRS
    assert task["source_plan"] == _PLAN
    assert {
        target
        for entry in task["justification"]
        for kind, target in entry.items()
        if kind == "satisfies"
    } == _EXPECTED_SRS
    assert "src/coherence/planning/" in task.content
    assert "pi-ext/factory-watch/src/skill-prompt.ts" in task.content
