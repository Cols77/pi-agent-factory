from __future__ import annotations

from pathlib import Path

import pytest

from coherence.trace.graph import build_graph
from coherence.trace.model import SpecError, extract_edges, load_nodes

pytestmark = pytest.mark.unit


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _coherence_spec(tmp_path: Path) -> Path:
    return _write(
        tmp_path / "docs" / "superpowers" / "specs" / "coherence.md",
        "---\nid: SPEC-COHERENCE-001\ntitle: Coherence\nstatus: accepted\n---\n\n"
        "# Coherence\n\nbody\n",
    )


def _plan_with_spec_field(tmp_path: Path, spec_ref: str) -> Path:
    return _write(
        tmp_path / "docs" / "superpowers" / "plans" / "p1.md",
        f"---\nspec: {spec_ref}\n---\n\n# P1\n\nbody\n",
    )


@pytest.mark.sr("SR-003")
def test_frontmatter_spec_emits_the_canonical_spec_node(tmp_path):
    _coherence_spec(tmp_path)

    nodes = {n.id: n for n in load_nodes(tmp_path)}

    node = nodes["spec:SPEC-COHERENCE-001"]
    assert node.kind == "spec"
    assert node.title == "Coherence"


def test_graph_emits_spec_node_for_frontmatter_spec(tmp_path):
    _coherence_spec(tmp_path)

    graph = build_graph(tmp_path)
    ids = {n.id for n in graph.nodes}

    assert "spec:SPEC-COHERENCE-001" in ids


@pytest.mark.sr("SR-003")
def test_plan_edges_target_the_canonical_spec_id(tmp_path):
    # A canonical frontmatter spec ref (`spec: SPEC-COHERENCE-001`) declared on a
    # plan must produce an edge to the canonical spec node, not a filename id.
    _coherence_spec(tmp_path)
    _plan_with_spec_field(tmp_path, "SPEC-COHERENCE-001")

    graph = build_graph(tmp_path)
    edges = [(e.src, e.dst, e.kind) for e in graph.edges if e.kind == "spec_ref"]

    assert ("plan:p1.md", "spec:SPEC-COHERENCE-001", "spec_ref") in edges


@pytest.mark.sr("SR-003")
def test_a_plan_body_reference_resolves_to_the_canonical_spec_id(tmp_path):
    # A literal body path must now resolve against real spec nodes, so the
    # edge targets the canonical frontmatter id, not a filename-derived id.
    _coherence_spec(tmp_path)
    _write(
        tmp_path / "docs" / "superpowers" / "plans" / "p1.md",
        "# P1\n\nSee docs/superpowers/specs/coherence.md for context.\n",
    )

    graph = build_graph(tmp_path)
    edges = [(e.src, e.dst, e.kind) for e in graph.edges if e.kind == "spec_ref"]

    assert ("plan:p1.md", "spec:SPEC-COHERENCE-001", "spec_ref") in edges
    assert not any(dst == "spec:coherence.md" for _src, dst, _kind in edges)


def test_filename_only_specs_remain_readable_legacy_nodes(tmp_path):
    _write(tmp_path / "docs" / "superpowers" / "specs" / "2026-07-30-legacy.md", "# Legacy\nno fm\n")

    nodes = {n.id: n for n in load_nodes(tmp_path)}

    assert nodes["spec:2026-07-30-legacy.md"].kind == "spec"
    assert nodes["spec:2026-07-30-legacy.md"].title == "Legacy"


def test_legacy_spec_carries_a_diagnostic_migration_hint(tmp_path):
    _write(tmp_path / "docs" / "superpowers" / "specs" / "legacy.md", "# Legacy\nno fm\n")

    (node,) = [n for n in load_nodes(tmp_path) if n.kind == "spec"]

    assert node.migration_hint is not None
    assert "migration" in node.migration_hint.lower()


@pytest.mark.sr("SR-003")
def test_duplicate_spec_ids_with_differing_content_fail_deterministically(tmp_path):
    _write(
        tmp_path / "docs" / "superpowers" / "specs" / "a.md",
        "---\nid: SPEC-DUP\ntitle: A\nstatus: accepted\n---\na\n",
    )
    _write(
        tmp_path / "docs" / "superpowers" / "specs" / "b.md",
        "---\nid: SPEC-DUP\ntitle: A\nstatus: accepted\n---\nb\n",
    )

    with pytest.raises(SpecError, match="duplicate"):
        load_nodes(tmp_path)


def test_frontmatter_spec_missing_required_field_fails_deterministically(tmp_path):
    _write(
        tmp_path / "docs" / "superpowers" / "specs" / "partial.md",
        "---\nstatus: accepted\n---\nno id\n",
    )

    with pytest.raises(SpecError):
        load_nodes(tmp_path)


def test_missing_status_fails_deterministically(tmp_path):
    _write(
        tmp_path / "docs" / "superpowers" / "specs" / "partial.md",
        "---\nid: SPEC-X\ntitle: X\n---\nno status\n",
    )

    with pytest.raises(SpecError):
        load_nodes(tmp_path)


def test_missing_title_fails_deterministically(tmp_path):
    _write(
        tmp_path / "docs" / "superpowers" / "specs" / "partial.md",
        "---\nid: SPEC-X\nstatus: accepted\n---\nno title\n",
    )

    with pytest.raises(SpecError):
        load_nodes(tmp_path)


def test_empty_frontmatter_block_fails_deterministically_not_legacy(tmp_path):
    # An explicit ``---`` block with no fields is a frontmatter-bearing spec
    # missing every required field; it must raise, never fall back to a legacy
    # filename-derived node.
    _write(
        tmp_path / "docs" / "superpowers" / "specs" / "empty.md",
        "---\n---\n# Empty\nno fields\n",
    )

    with pytest.raises(SpecError):
        load_nodes(tmp_path)


def test_malformed_frontmatter_fails_deterministically_not_legacy(tmp_path):
    # Undecodable frontmatter is NOT a valid frontmatter spec; it must raise
    # rather than quietly degrade to a legacy filename-derived node.
    _write(
        tmp_path / "docs" / "superpowers" / "specs" / "broken.md",
        "---\nid: [unclosed\nstatus: accepted\n---\nbody\n",
    )

    with pytest.raises(SpecError, match="unreadable"):
        load_nodes(tmp_path)


def test_relation_to_an_unknown_spec_id_fails_deterministically(tmp_path):
    _coherence_spec(tmp_path)
    _plan_with_spec_field(tmp_path, "SPEC-DOES-NOT-EXIST")

    with pytest.raises(SpecError):
        build_graph(tmp_path)


def test_unknown_spec_reference_is_reported_on_the_plan(tmp_path):
    _coherence_spec(tmp_path)
    _plan_with_spec_field(tmp_path, "SPEC-DOES-NOT-EXIST")

    with pytest.raises(SpecError):
        extract_edges(tmp_path, load_nodes(tmp_path))