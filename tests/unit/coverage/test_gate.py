# tests/unit/coverage/test_gate.py
from __future__ import annotations

import pytest

from factory.coverage.gate import GateOutcome, run_gate

pytestmark = pytest.mark.unit


def test_pass() -> None:
    outcome, failed, warned, degraded = run_gate(
        {"SR-001": ("pass", ["some note"]), "SR-002": ("pass", [])},
        [],
    )
    assert outcome == GateOutcome.PASS


def test_fail_unlinked() -> None:
    outcome, failed, warned, degraded = run_gate(
        {"SR-001": ("unlinked", ["no task"])},
        [],
    )
    assert outcome == GateOutcome.FAIL
    assert "SR-001" in failed


def test_fail_not_implemented() -> None:
    outcome, failed, warned, degraded = run_gate(
        {"SR-001": ("not_implemented", ["code does not implement"])},
        [],
    )
    assert outcome == GateOutcome.FAIL
    assert "SR-001" in failed


def test_fail_dishonest() -> None:
    outcome, failed, warned, degraded = run_gate(
        {"SR-001": ("dishonest", ["binding test does not exercise behavior"])},
        [],
    )
    assert outcome == GateOutcome.FAIL
    assert "SR-001" in failed


def test_degraded_when_all_unverified_are_tool_failures() -> None:
    outcome, failed, warned, degraded = run_gate(
        {"SR-001": ("unverified", ["subagent dispatch failed"])},
        [{"sr_id": "SR-001", "issue": "subagent tool error"}],
    )
    assert outcome == GateOutcome.DEGRADED
    assert "SR-001" in degraded


def test_fail_when_unverified_and_no_tool_failure() -> None:
    outcome, failed, warned, degraded = run_gate(
        {"SR-001": ("unverified", ["no verdict recorded"])},
        [],
    )
    assert outcome == GateOutcome.FAIL
    assert "SR-001" in failed


def test_warn_on_suspect() -> None:
    outcome, failed, warned, degraded = run_gate(
        {"SR-001": ("suspect", ["overlap fails"])},
        [],
    )
    assert outcome == GateOutcome.PASS
    assert "SR-001" in warned


def test_warn_on_unmeasured() -> None:
    outcome, failed, warned, degraded = run_gate(
        {"SR-001": ("unmeasured", ["no passing measurement"])},
        [],
    )
    assert outcome == GateOutcome.PASS
    assert "SR-001" in warned


def test_declined_skipped() -> None:
    outcome, failed, warned, degraded = run_gate(
        {"SR-001": ("declined", [])},
        [],
    )
    assert outcome == GateOutcome.PASS


def test_mixed_degraded_and_fail() -> None:
    outcome, failed, warned, degraded = run_gate(
        {
            "SR-001": ("unverified", ["subagent dispatch failed"]),
            "SR-002": ("unlinked", ["no task"]),
        },
        [{"sr_id": "SR-001", "issue": "subagent tool error"}],
    )
    # Hard fail takes precedence over degraded
    assert outcome == GateOutcome.FAIL
    assert "SR-002" in failed
    assert "SR-001" in degraded
