"""Triage inbox (Increment 6 Task 4).

`list_items(root, now)` composes several PURE source collectors into one
stable-sorted, de-duplicated `InboxItem` list. It never writes; `resolve_cmd`
is informational. Sources wired concretely here: expired deferrals, stale
register bindings, and coverage gates awaiting a decision.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from coherence.inbox import InboxItem, list_items

pytestmark = pytest.mark.unit

NOW = "2026-09-15T00:00:00Z"


def _sr(root: Path, sid: str, *, deferred=None) -> None:
    (root / "requirements").mkdir(parents=True, exist_ok=True)
    defer_line = ""
    if deferred is not None:
        defer_line = f"trace_deferred: {json.dumps(deferred)}\n"
    (root / "requirements" / f"{sid}.md").write_text(
        f"---\nid: {sid}\ntitle: T\nstatement: s\ndomain: d\n{defer_line}---\nbody\n",
        encoding="utf-8",
    )


def _dimension_counts(items: list[InboxItem]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        counts[item.kind] = counts.get(item.kind, 0) + 1
    return counts


# -- InboxItem model / JSON shape -------------------------------------------


def test_inbox_item_carries_the_full_contract(tmp_path):
    _sr(tmp_path, "SR-001")
    db_dir = tmp_path / "coverage-reviews" / "FEAT-001-r1" / "gate-decisions"
    db_dir.mkdir(parents=True)
    GateStatus = tmp_path / "coverage-reviews" / "FEAT-001-r1" / "status.json"
    GateStatus.parent.mkdir(parents=True, exist_ok=True)
    GateStatus.write_text(
        json.dumps(
            {
                "phase": "gates_blocked",
                "needed_items": ["coverage:r1:proposal:SR-999"],
            }
        ),
        encoding="utf-8",
    )

    items = list_items(tmp_path, NOW)
    assert items  # at least the coverage gate item
    item = items[0]
    # The full contract: id/source/kind/ref/summary/evidence + resolve_cmd +
    # review_after, JSON-serializable (pure value object, no Path/no file).
    d = item.to_dict()
    assert set(d) == {
        "id", "source", "kind", "ref", "summary", "evidence",
        "resolve_cmd", "review_after",
    }
    json.dumps(d)  # must not raise


# -- expired deferrals -------------------------------------------------------


def test_expired_deferral_appears_and_future_one_does_not(tmp_path):
    _sr(tmp_path, "SR-001", deferred={"reason": "later", "review_after": "2026-09-01T00:00:00Z"})
    _sr(tmp_path, "SR-002", deferred={"reason": "later", "review_after": "2026-12-31T00:00:00Z"})

    items = list_items(tmp_path, NOW)
    kinds = _dimension_counts(items)
    assert kinds.get("expired_deferral", 0) == 1  # only SR-001 is due as of NOW
    expired = next(i for i in items if i.kind == "expired_deferral")
    assert expired.ref == "sr:SR-001"
    assert expired.review_after == "2026-09-01T00:00:00Z"
    assert expired.source == "deferrals"


# -- stale register bindings ------------------------------------------------


_BOUND_SR = """---
id: SR-001
title: "Nav preempts patrol for in-zone shark"
statement: "When a shark is detected inside a swim zone, the navigation system shall preempt patrol."
domain: behavioral
binding:
  harness: sim-testbench
  experiment: shark_warning
  metric: preemption_success_rate
  trials: 20
  assert: ">= 0.90"
checksum: {checksum}
---
body
"""


def test_stale_register_binding_appears(tmp_path):
    # A bound requirement whose recorded checksum is stale renders the same
    # present-deferral reason and surfaces as a stale_binding triage item.
    from coherence.register.register import (
        content_checksum,
        is_checksum_current,
        load_register,
    )

    req_dir = tmp_path / "requirements"
    req_dir.mkdir(parents=True)
    # Write the requirement with a real binding, compute its current checksum,
    # then rewrite with a DIFFERENT statement but the SAME recorded checksum
    # so the recorded value no longer matches -> stale.
    p = req_dir / "SR-001.md"
    p.write_text(_BOUND_SR.format(checksum="null"), encoding="utf-8")
    current = content_checksum(load_register(req_dir)[0])
    # Change the statement (staling the content) but keep the recorded checksum.
    p.write_text(
        _BOUND_SR.format(checksum=current).replace(
            "shall preempt patrol", "shall preempt patrol immediately and report"
        ),
        encoding="utf-8",
    )
    assert any(not is_checksum_current(r) for r in load_register(req_dir))

    items = list_items(tmp_path, NOW)
    kinds = {i.kind for i in items}
    assert "stale_binding" in kinds
    stale = next(i for i in items if i.kind == "stale_binding")
    assert stale.ref == "sr:SR-001"
    assert stale.source == "register"


# -- coverage gates awaiting a decision -------------------------------------


def test_coverage_gate_item_for_blocked_run(tmp_path):
    run_dir = tmp_path / "coverage-reviews" / "FEAT-001-r1"
    run_dir.mkdir(parents=True)
    (run_dir / "status.json").write_text(
        json.dumps(
            {
                "phase": "gates_blocked",
                "needed_items": ["coverage:r1:proposal:SR-999", "coverage:r1:warning:SR-5"],
            }
        ),
        encoding="utf-8",
    )

    items = list_items(tmp_path, NOW)
    coverage = [i for i in items if i.source == "coverage"]
    ids = {i.id for i in coverage}
    assert "coverage:r1:proposal:SR-999" in ids
    assert "coverage:r1:warning:SR-5" in ids


# -- ordering / dedup / no-write --------------------------------------------


def test_items_are_stable_sorted_and_duplicate_free(tmp_path):
    # Three distinct sources -> at least a few items; ids must be globally unique
    # and the list must be sorted by id (stable, deterministic across calls).
    _sr(tmp_path, "SR-001", deferred={"reason": "later", "review_after": "2026-09-01T00:00:00Z"})

    list_a = list_items(tmp_path, NOW)
    list_b = list_items(tmp_path, NOW)
    ids = [i.id for i in list_a]
    assert ids == sorted(ids)
    assert len(ids) == len(set(ids))  # no duplicate id
    assert [i.id for i in list_a] == [i.id for i in list_b]  # deterministic


def test_list_items_creates_no_new_file(tmp_path):
    # Reading the inbox never writes anything -- it is a pure collector.
    _sr(tmp_path, "SR-001")
    before = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*") if p.is_file())
    list_items(tmp_path, NOW)
    after = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*") if p.is_file())
    assert before == after