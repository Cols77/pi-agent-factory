from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from factory.orchestrator.grill import FakeGrillGate, FileGrillGate, GrillResult

pytestmark = pytest.mark.unit


def _write_verdict(path: Path, decision: str, **extra) -> None:
    payload = {"decision": decision, **extra}
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_gate_reads_a_full_verdict(tmp_path: Path):
    _write_verdict(
        tmp_path / "grill-result.json",
        "agreed",
        summary="user demonstrated understanding of T-001",
        explainers=2,
    )
    gate = FileGrillGate(tmp_path, poll_interval=0.005)
    result = gate.request_grill("T-001")
    assert result == GrillResult(
        decision="agreed",
        summary="user demonstrated understanding of T-001",
        explainers=2,
    )


def test_gate_defaults_decision_when_file_is_missing_decision(tmp_path: Path):
    (tmp_path / "grill-result.json").write_text("{}", encoding="utf-8")
    gate = FileGrillGate(tmp_path, poll_interval=0.005)
    result = gate.request_grill("T-001")
    # A malformed/empty verdict is NOT an agreement -- fail closed to not-agreed.
    assert result.decision == "not-agreed"
    assert result.summary is None


def test_gate_deletes_the_verdict_file_after_reading(tmp_path: Path):
    verdict_path = tmp_path / "grill-result.json"
    _write_verdict(verdict_path, "skipped")
    gate = FileGrillGate(tmp_path, poll_interval=0.005)
    gate.request_grill("T-001")
    assert not verdict_path.exists()


def test_gate_waits_for_the_verdict_to_appear(tmp_path: Path):
    verdict_path = tmp_path / "grill-result.json"
    gate = FileGrillGate(tmp_path, poll_interval=0.005)

    def write_after_delay():
        time.sleep(0.05)
        _write_verdict(verdict_path, "agreed")

    threading.Thread(target=write_after_delay).start()
    result = gate.request_grill("T-001")
    assert result.decision == "agreed"


def test_gate_times_out_to_not_agreed_when_no_verdict_appears(tmp_path: Path):
    gate = FileGrillGate(tmp_path, poll_interval=0.005, total_timeout_s=0.02)
    result = gate.request_grill("T-001")
    # Abandonment safety net: a dead/hung grill never blocks the pipeline.
    assert result.decision == "not-agreed"
    assert result.summary == "grill timed out"


def test_gate_does_not_block_when_total_timeout_disabled(tmp_path: Path):
    verdict_path = tmp_path / "grill-result.json"
    gate = FileGrillGate(tmp_path, poll_interval=0.005, total_timeout_s=0)

    def write_after_delay():
        time.sleep(0.05)
        _write_verdict(verdict_path, "agreed", explainers=1)

    threading.Thread(target=write_after_delay).start()
    result = gate.request_grill("T-001")
    assert result.explainers == 1


def test_fake_gate_records_requests_and_returns_scripted_results():
    gate = FakeGrillGate([GrillResult("agreed"), GrillResult("skipped"), GrillResult("not-agreed")])
    assert gate.request_grill("T-002") == GrillResult("agreed")
    assert gate.request_grill("T-002") == GrillResult("skipped")
    assert gate.request_grill("T-002") == GrillResult("not-agreed")
    assert gate.requests == ["T-002", "T-002", "T-002"]
