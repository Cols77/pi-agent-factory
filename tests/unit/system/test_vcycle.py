from __future__ import annotations

from pathlib import Path

import pytest

from factory.system.vcycle import vcycle_slice

pytestmark = pytest.mark.unit


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _nodes_by_band(result) -> dict[str, list[str]]:
    return {side.label: [node.id for node in side.nodes] for side in result.definition + result.verification}


def test_feature_slice_follows_the_recorded_vcycle_links(tmp_path):
    _write(
        tmp_path / "docs" / "features" / "FEAT-NAV-017.md",
        "---\n"
        "id: FEAT-NAV-017\n"
        "title: Target reacquisition\n"
        "contains: [SR-001]\n"
        "illustrates: ADR-0001\n"
        "---\n",
    )
    _write(
        tmp_path / "requirements" / "SR-001.md",
        "---\n"
        "id: SR-001\n"
        "title: Parent requirement\n"
        "statement: parent\n"
        "domain: behavior\n"
        "parent_of: [SR-002]\n"
        "verified_by: [T-001]\n"
        "---\n",
    )
    _write(
        tmp_path / "requirements" / "SR-002.md",
        "---\n"
        "id: SR-002\n"
        "title: Child requirement\n"
        "statement: child\n"
        "domain: behavior\n"
        "---\n",
    )
    _write(
        tmp_path / "tasks" / "T-001.md",
        "---\n"
        "id: T-001\n"
        "title: Implement child requirement\n"
        "status: done\n"
        "dod: []\n"
        "source_plan: docs/superpowers/plans/vcycle.md\n"
        "satisfies: [SR-002]\n"
        "---\n",
    )
    _write(
        tmp_path / "goals" / "GOAL-001.md",
        "---\n"
        "id: GOAL-001\n"
        "title: Reacquire target\n"
        "demonstrates: [SR-002]\n"
        "evaluates: [MET-001]\n"
        "---\n",
    )
    _write(
        tmp_path / "metrics" / "MET-001.md",
        "---\n"
        "id: MET-001\n"
        "title: reacquisition rate\n"
        "---\n",
    )
    _write(
        tmp_path / "docs" / "adr" / "ADR-0001.md",
        "---\n"
        "id: ADR-0001\n"
        "title: Reuse trace graph\n"
        "status: accepted\n"
        "---\n\n"
        "## Decision\n\nKeep it typed.\n",
    )
    _write(
        tmp_path / "docs" / "superpowers" / "plans" / "vcycle.md",
        "# V-cycle plan\n\nSee docs/superpowers/specs/vcycle.md.\n",
    )
    _write(tmp_path / "docs" / "superpowers" / "specs" / "vcycle.md", "# V-cycle spec\n")

    result = vcycle_slice(tmp_path, "feat:FEAT-NAV-017")

    assert result.anchor == "feat:FEAT-NAV-017"
    assert [side.label for side in result.definition] == [
        "NEEDS",
        "SYSTEM_REQUIREMENTS",
        "SUBSYSTEM_REQUIREMENTS",
        "ARCHITECTURE_DESIGN",
        "DETAILED_DESIGN",
        "CODE",
    ]
    assert [side.label for side in result.verification] == [
        "UNIT_VERIFICATION",
        "INTEGRATION_VERIFICATION",
        "SIMULATION_VERIFICATION",
        "SYSTEM_VALIDATION",
    ]
    nodes = _nodes_by_band(result)
    assert nodes == {
        "NEEDS": [],
        "SYSTEM_REQUIREMENTS": ["SR-001"],
        "SUBSYSTEM_REQUIREMENTS": ["SR-002"],
        "ARCHITECTURE_DESIGN": ["ADR-0001", "spec:vcycle.md"],
        "DETAILED_DESIGN": ["T-001", "plan:vcycle.md"],
        "CODE": [],
        "UNIT_VERIFICATION": [],
        "INTEGRATION_VERIFICATION": [],
        "SIMULATION_VERIFICATION": ["GOAL-001", "MET-001"],
        "SYSTEM_VALIDATION": ["T-001"],
    }
    assert [node.id for node in result.goals] == ["GOAL-001"]
    assert [node.id for node in result.metrics] == ["MET-001"]
    assert result.runs == []


def test_sr_anchor_is_exact_and_keeps_fixed_empty_bands(tmp_path):
    _write(
        tmp_path / "requirements" / "SR-010.md",
        "---\n"
        "id: SR-010\n"
        "title: Standalone\n"
        "statement: s\n"
        "domain: behavior\n"
        "---\n",
    )

    result = vcycle_slice(tmp_path, "sr:SR-010")

    assert [node.id for node in result.definition[1].nodes] == ["SR-010"]
    assert _nodes_by_band(result) == {
        "NEEDS": [],
        "SYSTEM_REQUIREMENTS": ["SR-010"],
        "SUBSYSTEM_REQUIREMENTS": [],
        "ARCHITECTURE_DESIGN": [],
        "DETAILED_DESIGN": [],
        "CODE": [],
        "UNIT_VERIFICATION": [],
        "INTEGRATION_VERIFICATION": [],
        "SIMULATION_VERIFICATION": [],
        "SYSTEM_VALIDATION": [],
    }
    with pytest.raises(ValueError, match="vcycle anchor"):
        vcycle_slice(tmp_path, "FEAT-NAV-017")


