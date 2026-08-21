# tests/unit/coverage/test_cli.py
from __future__ import annotations

import json
import subprocess
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
from factory.evidence.records import build_historical_record, write_historical_record

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


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def test_audit_writes_scope_json(tmp_path: Path) -> None:
    _feat_scope(tmp_path)
    result = cmd_audit(tmp_path, "FEAT-001", run_id="test-run")
    assert result["feature"] == "FEAT-001"
    assert "SR-001" in result["srs"]
    assert result["gate"] is None
    assert result["srs"]["SR-001"]["tasks"] == [
        {
            "task_id": "T-001",
            "changed_files": ["src/x.py"],
            "manifests": ["RUN-001"],
            "record_paths": [],
            "evidence_state": "present",
        }
    ]


def test_audit_reports_missing_evidence_for_all_linked_tasks(tmp_path: Path) -> None:
    (tmp_path / "docs" / "features").mkdir(parents=True)
    (tmp_path / "docs" / "features" / "FEAT-NAV-017.md").write_text(
        "---\nid: FEAT-NAV-017\ntitle: Navigator\nrequirements: [SR-NAV-001]\n---\n"
    )
    (tmp_path / "requirements").mkdir()
    (tmp_path / "requirements" / "SR-NAV-001.md").write_text(
        "---\nid: SR-NAV-001\ntitle: Navigator\nstatement: shall navigate\ndomain: behavioral\n"
        "binding:\n  harness: sim-testbench\n  experiment: tests/test_navigator.py\n"
        "  metric: unit_pass_rate\n  trials: 1\n  assert: '== 1.0'\nchecksum: null\n---\n"
    )
    (tmp_path / "tasks").mkdir()
    for task_id in ("T-058", "T-067"):
        (tmp_path / "tasks" / f"{task_id}.md").write_text(
            f"---\nid: {task_id}\ntitle: Navigator task\nstatus: done\nsatisfies: [SR-NAV-001]\n---\n"
        )

    result = cmd_audit(tmp_path, "FEAT-NAV-017", run_id="test-run")

    assert result["srs"]["SR-NAV-001"]["tasks"] == [
        {
            "task_id": "T-058",
            "changed_files": [],
            "manifests": [],
            "record_paths": [],
            "evidence_state": "missing",
        },
        {
            "task_id": "T-067",
            "changed_files": [],
            "manifests": [],
            "record_paths": [],
            "evidence_state": "missing",
        },
    ]
    assert result["overlaps"]["SR-NAV-001"] == {
        "ok": False,
        "reason": "missing evidence for tasks",
        "missing_task_ids": ["T-058", "T-067"],
    }


def test_audit_uses_historical_record_changed_files_for_overlap(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "user.name", "Coverage CLI Test")
    _feat_scope(tmp_path)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text(
        "from factory.navigator import navigate\n\n\ndef test_navigate() -> None:\n    assert navigate()\n",
        encoding="utf-8",
    )
    start = _commit(tmp_path, "add feature scope")
    navigator = tmp_path / "src" / "factory" / "navigator.py"
    navigator.parent.mkdir(parents=True)
    navigator.write_text("def navigate() -> bool:\n    return True\n", encoding="utf-8")
    result_commit = _commit(tmp_path, "implement navigator")
    record = build_historical_record(
        tmp_path,
        "T-001",
        start,
        result_commit,
        "reviewer@example.invalid",
        "Record approved historical implementation.",
    )
    write_historical_record(tmp_path / "evidence", record)

    result = cmd_audit(tmp_path, "FEAT-001", run_id="test-run")

    overlap = result["overlaps"]["SR-001"]
    assert overlap["ok"] is True
    assert overlap["overlap"] == ("src/factory/navigator.py",)
    assert overlap.get("reason") != "no changed files from tasks"


def test_audit_reports_recorded_empty_evidence(tmp_path: Path) -> None:
    _feat_scope(tmp_path)
    manifest_path = tmp_path / "evidence" / "runs" / "RUN-001.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["implementation"]["changed_files"] = []
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = cmd_audit(tmp_path, "FEAT-001", run_id="test-run")

    assert result["overlaps"]["SR-001"] == {
        "ok": False,
        "reason": "recorded evidence has no changed files",
        "empty_task_ids": ["T-001"],
    }


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


def test_pipeline_end_to_end_on_fixture() -> None:
    """The committed demo fixture: audit -> verdict -> consolidate -> gate."""
    from pathlib import Path as P

    root = P(__file__).resolve().parents[2] / "fixtures" / "coverage-demo"
    run_id = "demo-run"
    audit = cmd_audit(root, "FEAT-001", run_id=run_id)
    assert "SR-001" in audit["srs"]
    # The demo test imports the implementation, so overlap is true.
    assert audit["overlaps"]["SR-001"]["ok"] is True
    verdict = {
        "sr_id": "SR-001", "implemented": True, "honest": True,
        "confidence": "high", "margin": None,
        "reasoning": "preempt() returns the detection flag and the test drives it.",
        "checked": ["preempt path in src/demo/feature.py"],
        "assumed": ["detection flag is the only behavior"],
        "verify": [],
    }
    assert cmd_verdict(root, "FEAT-001", run_id, "SR-001", verdict)["valid"] is True
    report = cmd_consolidate(root, "FEAT-001", run_id)
    assert report["gate"]["outcome"] == "pass"
    assert cmd_gate(root, "FEAT-001", run_id) == "pass"
    assert cmd_report(root, "FEAT-001", run_id)
