from __future__ import annotations

from pathlib import Path

import pytest
from factory.trace.model import Edge, extract_edges, load_nodes

pytestmark = pytest.mark.unit


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _edges(tmp_path: Path) -> list[Edge]:
    return extract_edges(tmp_path, load_nodes(tmp_path))


def test_task_declares_source_plan_and_satisfies(tmp_path):
    _write(
        tmp_path / "tasks" / "T-012.md",
        "---\nid: T-012\ntitle: t\nstatus: done\ndod: []\n"
        "source_plan: docs/superpowers/plans/p1.md\nsatisfies:\n- SR-001\n---\n",
    )
    _write(tmp_path / "docs" / "superpowers" / "plans" / "p1.md", "# P\n")

    edges = _edges(tmp_path)

    assert Edge("T-012", "plan:p1.md", "source_plan") in edges
    assert Edge("T-012", "SR-001", "satisfies") in edges


def test_scalar_satisfies_is_accepted_as_single_edge(tmp_path):
    _write(
        tmp_path / "tasks" / "T-013.md",
        "---\nid: T-013\ntitle: t\nstatus: todo\ndod: []\nsatisfies: SR-002\n---\n",
    )

    assert Edge("T-013", "SR-002", "satisfies") in _edges(tmp_path)


def test_sr_upstream_edge_is_kept_even_when_target_is_missing(tmp_path):
    _write(
        tmp_path / "requirements" / "SR-001.md",
        "---\nid: SR-001\ntitle: t\nstatement: s\ndomain: d\n"
        "binding:\n  harness: h\n  experiment: e\n  metric: m\n  assert: '>= 0.9'\n"
        "upstream:\n- BR-002\n---\n",
    )

    assert Edge("SR-001", "BR-002", "upstream") in _edges(tmp_path)


def test_plan_spec_edge_comes_from_a_literal_path_in_the_body(tmp_path):
    _write(
        tmp_path / "docs" / "superpowers" / "plans" / "p1.md",
        "# Plan\n\nSee docs/superpowers/specs/2026-07-30-design.md for context.\n",
    )
    _write(tmp_path / "docs" / "superpowers" / "specs" / "2026-07-30-design.md", "# Spec\n")

    assert Edge("plan:p1.md", "spec:2026-07-30-design.md", "spec_ref") in _edges(tmp_path)


def test_similar_filenames_alone_never_create_an_edge(tmp_path):
    # The core invariant: a plan and a spec sharing a date and stem are NOT linked
    # unless the plan actually writes the path. Spec section 4.2.
    _write(tmp_path / "docs" / "superpowers" / "plans" / "2026-07-30-sim.md", "# Sim Plan\n")
    _write(tmp_path / "docs" / "superpowers" / "specs" / "2026-07-30-sim-design.md", "# Sim Spec\n")

    assert [e for e in _edges(tmp_path) if e.kind == "spec_ref"] == []


def test_duplicate_references_produce_one_edge(tmp_path):
    _write(
        tmp_path / "docs" / "superpowers" / "plans" / "p1.md",
        "# P\n\ndocs/superpowers/specs/s1.md and again docs/superpowers/specs/s1.md\n",
    )
    _write(tmp_path / "docs" / "superpowers" / "specs" / "s1.md", "# S\n")

    assert len([e for e in _edges(tmp_path) if e.kind == "spec_ref"]) == 1


def test_feature_vcycle_frontmatter_fields_produce_typed_edges(tmp_path):
    _write(
        tmp_path / "docs" / "features" / "FEAT-NAV-017.md",
        "---\nid: FEAT-NAV-017\ntitle: Target reacquisition\n"
        "contains: [SR-001]\nparent_of: SR-002\nchild_of: SR-003\n"
        "verified_by: RUN-001\ndemonstrates: GOAL-001\nevaluates: MET-001\n"
        "illustrates: ADR-0001\n---\n",
    )

    edges = _edges(tmp_path)

    assert {
        Edge("FEAT-NAV-017", "SR-001", "contains"),
        Edge("FEAT-NAV-017", "SR-002", "parent_of"),
        Edge("SR-003", "FEAT-NAV-017", "parent_of"),
        Edge("FEAT-NAV-017", "RUN-001", "verified_by"),
        Edge("FEAT-NAV-017", "GOAL-001", "demonstrates"),
        Edge("FEAT-NAV-017", "MET-001", "evaluates"),
        Edge("FEAT-NAV-017", "ADR-0001", "illustrates"),
    } <= set(edges)


def test_diagram_stub_illustrates_target_with_a_typed_edge(tmp_path):
    _write(
        tmp_path / "docs" / "diagrams" / "DIAG-NAV-001.md",
        "---\nid: DIAG-NAV-001\nkind: diag\ntitle: Navigator overview\n"
        "focus: Traceability\nillustrates: ADR-0001\ndiagram_file: overview.mmd\n---\n",
    )

    assert Edge("DIAG-NAV-001", "ADR-0001", "illustrates") in _edges(tmp_path)
