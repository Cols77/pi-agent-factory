from __future__ import annotations

import json
import subprocess
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
    human_review_to_gate_item,
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


def test_gate_archives_the_exact_decision_and_working_tree_diff(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    source = repo / "source.py"
    source.write_text("before = True\n", encoding="utf-8")
    subprocess.run(["git", "add", "source.py"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=repo, check=True)
    start_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()
    source.write_text("after = True\n", encoding="utf-8")

    transcript_dir = tmp_path / "transcript"
    transcript_dir.mkdir()
    (transcript_dir / "review-guide.json").write_text(
        json.dumps({"confidence": "high", "verify": [{"item": "branch"}]}),
        encoding="utf-8",
    )
    (transcript_dir / "review-decision.json").write_text(
        json.dumps({
            "decision": "reject",
            "annotations": [{"file": "source.py", "line": 1, "side": "new", "body": "explain this"}],
            "reviewedFiles": ["source.py"],
        }),
        encoding="utf-8",
    )

    decision = FileHumanReviewGate(transcript_dir, repo, poll_interval=0.01).request_review(
        "T-001", start_commit
    )

    record = json.loads((transcript_dir / "reviews" / "review-001.json").read_text(encoding="utf-8"))
    assert decision.reviewed_files == ["source.py"]
    assert record["task_id"] == "T-001"
    assert record["decision"] == "reject"
    assert record["annotations"][0]["body"] == "explain this"
    assert record["reviewed_files"] == ["source.py"]
    assert record["review_guide"]["confidence"] == "high"
    assert "+after = True" in record["diff"]
    assert "-before = True" in record["diff"]


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


def test_human_review_to_gate_item_maps_approve_reject(tmp_path: Path):
    approve = human_review_to_gate_item(
        HumanReviewDecision("approve", []), "review:17"
    )
    assert approve.item_id == "review:17"
    assert approve.action == "accept"
    assert approve.reason == ""

    reject = human_review_to_gate_item(
        HumanReviewDecision(
            "reject",
            [Annotation(file="src/foo.py", line=3, body="explain this")],
        ),
        "review:18",
    )
    assert reject.action == "reject"
    assert "src/foo.py:3" in reject.reason
    assert "explain this" in reject.reason


def test_human_review_gate_json_stays_byte_compatible(tmp_path: Path):
    """Task 2 Test 5: the orchestrator HumanReviewGate JSON must not change
    shape. Whatever FileHumanReviewGate writes today (the archive record) is
    pinned verbatim -- the gate adapter is additive and must not alter it."""
    transcript_dir = tmp_path / "transcript"
    transcript_dir.mkdir()
    reviews_dir = transcript_dir / "reviews"
    reviews_dir.mkdir(parents=True)
    (transcript_dir / "review-decision.json").write_text(
        json.dumps({
            "decision": "reject",
            "annotations": [{"file": "a.py", "line": 1, "side": "new", "body": "x"}],
            "reviewedFiles": ["a.py"],
        }),
        encoding="utf-8",
    )

    gate = FileHumanReviewGate(transcript_dir, poll_interval=0.01)
    gate.request_review("T-001", "abc123")
    payload = json.loads(
        (reviews_dir / "review-001.json").read_text(encoding="utf-8")
    )

    # Exact top-level key set -- adding/removing/renaming any field changes
    # the HumanReviewGate JSON shape and must fail this pin.
    assert set(payload) == {
        "version",
        "reviewed_at",
        "task_id",
        "start_commit",
        "decision",
        "annotations",
        "reviewed_files",
        "diff",
        "diff_error",
        "review_guide",
    }
    # Annotation JSON shape pinned verbatim.
    assert set(payload["annotations"][0]) == {"file", "body", "line", "side", "severity"}
    # The review-decision source file is consumed+deleted, never rewritten.
    assert not (transcript_dir / "review-decision.json").exists()
    # The adapter is purely additive: writing it produced no new HumanReview JSON.
    assert sorted(p.name for p in transcript_dir.iterdir()) == ["reviews"]
