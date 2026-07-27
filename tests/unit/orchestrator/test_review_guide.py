import json
import pytest
from factory.orchestrator.review_guide import (
    parse_gate_summary, review_guide_path, read_validation, write_review_guide,
)

pytestmark = pytest.mark.unit


def test_parse_gate_summary_all_passed():
    assert parse_gate_summary("....\n27 passed in 3.20s\n") == {"ok": True, "summary": "27 passed"}


def test_parse_gate_summary_with_failures():
    out = parse_gate_summary("F..\n2 failed, 25 passed in 3.2s\n")
    assert out["ok"] is False and "2 failed" in out["summary"] and "25 passed" in out["summary"]


def test_parse_gate_summary_non_pytest_failure_marker():
    assert parse_gate_summary("ruff....\nsrc/x.py:1:1: E501\nFAILED\n") == {"ok": False, "summary": "ran"}


def test_parse_gate_summary_none_when_no_signal():
    assert parse_gate_summary("some neutral output\n") is None


def test_review_guide_path(tmp_path):
    p = review_guide_path(tmp_path, "s1")
    assert p == tmp_path / "sessions" / ".factory-transcripts" / "s1" / "review-guide.json"


def test_read_validation_reads_existing_gate_logs(tmp_path):
    (tmp_path / "unit-gate.log").write_text("27 passed in 1s\n", encoding="utf-8")
    (tmp_path / "sim-gate.log").write_text("1 failed, 5 passed in 1s\n", encoding="utf-8")
    # no full-gate.log
    v = read_validation(tmp_path)
    assert v == [
        {"gate": "unit", "ok": True, "summary": "27 passed"},
        {"gate": "sim", "ok": False, "summary": "1 failed, 5 passed"},
    ]


def test_write_review_guide_atomic_and_best_effort(tmp_path):
    p = tmp_path / "d" / "review-guide.json"
    write_review_guide(p, {"confidence": "high", "verify": []})
    assert json.loads(p.read_text(encoding="utf-8"))["confidence"] == "high"
    # a bad path must NOT raise
    write_review_guide(tmp_path / "does" / "not" / "exist" / "x.json", {})  # dirs created; no raise
