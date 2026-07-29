from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from factory.orchestrator.human_review import (
    Annotation,
    FakeHumanReviewGate,
    FileHumanReviewGate,
    HumanReviewDecision,
    format_review_feedback,
)

pytestmark = pytest.mark.unit


def test_format_feedback_anchors_line_and_severity():
    anns = [
        Annotation(file="src/foo.py", line=42, side="new", body="guard empty", severity="must-fix"),
        Annotation(file="src/foo.py", body="naming inconsistent"),
        Annotation(file="src/bar.py", line=88, side="new", body="extract branch", severity="suggestion"),
    ]
    out = format_review_feedback(anns)
    assert "src/foo.py:42 [must-fix]: guard empty" in out
    assert "src/foo.py (file): naming inconsistent" in out
    assert "src/bar.py:88 [suggestion]: extract branch" in out


def test_format_review_feedback_with_no_annotations():
    assert format_review_feedback([]) == "human review requested changes:"


def test_gate_reads_annotations(tmp_path):
    (tmp_path / "review-decision.json").write_text(
        json.dumps({
            "decision": "reject",
            "annotations": [{"file": "a.py", "line": 3, "side": "new", "body": "x"}],
            "reviewedFiles": ["a.py"],
        }),
        encoding="utf-8",
    )
    gate = FileHumanReviewGate(tmp_path, poll_interval=0.01)
    d = gate.request_review("T-1", "abc")
    assert d.decision == "reject"
    assert d.annotations[0].file == "a.py"
    assert d.annotations[0].line == 3


def test_gate_falls_back_to_legacy_comments(tmp_path):
    (tmp_path / "review-decision.json").write_text(
        json.dumps({"decision": "reject", "comments": {"a.py": "please fix"}}),
        encoding="utf-8",
    )
    gate = FileHumanReviewGate(tmp_path, poll_interval=0.01)
    d = gate.request_review("T-1", "abc")
    assert d.annotations[0].file == "a.py"
    assert d.annotations[0].body == "please fix"
    assert d.annotations[0].line is None


def test_file_gate_returns_decision_when_file_already_exists(tmp_path: Path):
    decision_path = tmp_path / "review-decision.json"
    decision_path.write_text(
        json.dumps({"decision": "approve", "annotations": []}), encoding="utf-8"
    )
    gate = FileHumanReviewGate(tmp_path, poll_interval=0.01)

    result = gate.request_review("T-001", "abc123")

    assert result == HumanReviewDecision(decision="approve", annotations=[])


def test_file_gate_deletes_the_decision_file_after_reading(tmp_path: Path):
    decision_path = tmp_path / "review-decision.json"
    decision_path.write_text(json.dumps({"decision": "approve", "annotations": []}), encoding="utf-8")
    gate = FileHumanReviewGate(tmp_path, poll_interval=0.01)

    gate.request_review("T-001", "abc123")

    assert not decision_path.exists()


def test_file_gate_waits_for_the_file_to_appear(tmp_path: Path):
    decision_path = tmp_path / "review-decision.json"
    gate = FileHumanReviewGate(tmp_path, poll_interval=0.01)

    def write_after_delay():
        time.sleep(0.05)
        decision_path.write_text(json.dumps({"decision": "approve", "annotations": []}), encoding="utf-8")

    threading.Thread(target=write_after_delay).start()
    result = gate.request_review("T-001", "abc123")

    assert result.decision == "approve"


def test_fake_gate_records_requests_and_returns_scripted_decisions():
    gate = FakeHumanReviewGate([HumanReviewDecision("approve", [])])
    result = gate.request_review("T-002", "def456")
    assert result == HumanReviewDecision("approve", [])
    assert gate.requests == [("T-002", "def456")]
