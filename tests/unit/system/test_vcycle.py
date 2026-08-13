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
        "requirements",
        "design",
        "implementation",
    ]
    assert [side.label for side in result.verification] == [
        "verification",
        "goals",
        "metrics",
        "runs",
    ]
    nodes = _nodes_by_band(result)
    assert nodes["requirements"] == ["SR-001", "SR-002"]
    assert nodes["design"] == ["ADR-0001", "plan:vcycle.md", "spec:vcycle.md"]
    assert nodes["implementation"] == ["T-001"]
    assert nodes["verification"] == ["T-001"]
    assert nodes["goals"] == ["GOAL-001"]
    assert nodes["metrics"] == ["MET-001"]
    assert nodes["runs"] == []
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

    assert [node.id for node in result.definition[0].nodes] == ["SR-010"]
    assert _nodes_by_band(result) == {
        "requirements": ["SR-010"],
        "design": [],
        "implementation": [],
        "verification": [],
        "goals": [],
        "metrics": [],
        "runs": [],
    }
    with pytest.raises(ValueError, match="vcycle anchor"):
        vcycle_slice(tmp_path, "FEAT-NAV-017")
