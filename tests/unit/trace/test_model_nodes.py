from __future__ import annotations

from pathlib import Path

import pytest
from factory.trace.graph import build_graph
from factory.trace.model import load_nodes

pytestmark = pytest.mark.unit


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_loads_sr_task_plan_and_spec_nodes(tmp_path):
    _write(
        tmp_path / "requirements" / "SR-001.md",
        "---\nid: SR-001\ntitle: Preempt patrol\nstatement: s\ndomain: behavioral\n"
        "binding:\n  harness: h\n  experiment: e\n  metric: m\n  assert: '>= 0.9'\n---\n\nbody\n",
    )
    _write(
        tmp_path / "tasks" / "T-047-bug-capture.md",
        "---\nid: T-047\ntitle: Bug Capture\nstatus: done\ndod: []\n---\n\nbody\n",
    )
    _write(tmp_path / "docs" / "superpowers" / "plans" / "p1.md", "# Sim Testbench Plan\n\nbody\n")
    _write(tmp_path / "docs" / "superpowers" / "specs" / "s1.md", "# Sim Design\n\nbody\n")

    nodes = {n.id: n for n in load_nodes(tmp_path)}

    assert nodes["SR-001"].kind == "sr"
    assert nodes["SR-001"].title == "Preempt patrol"
    assert nodes["T-047"].kind == "task"
    assert nodes["T-047"].title == "Bug Capture"
    assert nodes["plan:p1.md"].kind == "plan"
    assert nodes["plan:p1.md"].title == "Sim Testbench Plan"
    assert nodes["spec:s1.md"].kind == "spec"
    assert nodes["spec:s1.md"].title == "Sim Design"


def test_loads_feature_metric_and_goal_nodes_with_declared_ids_and_titles(tmp_path):
    _write(
        tmp_path / "docs" / "features" / "FEAT-NAV-017.md",
        "---\nid: FEAT-NAV-017\ntitle: Target Reacquisition\nstatus: implemented\n---\n# FEAT\n",
    )
    _write(
        tmp_path / "metrics" / "MET-NAV-004.md",
        "---\nid: MET-NAV-004\ntitle: reacquisition_rate\n---\n# MET\n",
    )
    _write(
        tmp_path / "goals" / "GOAL-NAV-003.md",
        "---\nid: GOAL-NAV-003\ntitle: reacquire >= 90%\n---\n# GOAL\n",
    )

    nodes = {node.id: node for node in load_nodes(tmp_path)}

    assert (nodes["FEAT-NAV-017"].kind, nodes["FEAT-NAV-017"].title) == (
        "feat",
        "Target Reacquisition",
    )
    assert (nodes["MET-NAV-004"].kind, nodes["MET-NAV-004"].title) == (
        "metric",
        "reacquisition_rate",
    )
    assert (nodes["GOAL-NAV-003"].kind, nodes["GOAL-NAV-003"].title) == (
        "goal",
        "reacquire >= 90%",
    )


def test_loads_diagram_stub_with_declared_id_and_title(tmp_path):
    _write(
        tmp_path / "docs" / "diagrams" / "DIAG-NAV-001.md",
        "---\nid: DIAG-NAV-001\nkind: diag\ntitle: Navigator overview\n"
        "focus: Traceability\nillustrates: FEAT-NAV-017\ndiagram_file: overview.html\n---\n",
    )

    nodes = {node.id: node for node in load_nodes(tmp_path)}

    assert (nodes["DIAG-NAV-001"].kind, nodes["DIAG-NAV-001"].title) == (
        "diag",
        "Navigator overview",
    )


def test_build_graph_adapts_scc_adr_records_to_trace_nodes(tmp_path):
    path = _write(
        tmp_path / "docs" / "adr" / "ADR-0001.md",
        "---\nid: ADR-0001\ntitle: Use the existing ADR parser\nstatus: accepted\n---\n\n"
        "## Decision\n\nKeep one source of truth.\n",
    )

    adr_nodes = [node for node in build_graph(tmp_path).nodes if node.id == "ADR-0001"]

    assert len(adr_nodes) == 1
    assert adr_nodes[0].kind == "adr"
    assert adr_nodes[0].title == "Use the existing ADR parser"
    assert adr_nodes[0].path == path


