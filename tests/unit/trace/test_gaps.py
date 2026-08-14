from __future__ import annotations

from pathlib import Path

import pytest
from factory.trace.gaps import find_gaps
from factory.trace.model import Edge, Node
from factory.trace.validation_status import SrStatus

pytestmark = pytest.mark.unit


def _task(node_id: str, *, exempt: bool = False, deferred: str | None = None) -> Node:
    return Node(node_id, "task", node_id, Path(f"tasks/{node_id}.md"), exempt, deferred)


def _sr(node_id: str) -> Node:
    return Node(node_id, "sr", node_id, Path(f"requirements/{node_id}.md"))


def _plan(name: str) -> Node:
    return Node(f"plan:{name}", "plan", name, Path(f"docs/superpowers/plans/{name}"))


def _kinds(gaps, node_id: str) -> set[str]:
    return {g.kind for g in gaps if g.node_id == node_id}


def test_task_without_satisfies_is_a_gap():
    gaps = find_gaps([_task("T-001")], [], {})

    assert "task_no_sr" in _kinds(gaps, "T-001")


def test_task_declaring_no_source_plan_at_all_is_a_gap():
    # Found by running against cool_physical_ai_project: a task with no
    # source_plan key is as untraceable as one whose source_plan dangles.
    assert "task_no_plan" in _kinds(find_gaps([_task("T-001")], [], {}), "T-001")


def test_task_with_a_declared_source_plan_has_no_plan_gap():
    nodes = [_task("T-001"), _plan("p1.md")]
    edges = [Edge("T-001", "plan:p1.md", "source_plan")]

    assert "task_no_plan" not in _kinds(find_gaps(nodes, edges, {}), "T-001")


def test_task_source_plan_pointing_at_missing_file_is_a_gap():
    nodes = [_task("T-001")]
    edges = [Edge("T-001", "plan:gone.md", "source_plan")]

    assert "task_plan_missing" in _kinds(find_gaps(nodes, edges, {}), "T-001")


def test_plan_without_a_spec_reference_is_a_gap():
    assert "plan_no_spec" in _kinds(find_gaps([_plan("p1.md")], [], {}), "plan:p1.md")


def test_dangling_upstream_is_a_gap():
    nodes = [_sr("SR-001")]
    edges = [Edge("SR-001", "BR-002", "upstream")]

    assert "dangling_upstream" in _kinds(find_gaps(nodes, edges, {}), "SR-001")


def test_missing_vcycle_edge_target_is_a_dangling_reference_on_its_source():
    node = Node("FEAT-001", "feat", "Feature", Path("docs/features/FEAT-001.md"))

    gaps = find_gaps([node], [Edge("FEAT-001", "MISSING", "contains")], {})

    gap = next(gap for gap in gaps if gap.kind == "dangling_reference")
    assert gap.node_id == "FEAT-001"
    assert "contains" in gap.detail
    assert "MISSING" in gap.detail


def test_inverse_child_of_edge_with_missing_parent_is_reported_on_declaring_child():
    child = Node("FEAT-001", "feat", "Feature", Path("docs/features/FEAT-001.md"))

    gaps = find_gaps([child], [Edge("MISSING-PARENT", "FEAT-001", "parent_of")], {})

    gap = next(gap for gap in gaps if gap.kind == "dangling_reference")
    assert gap.node_id == "FEAT-001"
    assert "parent_of" in gap.detail
    assert "MISSING-PARENT" in gap.detail


def test_sr_absent_from_report_is_unvalidated_not_failed():
    kinds = _kinds(find_gaps([_sr("SR-001")], [], {}), "SR-001")

    assert "sr_unvalidated" in kinds


def test_passing_but_stale_sr_is_a_gap():
    validation = {"SR-001": SrStatus("SR-001", "passed", stale=True)}
    kinds = _kinds(find_gaps([_sr("SR-001")], [], validation), "SR-001")

    assert "sr_stale" in kinds
    assert "sr_unvalidated" not in kinds


def test_sr_with_no_satisfying_task_is_a_gap():
    assert "sr_unsatisfied" in _kinds(find_gaps([_sr("SR-001")], [], {}), "SR-001")


def test_satisfied_task_and_sr_produce_no_link_gaps():
    nodes = [_task("T-001"), _sr("SR-001")]
    edges = [Edge("T-001", "SR-001", "satisfies")]

    gaps = find_gaps(nodes, edges, {})

    assert "task_no_sr" not in _kinds(gaps, "T-001")
    assert "sr_unsatisfied" not in _kinds(gaps, "SR-001")


def test_exempt_task_gap_is_reported_with_exempt_disposition():
    gaps = [g for g in find_gaps([_task("T-001", exempt=True)], [], {}) if g.kind == "task_no_sr"]

    assert [g.disposition for g in gaps] == ["exempt"]


def test_deferred_task_gap_carries_the_reason_as_detail():
    nodes = [_task("T-001", deferred="needs an SR split first")]

    gaps = [g for g in find_gaps(nodes, [], {}) if g.kind == "task_no_sr"]

    assert gaps[0].disposition == "deferred"
    assert "needs an SR split first" in gaps[0].detail


def test_an_sr_cannot_exempt_itself_even_if_the_file_declares_it():
    # Spec 4.4: a requirement no task satisfies and no run validates is a real
    # gap, never an exception. A hand-edited SR must not be able to opt out.
    node = Node("SR-001", "sr", "SR-001", Path("requirements/SR-001.md"), exempt=True)

    gaps = [g for g in find_gaps([node], [], {}) if g.kind == "sr_unsatisfied"]

    assert gaps[0].disposition == "pending"


def test_gap_order_is_deterministic():
    nodes = [_task("T-002"), _task("T-001"), _plan("b.md"), _plan("a.md")]

    first = [(g.node_id, g.kind) for g in find_gaps(nodes, [], {})]
    second = [(g.node_id, g.kind) for g in find_gaps(list(reversed(nodes)), [], {})]

    assert first == second


def _proposed_sr(node_id: str) -> Node:
    return Node(node_id, "sr", node_id, Path(f"requirements/{node_id}.md"), proposed=True)


def test_a_proposed_requirement_reports_sr_proposed_and_is_deferred():
    gaps = find_gaps([_proposed_sr("SR-009")], [], {})
    kinds = _kinds(gaps, "SR-009")

    assert "sr_proposed" in kinds
    assert "sr_unvalidated" not in kinds
    # Deferred, not pending: the human accepted it knowing the binding was open,
    # which is exactly "discussed, still open". Pending would red-gate the repo
    # the moment the doctor is used.
    proposed = next(g for g in gaps if g.kind == "sr_proposed")
    assert proposed.disposition == "deferred"


def test_an_errored_requirement_is_unvalidatable_and_carries_the_reason():
    validation = {"SR-001": SrStatus("SR-001", "error", error="no harness 'sim-testbench'")}
    gaps = find_gaps([_sr("SR-001")], [], validation)

    gap = next(g for g in gaps if g.kind == "sr_unvalidatable")
    assert "no harness" in gap.detail
    assert gap.disposition == "pending"


def test_a_bound_requirement_with_no_report_is_unvalidated_not_unvalidatable():
    kinds = _kinds(find_gaps([_sr("SR-001")], [], {}), "SR-001")

    assert "sr_unvalidated" in kinds
    assert "sr_unvalidatable" not in kinds


def test_a_proposed_requirement_still_needs_a_satisfying_task():
    assert "sr_unsatisfied" in _kinds(find_gaps([_proposed_sr("SR-009")], [], {}), "SR-009")
