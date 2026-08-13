from __future__ import annotations

from pathlib import Path

import pytest
from factory.trace.gaps import Gap
from factory.trace.health import compute_health
from factory.trace.model import Node

pytestmark = pytest.mark.unit


def _task(node_id: str) -> Node:
    return Node(node_id, "task", node_id, Path(f"tasks/{node_id}.md"))


def _sr(node_id: str) -> Node:
    return Node(node_id, "sr", node_id, Path(f"requirements/{node_id}.md"))


def _by_name(health) -> dict:
    return {c.name: c for c in health.classes}


def test_no_gaps_is_full_health():
    health = compute_health([_task("T-001")], [])

    assert health.percent == 100
    assert health.expected == 2  # one source_plan slot + one satisfies slot


def test_pending_gap_consumes_a_slot():
    gaps = [Gap("T-001", "task_no_sr", "d", "pending")]

    health = compute_health([_task("T-001")], gaps)

    assert _by_name(health)["task->SR"].satisfied == 0
    assert health.percent == 50


def test_task_without_a_source_plan_consumes_the_plan_slot():
    gaps = [Gap("T-001", "task_no_plan", "d", "pending")]

    health = compute_health([_task("T-001")], gaps)

    assert _by_name(health)["task->plan"].satisfied == 0
    assert health.percent == 50


def test_exempt_gap_removes_the_slot_so_100_stays_reachable():
    gaps = [Gap("T-001", "task_no_sr", "d", "exempt")]

    health = compute_health([_task("T-001")], gaps)

    assert _by_name(health)["task->SR"].expected == 0
    assert _by_name(health)["task->SR"].exempt == 1
    assert health.percent == 100


def test_deferred_gap_still_counts_against_the_score():
    # Deferring is honest, not free -- it must not inflate the number.
    gaps = [Gap("T-001", "task_no_sr", "d", "deferred")]

    health = compute_health([_task("T-001")], gaps)

    assert _by_name(health)["task->SR"].satisfied == 0
    assert health.deferred == 1
    assert health.percent == 50


def test_dangling_references_are_counted_but_not_scored():
    gaps = [Gap("SR-001", "dangling_upstream", "d", "pending")]

    health = compute_health([_sr("SR-001")], gaps)

    assert health.dangling == 1
    assert _by_name(health)["SR satisfied"].expected == 1


def test_dangling_vcycle_reference_is_counted_but_not_scored():
    gaps = [Gap("FEAT-001", "dangling_reference", "contains target missing", "pending")]
    feature = Node("FEAT-001", "feat", "Feature", Path("docs/features/FEAT-001.md"))

    health = compute_health([feature], gaps)

    assert health.dangling == 1
    assert health.expected == 0


def test_upstream_is_never_an_expected_slot():
    # A top-level SR legitimately has no parent; penalising that would be wrong.
    health = compute_health([_sr("SR-001")], [])

    assert "SR upstream" not in _by_name(health)
    assert _by_name(health)["SR validated"].expected == 1


def test_empty_repo_is_100_percent_not_a_division_error():
    assert compute_health([], []).percent == 100


def _proposed_sr(node_id: str) -> Node:
    return Node(node_id, "sr", node_id, Path(f"requirements/{node_id}.md"), proposed=True)


def test_a_proposed_requirement_leaves_the_validated_denominator():
    # Nobody has claimed it is measurable yet, so counting it as an unfilled
    # validation slot would punish the doctor for recording a real state.
    nodes = [_proposed_sr("SR-009")]
    gaps = [
        Gap("SR-009", "sr_unsatisfied", "d", "pending"),
        Gap("SR-009", "sr_proposed", "d", "deferred"),
    ]

    health = compute_health(nodes, gaps)

    assert _by_name(health)["SR validated"].expected == 0
    assert health.proposed == 1


def test_a_proposed_requirement_stays_in_the_satisfied_denominator():
    nodes = [_proposed_sr("SR-009")]
    gaps = [
        Gap("SR-009", "sr_unsatisfied", "d", "pending"),
        Gap("SR-009", "sr_proposed", "d", "deferred"),
    ]

    satisfied = _by_name(compute_health(nodes, gaps))["SR satisfied"]

    assert satisfied.expected == 1
    assert satisfied.satisfied == 0


def test_an_unvalidatable_requirement_counts_as_unfilled():
    # Excluding it would hand a project with no config a green validation score.
    nodes = [_sr("SR-001")]
    gaps = [Gap("SR-001", "sr_unvalidatable", "no harness", "pending")]

    validated = _by_name(compute_health(nodes, gaps))["SR validated"]

    assert validated.expected == 1
    assert validated.satisfied == 0


def test_proposed_is_reported_on_its_own_line_not_as_deferred():
    nodes = [_proposed_sr("SR-009")]
    gaps = [Gap("SR-009", "sr_proposed", "d", "deferred")]

    assert compute_health(nodes, gaps).deferred == 0