def test_sr_anchor_walks_parent_of_hierarchy_in_both_directions(tmp_path):
    _write(
        tmp_path / "requirements" / "BR-001.md",
        "---\n"
        "id: BR-001\n"
        "title: Need\n"
        "statement: n\n"
        "domain: business\n"
        "parent_of: [SR-001]\n"
        "---\n",
    )
    _write(
        tmp_path / "requirements" / "SR-001.md",
        "---\n"
        "id: SR-001\n"
        "title: Parent system requirement\n"
        "statement: p\n"
        "domain: behavior\n"
        "parent_of: [SR-002]\n"
        "---\n",
    )
    _write(
        tmp_path / "requirements" / "SR-002.md",
        "---\n"
        "id: SR-002\n"
        "title: Child subsystem requirement\n"
        "statement: c\n"
        "domain: behavior\n"
        "---\n",
    )

    result = vcycle_slice(tmp_path, "sr:SR-002")

    nodes = _nodes_by_band(result)
    assert nodes["NEEDS"] == ["BR-001"]
    assert nodes["SYSTEM_REQUIREMENTS"] == ["SR-001"]
    assert nodes["SUBSYSTEM_REQUIREMENTS"] == ["SR-002"]


def test_goal_and_metric_evidence_only_follow_the_declared_direction(tmp_path):
    _write(
        tmp_path / "requirements" / "SR-100.md",
        "---\n"
        "id: SR-100\n"
        "title: Scoped requirement\n"
        "statement: s\n"
        "domain: behavior\n"
        "demonstrates: [GOAL-REVERSE]\n"
        "evaluates: [MET-REVERSE]\n"
        "---\n",
    )
    _write(
        tmp_path / "goals" / "GOAL-VALID.md",
        "---\n"
        "id: GOAL-VALID\n"
        "title: Valid goal\n"
        "demonstrates: [SR-100]\n"
        "evaluates: [MET-VALID]\n"
        "---\n",
    )
    _write(
        tmp_path / "goals" / "GOAL-REVERSE.md",
        "---\n"
        "id: GOAL-REVERSE\n"
        "title: Reverse goal\n"
        "---\n",
    )
    _write(
        tmp_path / "metrics" / "MET-VALID.md",
        "---\n"
        "id: MET-VALID\n"
        "title: Valid metric\n"
        "---\n",
    )
    _write(
        tmp_path / "metrics" / "MET-REVERSE.md",
        "---\n"
        "id: MET-REVERSE\n"
        "title: Reverse metric\n"
        "---\n",
    )

    result = vcycle_slice(tmp_path, "sr:SR-100")

    assert [node.id for node in result.goals] == ["GOAL-VALID"]
    assert [node.id for node in result.metrics] == ["MET-VALID"]
    verification_ids = {
        node.id for side in result.verification for node in side.nodes
    }
    assert {"GOAL-VALID", "MET-VALID"} <= verification_ids
    assert {"GOAL-REVERSE", "MET-REVERSE"}.isdisjoint(verification_ids)


def test_verification_bands_follow_subsystem_and_architecture_roles(tmp_path):
    _write(
        tmp_path / "docs" / "features" / "FEAT-001.md",
        "---\n"
        "id: FEAT-001\n"
        "title: Scoped feature\n"
        "contains: [SR-001]\n"
        "---\n",
    )
    _write(
        tmp_path / "requirements" / "SR-001.md",
        "---\n"
        "id: SR-001\n"
        "title: Parent requirement\n"
        "statement: p\n"
        "domain: behavior\n"
        "parent_of: [SR-002]\n"
        "---\n",
    )
    _write(
        tmp_path / "requirements" / "SR-002.md",
        "---\n"
        "id: SR-002\n"
        "title: Child requirement\n"
        "statement: c\n"
        "domain: behavior\n"
        "verified_by: [T-SUBSYSTEM]\n"
        "---\n",
    )
    _write(
        tmp_path / "docs" / "diagrams" / "DIAG-001.md",
        "---\n"
        "id: DIAG-001\n"
        "title: Architecture diagram\n"
        "diagram_file: architecture.html\n"
        "illustrates: [FEAT-001]\n"
        "verified_by: [T-ARCHITECTURE]\n"
        "---\n",
    )
    for task_id in ("T-SUBSYSTEM", "T-ARCHITECTURE"):
        _write(
            tmp_path / "tasks" / f"{task_id}.md",
            "---\n"
            f"id: {task_id}\n"
            "title: Verification task\n"
            "status: done\n"
            "dod: []\n"
            "---\n",
        )

    result = vcycle_slice(tmp_path, "feat:FEAT-001")

    nodes = _nodes_by_band(result)
    assert nodes["SIMULATION_VERIFICATION"] == ["T-SUBSYSTEM"]
    assert nodes["INTEGRATION_VERIFICATION"] == ["T-ARCHITECTURE"]