def test_malformed_adr_does_not_block_ordinary_trace_nodes(tmp_path):
    _write(tmp_path / "docs" / "adr" / "ADR-0009.md", "# ADR-0009: Legacy\n")
    _write(
        tmp_path / "tasks" / "T-001.md",
        "---\nid: T-001\ntitle: Remain available\nstatus: todo\ndod: []\n---\n",
    )

    nodes = {node.id: node for node in build_graph(tmp_path).nodes}

    assert "ADR-0009" not in nodes
    assert nodes["T-001"].kind == "task"


def test_malformed_task_degrades_to_filename_instead_of_raising(tmp_path):
    _write(tmp_path / "tasks" / "T-099-broken.md", "---\nnot: valid: yaml: at all\n")

    nodes = {n.id: n for n in load_nodes(tmp_path)}

    assert nodes["T-099-broken.md"].kind == "task"
    assert nodes["T-099-broken.md"].title == "T-099-broken.md"


def test_malformed_spec_degrades_to_filename_instead_of_raising(tmp_path):
    # `_file_node` (specs/plans) re-reads the file when frontmatter parsing
    # fails; that fallback read must degrade too, not crash load_nodes for
    # every other artifact over one undecodable spec.
    path = tmp_path / "docs" / "superpowers" / "specs" / "bad-design.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"# Bad\xff\xfe\n\nInvalid bytes above.\n")
    _write(tmp_path / "tasks" / "T-001.md", "---\nid: T-001\ntitle: t\nstatus: todo\ndod: []\n---\n")

    nodes = {n.path.name: n for n in load_nodes(tmp_path)}

    assert nodes["bad-design.md"].kind == "spec"
    assert nodes["bad-design.md"].title == "bad-design.md"
    assert nodes["T-001.md"].id == "T-001"


def test_reads_exempt_and_deferred_dispositions(tmp_path):
    _write(
        tmp_path / "tasks" / "T-001.md",
        "---\nid: T-001\ntitle: Infra\nstatus: done\ndod: []\ntrace_exempt: true\n---\n",
    )
    _write(
        tmp_path / "tasks" / "T-002.md",
        '---\nid: T-002\ntitle: Later\nstatus: todo\ndod: []\n'
        'trace_deferred: "needs SR split"\n---\n',
    )

    nodes = {n.id: n for n in load_nodes(tmp_path)}

    assert nodes["T-001"].exempt is True
    assert nodes["T-001"].deferred is None
    assert nodes["T-002"].exempt is False
    assert nodes["T-002"].deferred == "needs SR split"


def test_missing_directories_yield_no_nodes(tmp_path):
    assert load_nodes(tmp_path) == []


def test_a_requirement_without_a_binding_is_proposed(tmp_path):
    _write(
        tmp_path / "requirements" / "SR-009.md",
        "---\nid: SR-009\ntitle: Zone clear\nstatement: s\ndomain: behavioral\n---\n\nbody\n",
    )
    nodes = {n.id: n for n in load_nodes(tmp_path)}
    assert nodes["SR-009"].proposed is True


def test_a_bound_requirement_is_not_proposed(tmp_path):
    _write(
        tmp_path / "requirements" / "SR-001.md",
        "---\nid: SR-001\ntitle: t\nstatement: s\ndomain: behavioral\n"
        "binding:\n  harness: h\n  experiment: e\n  metric: m\n  assert: '>= 0.9'\n---\n\nbody\n",
    )
    nodes = {n.id: n for n in load_nodes(tmp_path)}
    assert nodes["SR-001"].proposed is False


def test_a_task_is_never_proposed(tmp_path):
    _write(tmp_path / "tasks" / "T-001.md", "---\nid: T-001\ntitle: t\nstatus: todo\ndod: []\n---\n")
    assert all(n.proposed is False for n in load_nodes(tmp_path) if n.kind == "task")


def test_a_malformed_requirement_still_degrades_to_a_filename_node(tmp_path):
    # proposed adds a second frontmatter read; the degrade contract must survive it.
    _write(tmp_path / "requirements" / "SR-bad.md", "---\nnot: valid: yaml: at all\n")
    nodes = {n.path.name: n for n in load_nodes(tmp_path)}
    assert nodes["SR-bad.md"].id == "SR-bad.md"
    assert nodes["SR-bad.md"].proposed is False
