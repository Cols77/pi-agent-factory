from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from coherence.planning import PlanningInput, check_planning_input

pytestmark = pytest.mark.unit

_INTENT = {
    "schema": 1,
    "prompt": "Build a deterministic planner",
    "answers": [
        {"id": "goal", "text": "Build a deterministic planner"},
        {"id": "constraint-files", "text": "Files remain canonical"},
    ],
}

_SPEC = """---
id: intent-spec
title: Intent Specification
status: draft
---
# Intent Specification

The goal is to build a deterministic planner.
The constraint-files rule says files remain canonical.
"""

_PLAN = """---
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


def _write_fixture(root: Path, *, complete_tasks: bool) -> PlanningInput:
    intent_path = root / ".intent" / "intent.json"
    spec_path = root / "docs" / "superpowers" / "specs" / "intent-spec.md"
    plan_path = root / "docs" / "superpowers" / "plans" / "intent-plan.md"
    for path in (intent_path, spec_path, plan_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    intent_path.write_text(json.dumps(_INTENT), encoding="utf-8")
    spec_path.write_text(_SPEC, encoding="utf-8")
    plan_path.write_text(_PLAN, encoding="utf-8")

    tasks_dir = root / "tasks"
    tasks_dir.mkdir()
    for number, slug in ((1, "first"), (2, "second")):
        if number == 2 and not complete_tasks:
            continue
        (tasks_dir / f"T-00{number}-{slug}.md").write_text(
            "---\n"
            f"id: T-00{number}\n"
            f"title: {slug.title()} Task\n"
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
    report = check_planning_input(_write_fixture(tmp_path, complete_tasks=False))

    assert report.ok is False
    assert any(
        finding.code == "PLAN_TASK_PARITY" and finding.severity == "error"
        for finding in report.findings
    )


def test_complete_fixture_is_valid_but_requires_review(tmp_path: Path) -> None:
    report = check_planning_input(_write_fixture(tmp_path, complete_tasks=True))

    assert report.ok is True
    assert report.review_required is True
    assert report.suggestion is None
    assert not any(finding.severity == "error" for finding in report.findings)


def test_duplicate_generated_task_ids_fail_closed(tmp_path: Path) -> None:
    input_data = _write_fixture(tmp_path, complete_tasks=True)
    (tmp_path / "tasks" / "T-003-duplicate.md").write_text(
        "---\n"
        "id: T-001\n"
        "title: Duplicate Task\n"
        "status: todo\n"
        "source_plan: docs/superpowers/plans/intent-plan.md\n"
        "source_task: 2\n"
        "---\n",
        encoding="utf-8",
    )

    report = check_planning_input(input_data)

    assert report.ok is False
    assert any(finding.code == "PLAN_TASK_PARITY" for finding in report.findings)


def test_foreign_generated_task_fails_closed_in_parity_gate(tmp_path: Path) -> None:
    input_data = _write_fixture(tmp_path, complete_tasks=True)
    (tmp_path / "tasks" / "T-999-foreign.md").write_text(
        "---\n"
        "id: T-999\n"
        "title: Foreign\n"
        "status: todo\n"
        "source_plan: docs/other-plan.md\n"
        "source_task: 1\n"
        "---\n",
        encoding="utf-8",
    )

    report = check_planning_input(input_data)

    assert report.ok is False
    assert any(
        finding.code == "PLAN_TASK_PARITY" and "source_plan" in finding.detail
        for finding in report.findings
    )


def test_noncanonical_generated_task_id_fails_closed(tmp_path: Path) -> None:
    input_data = _write_fixture(tmp_path, complete_tasks=True)
    (tmp_path / "tasks" / "T-003-noncanonical.md").write_text(
        "---\n"
        "id: T-foo\n"
        "title: Noncanonical\n"
        "status: todo\n"
        "source_plan: docs/superpowers/plans/intent-plan.md\n"
        "source_task: 1\n"
        "---\n",
        encoding="utf-8",
    )

    report = check_planning_input(input_data)

    assert report.ok is False
    assert any("T-<digits>" in finding.detail for finding in report.findings)



def test_empty_files_block_fails_plan_contract(tmp_path: Path) -> None:
    input_data = _write_fixture(tmp_path, complete_tasks=True)
    input_data.plan_path.write_text(
        _PLAN.replace("- Create: `src/first.py`\n", ""),
        encoding="utf-8",
    )

    report = check_planning_input(input_data)

    assert report.ok is False
    assert any(finding.code == "PLAN_INVALID" for finding in report.findings)


def test_duplicate_plan_task_numbers_fail_closed(tmp_path: Path) -> None:
    input_data = _write_fixture(tmp_path, complete_tasks=True)
    input_data.plan_path.write_text(
        _PLAN.replace("### Task 2: Second Task", "### Task 1: Duplicate Task"),
        encoding="utf-8",
    )

    report = check_planning_input(input_data)

    assert report.ok is False
    assert any(
        finding.code == "PLAN_INVALID" and "unique" in finding.detail
        for finding in report.findings
    )


def test_fenced_heading_does_not_satisfy_authority_anchor(tmp_path: Path) -> None:
    input_data = _write_fixture(tmp_path, complete_tasks=True)
    input_data.spec_path.write_text(
        _SPEC.replace(
            "# Intent Specification",
            "# Intent Specification\n\n```md\n### goal\n```",
        ),
        encoding="utf-8",
    )
    (tmp_path / "docs" / "features").mkdir(parents=True)
    (tmp_path / "bundles").mkdir()
    (tmp_path / "requirements").mkdir()
    (tmp_path / "docs" / "features" / "FEAT-017.md").write_text(
        "---\nid: FEAT-017\ntitle: Test feature\nrequirements:\n- SR-001\n---\n",
        encoding="utf-8",
    )
    (tmp_path / "bundles" / "FEAT-017.json").write_text(
        json.dumps({"id": "FEAT-017", "members": ["feat:FEAT-017", "sr:SR-001"]}),
        encoding="utf-8",
    )
    (tmp_path / "requirements" / "SR-001.md").write_text(
        "---\n"
        "id: SR-001\n"
        "title: Goal\n"
        "statement: Goal\n"
        "domain: behavioral\n"
        "upstream: []\n"
        "source: docs/superpowers/specs/intent-spec.md#goal\n"
        "---\n",
        encoding="utf-8",
    )

    report = check_planning_input(input_data)

    assert report.ok is False
    assert any(finding.code == "PLANNING_REFERENCE_INVALID" for finding in report.findings)


def test_boolean_intent_schema_is_not_an_integer_schema(tmp_path: Path) -> None:
    input_data = _write_fixture(tmp_path, complete_tasks=True)
    payload = json.loads(input_data.intent_path.read_text(encoding="utf-8"))
    payload["schema"] = True
    input_data.intent_path.write_text(json.dumps(payload), encoding="utf-8")

    report = check_planning_input(input_data)

    assert report.ok is False
    assert any(finding.code == "INTENT_INVALID" for finding in report.findings)


def test_duplicate_intent_json_keys_fail_closed(tmp_path: Path) -> None:
    input_data = _write_fixture(tmp_path, complete_tasks=True)
    input_data.intent_path.write_text(
        '{"schema": 1, "prompt": "first", "prompt": "second", '
        '"answers": [{"id": "goal", "text": "goal"}]}',
        encoding="utf-8",
    )

    report = check_planning_input(input_data)

    assert report.ok is False
    assert any(finding.code == "INTENT_INVALID" for finding in report.findings)


def test_overflowed_json_number_fails_closed(tmp_path: Path) -> None:
    input_data = _write_fixture(tmp_path, complete_tasks=True)
    input_data.intent_path.write_text(
        '{"schema": 1, "prompt": "first", "answers": [{"id": "goal", "text": 1e999}]}',
        encoding="utf-8",
    )

    report = check_planning_input(input_data)

    assert report.ok is False
    assert any(finding.code == "INTENT_INVALID" for finding in report.findings)


def test_duplicate_spec_frontmatter_keys_fail_closed(tmp_path: Path) -> None:
    input_data = _write_fixture(tmp_path, complete_tasks=True)
    input_data.spec_path.write_text(
        "---\n"
        "id: intent-spec\n"
        "id: other-spec\n"
        "title: Intent Specification\n"
        "status: draft\n"
        "---\n"
        "The goal and constraint-files are covered.\n",
        encoding="utf-8",
    )

    report = check_planning_input(input_data)

    assert report.ok is False
    assert any(finding.code == "FRONTMATTER_INVALID" for finding in report.findings)


def test_four_dash_frontmatter_duplicate_keys_fail_closed(tmp_path: Path) -> None:
    input_data = _write_fixture(tmp_path, complete_tasks=True)
    input_data.spec_path.write_text(
        "----\n"
        "id: intent-spec\n"
        "id: other-spec\n"
        "title: Intent Specification\n"
        "status: draft\n"
        "----\n"
        "The goal and constraint-files are covered.\n",
        encoding="utf-8",
    )

    report = check_planning_input(input_data)

    assert report.ok is False
    assert any(finding.code == "FRONTMATTER_INVALID" for finding in report.findings)


def test_json_frontmatter_duplicate_keys_fail_closed(tmp_path: Path) -> None:
    input_data = _write_fixture(tmp_path, complete_tasks=True)
    input_data.spec_path.write_text(
        "{\n"
        "\"id\": \"intent-spec\",\n"
        "\"id\": \"other-spec\",\n"
        "\"title\": \"Intent Specification\",\n"
        "\"status\": \"draft\"\n"
        "}\n"
        "The goal and constraint-files are covered.\n",
        encoding="utf-8",
    )

    report = check_planning_input(input_data)

    assert report.ok is False
    assert any(finding.code == "FRONTMATTER_INVALID" for finding in report.findings)


def test_yaml_frontmatter_nonfinite_values_fail_closed(tmp_path: Path) -> None:
    input_data = _write_fixture(tmp_path, complete_tasks=True)
    input_data.spec_path.write_text(
        "---\n"
        "id: intent-spec\n"
        "title: Intent Specification\n"
        "status: draft\n"
        "nonfinite: .inf\n"
        "---\n"
        "The goal and constraint-files are covered.\n",
        encoding="utf-8",
    )

    report = check_planning_input(input_data)

    assert report.ok is False
    assert any(finding.code == "FRONTMATTER_INVALID" for finding in report.findings)


def test_unsafe_spec_id_cannot_authorize_unsafe_spec_ref(tmp_path: Path) -> None:
    input_data = _write_fixture(tmp_path, complete_tasks=True)
    input_data.spec_path.write_text(
        _SPEC.replace("id: intent-spec", "id: ../../outside"),
        encoding="utf-8",
    )
    input_data.plan_path.write_text(
        _PLAN.replace("spec_ref: intent-spec.md", "spec_ref: ../../outside"),
        encoding="utf-8",
    )

    report = check_planning_input(input_data)

    assert report.ok is False
    assert any(finding.code == "PLAN_SPEC_REF" for finding in report.findings)


def test_invalid_intent_is_fail_closed(tmp_path: Path) -> None:
    input_data = _write_fixture(tmp_path, complete_tasks=True)
    payload = json.loads(input_data.intent_path.read_text(encoding="utf-8"))
    payload["schema"] = 2
    input_data.intent_path.write_text(json.dumps(payload), encoding="utf-8")

    report = check_planning_input(input_data)

    assert report.ok is False
    assert any(finding.code == "INTENT_INVALID" for finding in report.findings)


def test_uncovered_intent_and_unsupported_claim_are_reported(tmp_path: Path) -> None:
    input_data = _write_fixture(tmp_path, complete_tasks=True)
    input_data.spec_path.write_text(
        "---\nid: intent-spec\ntitle: Intent Specification\nstatus: draft\n---\n"
        "goal only. claim:unanswered\n",
        encoding="utf-8",
    )

    report = check_planning_input(input_data)

    assert report.ok is False
    assert any(finding.code == "INTENT_UNCOVERED" for finding in report.findings)
    assert any(finding.code == "SPEC_UNSUPPORTED_CLAIM" for finding in report.findings)


def test_artifacts_are_relative_hashed_and_sorted(tmp_path: Path) -> None:
    report = check_planning_input(_write_fixture(tmp_path, complete_tasks=True))

    paths = [str(artifact["path"]) for artifact in report.artifacts]
    assert paths == sorted(paths)
    assert ".intent/intent.json" in paths
    assert "docs/superpowers/specs/intent-spec.md" in paths
    assert all(isinstance(artifact["sha256"], str) for artifact in report.artifacts)


def test_checker_does_not_write_derived_review_files(tmp_path: Path) -> None:
    input_data = _write_fixture(tmp_path, complete_tasks=True)
    before = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))

    report = check_planning_input(input_data)

    after = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))
    assert report.suggestion is None
    assert before == after


def test_planning_input_is_frozen(tmp_path: Path) -> None:
    input_data = _write_fixture(tmp_path, complete_tasks=True)

    with pytest.raises(AttributeError):
        input_data.run_id = "other"  # type: ignore[misc]


def test_empty_answers_fail_closed(tmp_path: Path) -> None:
    input_data = _write_fixture(tmp_path, complete_tasks=True)
    input_data.intent_path.write_text(
        json.dumps({"schema": 1, "prompt": "prompt", "answers": []}), encoding="utf-8"
    )

    report = check_planning_input(input_data)

    assert report.ok is False
    assert any(finding.code == "INTENT_INVALID" for finding in report.findings)


def test_nul_containing_path_fails_closed(tmp_path: Path) -> None:
    input_data = _write_fixture(tmp_path, complete_tasks=True)
    malformed_path = tmp_path / "intent\x00.json"
    input_data = replace(input_data, intent_path=malformed_path)

    report = check_planning_input(input_data)

    assert report.ok is False
    assert any(finding.code == "INPUT_READ_ERROR" for finding in report.findings)
