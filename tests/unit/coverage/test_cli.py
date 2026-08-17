# tests/unit/coverage/test_cli.py
from __future__ import annotations

import json
from pathlib import Path

import pytest

from factory.coverage.cli import (
    cmd_audit,
    cmd_consolidate,
    cmd_gate,
    cmd_record_failure,
    cmd_report,
    cmd_verdict,
)

pytestmark = pytest.mark.unit


def _feat_scope(tmp_path: Path) -> None:
    """Minimal fixture with one SR, one task, one manifest."""
    (tmp_path / "docs" / "features").mkdir(parents=True)
    (tmp_path / "docs" / "features" / "FEAT-001.md").write_text(
        "---\nid: FEAT-001\ntitle: Test\nrequirements: [SR-001]\n---\n"
    )
    (tmp_path / "requirements").mkdir()
    (tmp_path / "requirements" / "SR-001.md").write_text(
        "---\nid: SR-001\ntitle: X\nstatement: shall do X\ndomain: behavioral\n"
        "binding:\n  harness: sim-testbench\n  experiment: tests/test_x.py\n"
        "  metric: unit_pass_rate\n  trials: 1\n  assert: '== 1.0'\nchecksum: null\n---\n"
    )
    (tmp_path / "tasks").mkdir()
    (tmp_path / "tasks" / "T-001.md").write_text(
        "---\nid: T-001\ntitle: T\ndeliverables: []\nsatisfies: [SR-001]\n---\n"
    )
    (tmp_path / "evidence" / "runs").mkdir(parents=True)
    manifest = {
        "schema_version": 2, "run_id": "RUN-001", "task_id": "T-001",
        "started_at": "2026-08-01T00:00:00Z", "ended_at": "2026-08-01T01:00:00Z",
        "start_commit": "a" * 40, "result_commit": "b" * 40, "outcome": "completed",
        "inputs": {"task": {"path": "tasks/T-001.md", "sha256": "0"*64}, "requirements": [], "factory_config_sha256": "0"*64},
        "implementation": {
            "changed_files": ["src/x.py"],
            "patch": {"sha256": "0"*64, "size": 0, "media_type": "application/json"},
        },
        "dependencies": [], "validation": [], "reviews": [], "decisions": [],
        "publication": {"state": "local", "errors": []},
    }
    (tmp_path / "evidence" / "runs" / "RUN-001.json").write_text(json.dumps(manifest), encoding="utf-8")


def _verdict_json() -> dict:
    return {
        "sr_id": "SR-001", "implemented": True, "honest": True,
        "confidence": "high", "margin": None,
        "reasoning": "Test exercises the preempt path.",
        "checked": ["preempt path"], "assumed": ["fixture"],
        "verify": [],
    }


def test_audit_writes_scope_json(tmp_path: Path) -> None:
    _feat_scope(tmp_path)
    result = cmd_audit(tmp_path, "FEAT-001", run_id="test-run")
    assert result["feature"] == "FEAT-001"
    assert "SR-001" in result["srs"]
    assert result["gate"] is None


def test_verdict_validates_and_writes(tmp_path: Path) -> None:
    _feat_scope(tmp_path)
    cmd_audit(tmp_path, "FEAT-001", run_id="test-run")
    result = cmd_verdict(tmp_path, "FEAT-001", "test-run", "SR-001", _verdict_json())
    assert result["valid"] is True
    v_dir = tmp_path / "coverage-reviews" / "FEAT-001-test-run" / "verdicts"
    assert (v_dir / "SR-001.json").exists()


def test_verdict_rejects_invalid(tmp_path: Path) -> None:
    _feat_scope(tmp_path)
    cmd_audit(tmp_path, "FEAT-001", run_id="test-run")
    result = cmd_verdict(tmp_path, "FEAT-001", "test-run", "SR-001", {"sr_id": "SR-001"})
    assert result["valid"] is False
    assert result["error"] is not None


def test_consolidate_classifies_and_gates(tmp_path: Path) -> None:
    _feat_scope(tmp_path)
    cmd_audit(tmp_path, "FEAT-001", run_id="test-run")
    cmd_verdict(tmp_path, "FEAT-001", "test-run", "SR-001", _verdict_json())
    result = cmd_consolidate(tmp_path, "FEAT-001", "test-run")
    assert result["gate"]["outcome"] == "pass"
    assert len(result["states"]) == 1


def test_gate_re_derives(tmp_path: Path) -> None:
    _feat_scope(tmp_path)
    cmd_audit(tmp_path, "FEAT-001", run_id="test-run")
    cmd_verdict(tmp_path, "FEAT-001", "test-run", "SR-001", _verdict_json())
    cmd_consolidate(tmp_path, "FEAT-001", "test-run")
    outcome = cmd_gate(tmp_path, "FEAT-001", "test-run")
    assert outcome == "pass"


def test_gate_fails_on_dishonest(tmp_path: Path) -> None:
    _feat_scope(tmp_path)
    cmd_audit(tmp_path, "FEAT-001", run_id="test-run")
    v = _verdict_json()
    v["implemented"] = True
    v["honest"] = False
    v["confidence"] = "low"
    v["verify"] = [{"item": "Rewrite test", "file": "tests/test_x.py", "why": "does not assert the claim"}]
    cmd_verdict(tmp_path, "FEAT-001", "test-run", "SR-001", v)
    cmd_consolidate(tmp_path, "FEAT-001", "test-run")
    outcome = cmd_gate(tmp_path, "FEAT-001", "test-run")
    assert outcome == "fail"


def test_record_failure_then_degraded_gate(tmp_path: Path) -> None:
    _feat_scope(tmp_path)
    cmd_audit(tmp_path, "FEAT-001", run_id="test-run")
    result = cmd_record_failure(tmp_path, "FEAT-001", "test-run", "SR-001", "subagent tool error")
    assert result["recorded"] is True
    consolidated = cmd_consolidate(tmp_path, "FEAT-001", "test-run")
    assert consolidated["gate"]["outcome"] == "degraded"
    assert "SR-001" in consolidated["gate"]["degraded"]


def test_report_renders_human_summary(tmp_path: Path) -> None:
    _feat_scope(tmp_path)
    cmd_audit(tmp_path, "FEAT-001", run_id="test-run")
    cmd_verdict(tmp_path, "FEAT-001", "test-run", "SR-001", _verdict_json())
    cmd_consolidate(tmp_path, "FEAT-001", "test-run")
    assert cmd_report(tmp_path, "FEAT-001", "test-run")
