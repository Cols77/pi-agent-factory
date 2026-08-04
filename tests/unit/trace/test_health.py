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


def test_upstream_is_never_an_expected_slot():
    # A top-level SR legitimately has no parent; penalising that would be wrong.
    health = compute_health([_sr("SR-001")], [])

    assert "SR upstream" not in _by_name(health)
    assert _by_name(health)["SR validated"].expected == 1


def test_empty_repo_is_100_percent_not_a_division_error():
    assert compute_health([], []).percent == 100
