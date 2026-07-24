from __future__ import annotations

import json
import pytest
import threading
import time
from pathlib import Path

from factory.orchestrator.human_review import (
    FileHumanReviewGate,
    FakeHumanReviewGate,
    HumanReviewDecision,
    format_review_feedback,
)

pytestmark = pytest.mark.unit


def test_file_gate_returns_decision_when_file_already_exists(tmp_path: Path):
    decision_path = tmp_path / "review-decision.json"
    decision_path.write_text(
        json.dumps({"decision": "approve", "comments": {}}), encoding="utf-8"
    )
    gate = FileHumanReviewGate(tmp_path, poll_interval=0.01)

    result = gate.request_review("T-001", "abc123")

    assert result == HumanReviewDecision(decision="approve", comments={})


def test_file_gate_parses_reject_with_comments(tmp_path: Path):
    decision_path = tmp_path / "review-decision.json"
    decision_path.write_text(
        json.dumps({"decision": "reject", "comments": {"src/x.py": "fix this"}}), encoding="utf-8"
    )
    gate = FileHumanReviewGate(tmp_path, poll_interval=0.01)

    result = gate.request_review("T-001", "abc123")

    assert result.decision == "reject"
    assert result.comments == {"src/x.py": "fix this"}


def test_file_gate_deletes_the_decision_file_after_reading(tmp_path: Path):
    decision_path = tmp_path / "review-decision.json"
    decision_path.write_text(json.dumps({"decision": "approve", "comments": {}}), encoding="utf-8")
    gate = FileHumanReviewGate(tmp_path, poll_interval=0.01)

    gate.request_review("T-001", "abc123")

    assert not decision_path.exists()


def test_file_gate_waits_for_the_file_to_appear(tmp_path: Path):
    decision_path = tmp_path / "review-decision.json"
    gate = FileHumanReviewGate(tmp_path, poll_interval=0.01)

    def write_after_delay():
        time.sleep(0.05)
        decision_path.write_text(json.dumps({"decision": "approve", "comments": {}}), encoding="utf-8")

    threading.Thread(target=write_after_delay).start()
    result = gate.request_review("T-001", "abc123")

    assert result.decision == "approve"


def test_fake_gate_records_requests_and_returns_scripted_decisions():
    gate = FakeHumanReviewGate([HumanReviewDecision("approve", {})])
    result = gate.request_review("T-002", "def456")
    assert result == HumanReviewDecision("approve", {})
    assert gate.requests == [("T-002", "def456")]


def test_format_review_feedback_lists_each_file_comment():
    text = format_review_feedback({"src/a.py": "missing check", "src/b.py": "typo"})
    assert text == (
        "human review requested changes:\n"
        "- src/a.py: missing check\n"
        "- src/b.py: typo"
    )


def test_format_review_feedback_with_no_comments():
    assert format_review_feedback({}) == "human review requested changes:"
