from __future__ import annotations

import io
import json
import pytest
from factory.orchestrator.human_review import (
    FakeHumanReviewGate,
    HumanReviewDecision,
    StdioHumanReviewGate,
    format_review_feedback,
)

pytestmark = pytest.mark.unit


def test_stdio_gate_writes_review_pending_line_and_reads_decision():
    decision_line = json.dumps({"decision": "approve", "comments": {}}) + "\n"
    stdin = io.StringIO(decision_line)
    stdout = io.StringIO()
    gate = StdioHumanReviewGate(stdout=stdout, stdin=stdin)

    result = gate.request_review("T-001", "abc123")

    written = json.loads(stdout.getvalue().strip())
    assert written == {"type": "review_pending", "task_id": "T-001", "start_commit": "abc123"}
    assert result == HumanReviewDecision(decision="approve", comments={})


def test_stdio_gate_parses_reject_with_comments():
    decision_line = json.dumps(
        {"decision": "reject", "comments": {"src/x.py": "fix this"}}
    ) + "\n"
    gate = StdioHumanReviewGate(stdout=io.StringIO(), stdin=io.StringIO(decision_line))

    result = gate.request_review("T-001", "abc123")

    assert result.decision == "reject"
    assert result.comments == {"src/x.py": "fix this"}


def test_stdio_gate_raises_eof_error_when_stdin_closes_without_a_decision():
    gate = StdioHumanReviewGate(stdout=io.StringIO(), stdin=io.StringIO(""))
    with pytest.raises(EOFError):
        gate.request_review("T-001", "abc123")


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
